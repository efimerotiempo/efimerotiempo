from flask import Flask, render_template, request, redirect, url_for, jsonify, Response
from datetime import date, timedelta, datetime
from itertools import zip_longest
import uuid
import os
import copy
import json
import re
import unicodedata
from werkzeug.utils import secure_filename
from urllib.request import Request, urlopen
import urllib.parse
import sys
import importlib.util
import random
from queue import Queue

from localtime import local_today, local_now

# Always load this repository's ``schedule.py`` regardless of the working
# directory or any installed package named ``schedule``.  After importing, pull
# the required symbols from the loaded module.  This approach prevents
# ``ImportError`` even if an unexpected third-party module shadows the local
# file.
_schedule_dir = os.path.dirname(os.path.abspath(__file__))
_schedule_path = os.path.join(_schedule_dir, "schedule.py")
if _schedule_dir not in sys.path:
    sys.path.insert(0, _schedule_dir)
_spec = importlib.util.spec_from_file_location("schedule", _schedule_path)
_schedule_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_schedule_mod)
sys.modules['schedule'] = _schedule_mod

# Expose schedule helpers as module-level names
load_projects = _schedule_mod.load_projects
save_projects = _schedule_mod.save_projects
schedule_projects = _schedule_mod.schedule_projects
load_dismissed = _schedule_mod.load_dismissed
save_dismissed = _schedule_mod.save_dismissed
load_extra_conflicts = _schedule_mod.load_extra_conflicts
save_extra_conflicts = _schedule_mod.save_extra_conflicts
load_notes = _schedule_mod.load_notes
save_notes = _schedule_mod.save_notes
load_worker_notes = _schedule_mod.load_worker_notes
save_worker_notes = _schedule_mod.save_worker_notes
load_vacations = _schedule_mod.load_vacations
save_vacations = _schedule_mod.save_vacations
load_daily_hours = _schedule_mod.load_daily_hours
save_daily_hours = _schedule_mod.save_daily_hours
_load_worker_hours_func = getattr(_schedule_mod, "load_worker_hours", None)
_save_worker_hours_func = getattr(_schedule_mod, "save_worker_hours", None)
load_inactive_workers = _schedule_mod.load_inactive_workers
save_inactive_workers = _schedule_mod.save_inactive_workers
set_worker_order = _schedule_mod.set_worker_order
PHASE_ORDER = _schedule_mod.PHASE_ORDER
WORKERS = _schedule_mod.WORKERS
IGOR_END = _schedule_mod.IGOR_END
compute_schedule_map = _schedule_mod.compute_schedule_map
UNPLANNED = _schedule_mod.UNPLANNED
if hasattr(_schedule_mod, "phase_start_map"):
    phase_start_map = _schedule_mod.phase_start_map
else:
    def phase_start_map(projects):
        mapping = compute_schedule_map(projects)
        result = {}
        for pid, items in mapping.items():
            for worker, day, phase, hours, _ in items:
                result.setdefault(pid, {}).setdefault(phase, day)
        return result
WEEKEND = _schedule_mod.WEEKEND
HOURS_PER_DAY = _schedule_mod.HOURS_PER_DAY
HOURS_LIMITS = _schedule_mod.HOURS_LIMITS
next_workday = _schedule_mod.next_workday
DEADLINE_MSG = 'Fecha cliente soprepasada.'
CLIENT_DEADLINE_MSG = 'FECHA TOPE SOBREPASADA.'

app = Flask(__name__)
app.url_map.strict_slashes = False


@app.template_filter('format_due_date')
def format_due_date(value, include_year=True):
    """Return a human readable ``dd/mm`` or ``dd/mm/YYYY`` string."""

    if not value:
        return ''

    if isinstance(value, str):
        value = value.strip()
        if not value:
            return ''
        try:
            value = date.fromisoformat(value[:10])
        except ValueError:
            parsed = parse_input_date(value)
            if not parsed:
                return value
            value = parsed

    if not isinstance(value, date):
        return str(value)

    fmt = '%d/%m/%Y' if include_year else '%d/%m'
    return value.strftime(fmt)

# Basic HTTP authentication setup
AUTH_USER = os.environ.get("EFIMERO_USER", "admin")
AUTH_PASS = os.environ.get("EFIMERO_PASS", "secreto")


def _check_auth(user, password):
    return user == AUTH_USER and password == AUTH_PASS


def _authenticate():
    return Response(
        "Acceso denegado.\n",
        401,
        {"WWW-Authenticate": 'Basic realm="Login requerido"'},
    )


@app.before_request
def _require_auth():
    if request.path.startswith("/static") or request.path.startswith("/kanbanize-webhook"):
        return
    auth = request.authorization
    if not auth or not _check_auth(auth.username, auth.password):
        return _authenticate()

COLORS = [
    '#ffd9e8', '#ffe4c4', '#e0ffff', '#d0f0c0', '#fef9b7', '#ffe8d6',
    '#dcebf1', '#e6d3f8', '#fdfd96', '#e7f5ff', '#ccffcc', '#e9f7fd',
    '#ffd8be', '#f8f0fb', '#f2ffde', '#fae1dd', '#fffff0', '#e8f0fe',
    '#ffcfd2', '#f0fff4', '#e7f9ea', '#fff2cc', '#e0e0ff', '#f0f8ff',
]

_last_api_color = None


def _next_api_color():
    """Return a light random color distinct from the last one."""
    global _last_api_color
    while True:
        r = random.randint(0, 255)
        g = random.randint(0, 255)
        b = random.randint(0, 255)
        # Relative luminance to avoid very dark colors
        luminance = 0.299 * r + 0.587 * g + 0.114 * b
        if luminance < 140:
            continue
        color = f"#{r:02x}{g:02x}{b:02x}"
        if color != _last_api_color:
            _last_api_color = color
            return color
MIN_DATE = date(2024, 1, 1)
MAX_DATE = date(2026, 12, 31)
UPLOAD_FOLDER = os.path.join('static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
DATA_DIR = os.environ.get('EFIMERO_DATA_DIR', 'data')
KANBAN_CARDS_FILE = os.path.join(DATA_DIR, 'kanban_cards.json')
KANBAN_PREFILL_FILE = os.path.join(DATA_DIR, 'kanban_prefill.json')
KANBAN_COLUMN_COLORS_FILE = os.path.join(DATA_DIR, 'kanban_column_colors.json')
TRACKER_FILE = os.path.join(DATA_DIR, 'tracker.json')

if _load_worker_hours_func and _save_worker_hours_func:
    load_worker_hours = _load_worker_hours_func
    save_worker_hours = _save_worker_hours_func
else:
    _WORKER_HOURS_FILE = os.path.join(DATA_DIR, 'worker_hours.json')
    _WORKER_DEFAULT_LIMITS = {worker: limit for worker, limit in HOURS_LIMITS.items()}

    def _sanitize_worker_hours_payload(data):
        """Return a mapping of workers to hour overrides (1..12)."""

        if not isinstance(data, dict):
            return {}
        cleaned = {}
        for worker, value in data.items():
            if worker not in WORKERS:
                continue
            try:
                hours = int(value)
            except (TypeError, ValueError):
                continue
            if 1 <= hours <= 12:
                cleaned[worker] = hours
        return cleaned

    def _sync_worker_defaults():
        for worker in WORKERS:
            if worker not in _WORKER_DEFAULT_LIMITS:
                limit = HOURS_LIMITS.get(worker, HOURS_PER_DAY)
                if isinstance(limit, (int, float)):
                    _WORKER_DEFAULT_LIMITS[worker] = limit
                else:
                    _WORKER_DEFAULT_LIMITS[worker] = HOURS_PER_DAY
        for worker in list(_WORKER_DEFAULT_LIMITS):
            if worker not in WORKERS:
                _WORKER_DEFAULT_LIMITS.pop(worker, None)

    def _apply_worker_hour_overrides(overrides):
        _sync_worker_defaults()
        for worker, default in _WORKER_DEFAULT_LIMITS.items():
            HOURS_LIMITS[worker] = default
        for worker, hours in overrides.items():
            if worker in HOURS_LIMITS:
                HOURS_LIMITS[worker] = hours

    def load_worker_hours():
        overrides = {}
        if os.path.exists(_WORKER_HOURS_FILE):
            try:
                with open(_WORKER_HOURS_FILE, 'r') as fh:
                    raw = json.load(fh)
            except (json.JSONDecodeError, OSError):
                raw = {}
            overrides = _sanitize_worker_hours_payload(raw)
        _apply_worker_hour_overrides(overrides)
        return overrides

    def save_worker_hours(data):
        overrides = _sanitize_worker_hours_payload(data or {})
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(_WORKER_HOURS_FILE, 'w') as fh:
            json.dump(overrides, fh)
        _apply_worker_hour_overrides(overrides)

    # Ensure in-memory limits reflect any persisted overrides.
    try:
        load_worker_hours()
    except Exception:
        pass

KANBAN_POPUP_FIELDS = [
    'LANZAMIENTO',
    'MATERIAL',
    'CALDERERIA',
    'PINTADO',
    'MECANIZADO',
    'TRATAMIENTO',
]

PROJECT_TITLE_PATTERN = re.compile(r'\bOF\s*\d{4}\b', re.IGNORECASE)
_NON_ALNUM_RE = re.compile(r'[^0-9a-z]+')


def normalize_key(text):
    """Return a case-insensitive token stripped of diacritics and punctuation."""

    if not text:
        return ''

    normalized = unicodedata.normalize('NFKD', str(text))
    normalized = ''.join(
        ch for ch in normalized if not unicodedata.category(ch).startswith('M')
    )
    normalized = normalized.casefold()
    return _NON_ALNUM_RE.sub('', normalized)


MATERIAL_ALERT_COLUMNS = {
    normalize_key('Plegado/Curvado'),
    normalize_key('Comerciales varios'),
    normalize_key('Tubo/perfil/llanta/chapa'),
    normalize_key('Oxicorte'),
    normalize_key('Laser'),
    normalize_key('Plegado/Curvado - fabricación'),
    normalize_key('Material Incompleto'),
    normalize_key('Material NO CONFORME'),
}


def _upload_folder_path():
    """Return the absolute path to the uploads directory."""

    if os.path.isabs(UPLOAD_FOLDER):
        return UPLOAD_FOLDER
    return os.path.join(app.root_path, UPLOAD_FOLDER)


def _extract_upload_filename(image_value):
    """Return the file name for a stored project image, if local."""

    if not image_value:
        return None
    value = str(image_value).strip().replace('\\', '/').lstrip('/')
    if not value:
        return None
    if value.startswith('static/'):
        value = value[len('static/'):]
    if not value.startswith('uploads/'):
        return None
    basename = os.path.basename(value[len('uploads/'):])
    return basename or None


def _remove_upload_file(image_value):
    """Delete the file associated with *image_value* if it lives in uploads."""

    filename = _extract_upload_filename(image_value)
    if not filename:
        return False
    directory = _upload_folder_path()
    path = os.path.join(directory, filename)
    try:
        os.remove(path)
        return True
    except FileNotFoundError:
        return False
    except OSError:
        app.logger.warning('No se pudo eliminar la imagen %s', path, exc_info=True)
        return False


def prune_orphan_uploads(projects):
    """Remove files in the uploads folder that no project references."""

    directory = _upload_folder_path()
    if not os.path.isdir(directory):
        return
    referenced = set()
    for project in projects or []:
        filename = _extract_upload_filename(project.get('image'))
        if filename:
            referenced.add(filename)
    try:
        entries = os.listdir(directory)
    except OSError:
        app.logger.warning('No se pudo listar la carpeta de imágenes', exc_info=True)
        return
    for name in entries:
        path = os.path.join(directory, name)
        if not os.path.isfile(path):
            continue
        if name in referenced:
            continue
        try:
            os.remove(path)
        except OSError:
            app.logger.warning('No se pudo eliminar la imagen huérfana %s', path, exc_info=True)

READY_TO_ARCHIVE_COLUMN = normalize_key('Ready to Archive')

SSE_CLIENTS = []


def compute_material_status_map(projects):
    """Return a mapping pid->material availability status for planning views."""

    status_map = {}
    try:
        compras_raw, _ = load_compras_raw()
        raw_links = attach_phase_starts(build_project_links(compras_raw), projects)
        projects_with_children = set()
        columns_by_pid = {}
        for project in projects or []:
            pid = project.get('id')
            if pid:
                status_map[str(pid)] = 'complete'
        for entry in raw_links:
            pid = entry.get('pid')
            if not pid:
                continue
            pid_key = str(pid)
            details = entry.get('link_details') or []
            if details or entry.get('links'):
                projects_with_children.add(pid_key)
            if details:
                project_columns = columns_by_pid.setdefault(pid_key, set())
            if status_map.get(pid_key) == 'missing':
                continue
            for detail in details:
                if not isinstance(detail, dict):
                    continue
                column = detail.get('column')
                column_key = normalize_key(column)
                if column_key:
                    project_columns.add(column_key)
                if column_key in MATERIAL_ALERT_COLUMNS:
                    status_map[pid_key] = 'missing'
                    break
        for pid_key, columns in columns_by_pid.items():
            if not columns:
                continue
            if status_map.get(pid_key) == 'missing':
                continue
            if all(column == READY_TO_ARCHIVE_COLUMN for column in columns):
                status_map[pid_key] = 'archived'
        for pid_key, current in list(status_map.items()):
            if pid_key not in projects_with_children and current != 'missing':
                status_map[pid_key] = 'pending'
    except Exception:  # pragma: no cover - defensive logging
        app.logger.exception('Failed to compute material status from project links')
    return status_map


def get_card_custom_id(card):
    """Return the Kanban custom card identifier (e.g. ``OF 1234``) if present."""

    if not isinstance(card, dict):
        return ''

    for key in (
        'customCardId',
        'customcardid',
        'customId',
        'customid',
    ):
        value = card.get(key)
        if value:
            text = str(value).strip()
            if text:
                return text
    return ''


def broadcast_event(data):
    for q in list(SSE_CLIENTS):
        q.put(data)

@app.route('/events')
def event_stream():
    def gen():
        q = Queue()
        SSE_CLIENTS.append(q)
        try:
            while True:
                data = q.get()
                yield f"data: {json.dumps(data)}\n\n"
        except GeneratorExit:
            SSE_CLIENTS.remove(q)
    return Response(gen(), mimetype='text/event-stream', headers={'Cache-Control': 'no-cache'})


def load_tracker():
    if os.path.exists(TRACKER_FILE):
        try:
            with open(TRACKER_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_tracker(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(TRACKER_FILE, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def build_move_reason(projects, pid, phase, part, mode, info):
    """Return a detailed explanation of how a phase was distributed."""
    schedule, _ = schedule_projects(projects)
    segments = []
    for worker, days in schedule.items():
        for day, tasks in days.items():
            for t in tasks:
                if t.get('pid') == pid and t['phase'] == phase and (
                    part is None or t.get('part') == part
                ):
                    segments.append((worker, day, t))
    segments.sort(key=lambda x: (x[1], x[2].get('start', 0)))
    explanations = []
    for idx, (worker, day, t) in enumerate(segments):
        start = t.get('start', 0)
        hours = t['hours']
        day_fmt = date.fromisoformat(day).strftime('%d/%m/%Y')
        day_tasks = sorted(schedule[worker][day], key=lambda x: x.get('start', 0))
        before = [
            x
            for x in day_tasks
            if x is not t and x['start'] + x['hours'] <= start
        ]
        if before:
            prev = ', '.join(
                f"{b['project']} - {b['phase']} ({b['hours']}h)" for b in before
            )
            msg = f"{day_fmt}: {hours}h tras {start}h ocupadas por {prev}"
        else:
            msg = f"{day_fmt}: {hours}h al inicio de la jornada"
        limit = HOURS_LIMITS.get(worker, HOURS_PER_DAY)
        end = start + hours
        if idx < len(segments) - 1:
            remaining = limit - end
            if remaining > 0:
                msg += f"; quedaban {remaining}h libres y se continuó al día siguiente"
            else:
                msg += "; jornada completa, se continuó al día siguiente"
        explanations.append(msg)
    if mode == 'push' and info.get('affected'):
        explanations.append(
            'Se desplazaron fases posteriores para mantener la continuidad'
        )
    return '\n'.join(explanations)

# Kanbanize integration constants
KANBANIZE_BASE_URL = 'https://caldereriacpk.kanbanize.com'
KANBANIZE_BOARD_TOKEN = os.environ.get('KANBANIZE_BOARD_TOKEN', '682d829a0aafe44469o50acd')
KANBANIZE_API_KEY = "jpQfMzS8AzdyD70zLkilBjP0Uig957mOATuM0BOE"

# Lanes from Kanbanize that the webhook listens to for project events.
ARCHIVE_LANES = {'Acero al Carbono', 'Inoxidable - Aluminio'}

# Column and lane filters for the orders calendar and associated tables
PEDIDOS_ALLOWED_COLUMNS = {
    'Plegado/Curvado',
    'Planif. Bekola',
    'Planif. AZ',
    'Comerciales varios',
    'Tubo/perfil/llanta/chapa',
    'Oxicorte',
    'Laser',
    'Premecanizado',
    'Planif. Premec.',
    'Plegado/curvado - Fabricación',
    'Material Incompleto',
    'Material NO CONFORME',
    'Planificado para montaje',
}

PEDIDOS_HIDDEN_COLUMNS = [
    "Ready to Archive",
    "Material recepcionado",
    "Pdte. Verificación",
]

PENDING_VERIFICATION_COLUMN_KEYS = {
    normalize_key('Pdte. Verificación'),
}

PEDIDOS_UNCONFIRMED_COLUMNS = {
    'Tau',
    'Bekola',
    'AZ',
    'OTROS',
    'Tratamiento',
    'Planf. TAU',
    'Planif. OTROS',
}

PEDIDOS_EXTRA_LANE_COLUMNS = {
    'Planif. Premec.',
    'Premecanizado',
}

PEDIDOS_OFFSET_TO_PLAN_END_COLUMNS = {
    'Tratamiento',
    'Tratamiento final',
    'Planf. TAU',
    'Planif. Bekola',
    'Planif. AZ',
    'Planif. OTROS',
    'Tau',
    'Bekola',
    'AZ',
    'OTROS',
}

PROJECT_LINK_LANES = {
    'acero al carbono',
    'inoxidable - aluminio',
    'seguimiento compras',
}

PEDIDOS_ALLOWED_KEYS = {normalize_key(col) for col in PEDIDOS_ALLOWED_COLUMNS}
PEDIDOS_UNCONFIRMED_KEYS = {normalize_key(col) for col in PEDIDOS_UNCONFIRMED_COLUMNS}
PEDIDOS_HIDDEN_KEYS = {normalize_key(col) for col in PEDIDOS_HIDDEN_COLUMNS}
PEDIDOS_OFFSET_TO_PLAN_END_KEYS = {
    normalize_key(col) for col in PEDIDOS_OFFSET_TO_PLAN_END_COLUMNS
}
PEDIDOS_SEGUIMIENTO_LANE_KEY = normalize_key('Seguimiento compras')

MATERIAL_EXCLUDED_COLUMNS = {
    normalize_key('Ready to Archive'),
    normalize_key('Ready to archieve'),
    normalize_key('Material Recepcionado'),
    normalize_key('Material recepcionado'),
    normalize_key('Pdte. Verificación'),
}


def active_workers(today=None):
    """Return the list of workers shown in the calendar."""
    if today is None:
        today = local_today()
    workers = [w for w in WORKERS.keys() if w != UNPLANNED]
    if today >= IGOR_END and 'Igor' in workers:
        workers.remove('Igor')
    inactive = set(load_inactive_workers())
    return [w for w in workers if w not in inactive]


def parse_input_date(value):
    """Parse a date string that may omit the year.

    Accepts formats like 'dd-mm', 'dd/mm' or full ISO 'YYYY-MM-DD'.
    If the year is missing, the current year is used.
    Returns a ``date`` instance.
    """
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        parts = value.replace('/', '-').split('-')
        if len(parts) >= 2:
            try:
                day = int(parts[0])
                month = int(parts[1])
            except ValueError:
                return None
            year = local_today().year
            if len(parts) == 3:
                try:
                    year = int(parts[2])
                except ValueError:
                    pass
            try:
                return date(year, month, day)
            except ValueError:
                return None
    return None


def parse_kanban_date(value):
    """Parse Kanbanize date strings which may include time."""
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        return parse_input_date(value)


def _sort_cell_tasks(schedule):
    """Sort tasks in each day so started phases appear before unstarted ones."""
    for days in schedule.values():
        for tasks in days.values():
            tasks.sort(key=lambda t: (not t.get('start_date'), t.get('start', 0)))


def format_dd_mm(value):
    """Return 'dd-mm' string for a date or date string."""
    if not value:
        return ''
    if isinstance(value, str):
        value = parse_input_date(value)
    if isinstance(value, date):
        return f"{value.day:02d}-{value.month:02d}"
    return ''


def load_kanban_cards():
    """Return stored Kanban cards, skipping malformed entries."""
    if os.path.exists(KANBAN_CARDS_FILE):
        with open(KANBAN_CARDS_FILE, 'r') as f:
            try:
                data = json.load(f)
            except Exception:
                return []
        # Ensure we always return a list of dictionaries
        return [c for c in data if isinstance(c, dict)]
    return []


def save_kanban_cards(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(KANBAN_CARDS_FILE, 'w') as f:
        json.dump(data, f)


def last_kanban_card(cid):
    """Return the most recent stored Kanban card with the given *cid*.

    If no prior card is found, an empty dict is returned.  This helper lets the
    webhook determine which fields actually changed in Kanbanize so that the
    planner only updates those specific fields.
    """
    cid = str(cid)
    for entry in reversed(load_kanban_cards()):
        card = entry.get('card') or {}
        old_cid = card.get('taskid') or card.get('cardId') or card.get('id')
        if str(old_cid) == cid:
            return card
    return {}


def load_compras_raw():
    allowed_lanes = {lane.lower() for lane in PROJECT_LINK_LANES}
    compras_raw = {}
    column_colors = load_column_colors()
    updated_colors = False
    for entry in load_kanban_cards():
        if not isinstance(entry, dict):
            continue
        card = entry.get('card') or {}
        if not isinstance(card, dict):
            continue
        lane_name = (card.get('lanename') or card.get('laneName') or '').strip()
        if lane_name.lower() not in allowed_lanes:
            continue
        column = (card.get('columnname') or card.get('columnName') or '').strip()
        cid = card.get('taskid') or card.get('cardId') or card.get('id')
        if not cid:
            continue
        compras_raw[cid] = {
            'card': card,
            'stored_date': entry.get('stored_title_date'),
            'prev_date': entry.get('previous_title_date'),
        }
        if column and column not in column_colors:
            column_colors[column] = _next_api_color()
            updated_colors = True
    if updated_colors:
        save_column_colors(column_colors)
    return compras_raw, column_colors


def split_project_and_client(title):
    title = (title or '').strip()
    if not title:
        return '', ''

    match = PROJECT_TITLE_PATTERN.search(title)
    if not match:
        return title, ''

    start = match.start()
    end = match.end()
    tail = title[end:]
    separator = re.search(r'\s+-\s+', tail)
    if separator:
        end += separator.start()
    else:
        end = len(title)

    project = title[start:end].strip(' -')
    before = title[:start].strip(' -')
    after = title[end:].strip(' -')

    client_parts = [part for part in (before, after) if part]
    client = ' - '.join(client_parts)

    if not project:
        project = title

    return project, client


def build_project_links(compras_raw):
    children_by_parent = {}
    children_norms_by_parent = {}
    children_ids_by_parent = {}
    seguimiento_titles = {}
    seguimiento_by_id = {}
    candidate_cards = []
    excluded_columns = {
        normalize_key(col) for col in PEDIDOS_HIDDEN_COLUMNS
        if normalize_key(col) not in PENDING_VERIFICATION_COLUMN_KEYS
    }
    target_lanes = {normalize_key('Acero al Carbono'), normalize_key('Inoxidable - Aluminio')}
    seguimiento_lane = normalize_key('Seguimiento compras')
    seen_candidates = set()

    card_index = {}
    def _attach_child_card_metadata(serialized, card_id):
        """Populate ``serialized`` with lane/column info from cached Kanban cards."""

        if not isinstance(serialized, dict):
            return serialized

        key = str(card_id).strip() if card_id not in (None, '') else ''
        if not key:
            return serialized

        card = card_index.get(key)
        if not isinstance(card, dict):
            return serialized

        if not serialized.get('column'):
            column = (card.get('columnname') or card.get('columnName') or '').strip()
            if column:
                serialized['column'] = column

        if not serialized.get('lane'):
            lane = (card.get('lanename') or card.get('laneName') or '').strip()
            if lane:
                serialized['lane'] = lane

        return serialized

    for data in compras_raw.values():
        card = data['card']
        if not isinstance(card, dict):
            continue
        card_id = card.get('taskid') or card.get('cardId') or card.get('id')
        if card_id:
            card_index[str(card_id)] = card

    for data in compras_raw.values():
        card = data['card']
        if not isinstance(card, dict):
            continue
        title = (card.get('title') or '').strip()
        custom_id = get_card_custom_id(card)
        cid_value = card.get('taskid') or card.get('cardId') or card.get('id')
        cid = str(cid_value) if cid_value else None
        links_info = card.get('links') or {}

        parents = []
        children = []
        if isinstance(links_info, dict):
            parent_entries = links_info.get('parent')
            if isinstance(parent_entries, list):
                parents.extend(parent_entries)
            parent_entries = links_info.get('parents')
            if isinstance(parent_entries, list):
                parents.extend(parent_entries)

            child_entries = links_info.get('child')
            if isinstance(child_entries, list):
                children.extend(child_entries)
            child_entries = links_info.get('children')
            if isinstance(child_entries, list):
                children.extend(child_entries)

        normalized_child_title = normalize_key(title)
        if parents and normalized_child_title:
            for p in parents:
                if not isinstance(p, dict):
                    continue
                pid = p.get('taskid') or p.get('cardId') or p.get('id')
                if not pid:
                    continue
                key = str(pid)
                lst = children_by_parent.setdefault(key, [])
                norms = children_norms_by_parent.setdefault(key, set())
                ids = children_ids_by_parent.setdefault(key, set())
                if cid:
                    if cid in ids:
                        continue
                    ids.add(cid)
                elif normalized_child_title in norms:
                    continue
                lst.append((cid, title))
                norms.add(normalized_child_title)

        if children and cid:
            for ch in children:
                if isinstance(ch, dict):
                    child_id = ch.get('taskid') or ch.get('cardId') or ch.get('id')
                    child_title = (ch.get('title') or '').strip()
                    if child_id:
                        cached_card = card_index.get(str(child_id))
                        if cached_card:
                            canonical = (cached_card.get('title') or '').strip()
                            if canonical:
                                child_title = canonical
                    if child_id and not child_title:
                        fetched = _fetch_kanban_card(child_id)
                        if fetched:
                            child_title = (fetched.get('title') or '').strip()
                    norm_child = normalize_key(child_title)
                    child_key = str(child_id) if child_id else None
                    if (child_key or norm_child) and cid:
                        lst = children_by_parent.setdefault(cid, [])
                        norms = children_norms_by_parent.setdefault(cid, set())
                        ids = children_ids_by_parent.setdefault(cid, set())
                        if child_key:
                            if child_key in ids:
                                continue
                            ids.add(child_key)
                        elif not norm_child or norm_child in norms:
                            continue
                        lst.append((child_key, child_title))
                        if norm_child:
                            norms.add(norm_child)

        lane_name = (card.get('lanename') or card.get('laneName') or '').strip()
        board_name = (card.get('boardName') or card.get('boardname') or '').strip()
        lane_key = normalize_key(lane_name)
        column = (card.get('columnname') or card.get('columnName') or '').strip()
        column_key = normalize_key(column)

        if (
            title
            and normalized_child_title
            and lane_key == seguimiento_lane
            and column_key not in excluded_columns
        ):
            deadline = parse_kanban_date(card.get('deadline'))
            detail = {
                'id': cid or '',
                'title': title,
                'column': column,
                'deadline': deadline.isoformat() if deadline else None,
                'lane': lane_name,
            }
            if detail['id']:
                seguimiento_by_id[detail['id']] = detail
            titles = seguimiento_titles.setdefault(normalized_child_title, [])
            if detail['id']:
                if not any(existing.get('id') == detail['id'] for existing in titles):
                    titles.append(detail)
            else:
                if not any(existing.get('title') == title for existing in titles):
                    titles.append(detail)

        if cid and lane_key in target_lanes and cid not in seen_candidates:
            project_name, client_name = split_project_and_client(title)
            due = parse_kanban_date(card.get('deadline'))
            base_display = title or project_name or ''
            if custom_id and base_display:
                if base_display.lower().startswith(custom_id.lower()):
                    display_title = base_display
                else:
                    display_title = f"{custom_id} - {base_display}"
            else:
                display_title = base_display or custom_id
            candidate_cards.append({
                'cid': cid,
                'project': project_name,
                'title': title,
                'display_title': display_title,
                'client': client_name,
                'custom_card_id': custom_id,
                'due': due,
                'column': column,
                'lane': lane_name,
                'board': board_name,
            })
            seen_candidates.add(cid)

    links_table = []
    for info in candidate_cards:
        child_links = children_by_parent.get(info['cid'], [])
        matches = []
        match_ids = []
        match_details = []
        seen_norms = set()
        seen_ids = set()
        for child_id, child_title in child_links:
            norm_child = normalize_key(child_title)
            child_id = str(child_id).strip() if child_id else ''
            if not norm_child and not child_id:
                continue
            if child_id and child_id in seen_ids:
                continue
            if norm_child and norm_child in seen_norms and not child_id:
                continue
            lane_entries = seguimiento_titles.get(norm_child) if norm_child else None
            appended = False
            if lane_entries:
                for lane_detail in lane_entries:
                    lane_id = str(lane_detail.get('id') or '').strip()
                    lane_title = (lane_detail.get('title') or '').strip() or child_title
                    if lane_id and lane_id in seen_ids:
                        continue
                    if lane_title in matches:
                        continue
                    matches.append(lane_title)
                    match_ids.append(lane_id)
                    serialized = {'title': lane_title}
                    if lane_id:
                        serialized['id'] = lane_id
                    column_name = lane_detail.get('column')
                    if column_name:
                        serialized['column'] = column_name
                    deadline_value = lane_detail.get('deadline')
                    if deadline_value:
                        serialized['deadline'] = deadline_value
                    lane_value = lane_detail.get('lane')
                    if lane_value:
                        serialized['lane'] = lane_value
                    match_details.append(serialized)
                    if lane_id:
                        seen_ids.add(lane_id)
                    _attach_child_card_metadata(serialized, lane_id or child_id)
                    appended = True
                if norm_child:
                    seen_norms.add(norm_child)
            if not appended:
                if child_title not in matches:
                    matches.append(child_title)
                    match_ids.append(child_id)
                    serialized = {'title': child_title}
                    if child_id:
                        serialized['id'] = child_id
                    detail = seguimiento_by_id.get(child_id) if child_id else None
                    if detail:
                        column_name = detail.get('column')
                        if column_name:
                            serialized['column'] = column_name
                        deadline_value = detail.get('deadline')
                        if deadline_value:
                            serialized['deadline'] = deadline_value
                        lane_value = detail.get('lane')
                        if lane_value:
                            serialized['lane'] = lane_value
                    _attach_child_card_metadata(serialized, child_id or detail and detail.get('id'))
                    match_details.append(serialized)
                    if child_id:
                        seen_ids.add(child_id)
                if norm_child:
                    seen_norms.add(norm_child)
        entry = {
            'project': info['project'],
            'title': info['title'],
            'display_title': info['display_title'],
            'client': info['client'],
            'custom_card_id': info['custom_card_id'],
            'links': matches,
        }
        if info.get('column'):
            entry['column'] = info['column']
        if info.get('lane'):
            entry['lane'] = info['lane']
        if info.get('board'):
            entry['board'] = info['board']
        if matches and any(match_ids):
            entry['link_ids'] = match_ids
        elif not matches:
            entry['link_ids'] = []
        if match_details:
            entry['link_details'] = match_details
        elif not matches:
            entry['link_details'] = []
        if info['due']:
            entry['due'] = info['due'].isoformat()
        else:
            entry['due'] = None
        links_table.append(entry)
    return links_table


def attach_phase_starts(links_table, projects=None):
    """Attach the scheduled start date of the ``montar`` phase to each link."""

    if projects is None:
        projects = load_projects()
    projects = filter_visible_projects(projects)
    start_mapping = phase_start_map(projects)
    montar_by_name = {}
    ids_by_name = {}
    montar_by_key = {}
    ids_by_key = {}
    for proj in projects:
        phase_starts = start_mapping.get(proj['id'], {})
        montar_start = phase_starts.get('montar')
        name = (proj['name'] or '').strip()
        if not name:
            continue
        if montar_start:
            montar_by_name[name] = montar_start
        ids_by_name[name] = proj['id']

        split_name, _ = split_project_and_client(name)
        if split_name and split_name != name:
            if montar_start and split_name not in montar_by_name:
                montar_by_name[split_name] = montar_start
            ids_by_name.setdefault(split_name, proj['id'])

        keys = {normalize_key(name)}
        if split_name:
            keys.add(normalize_key(split_name))

        custom_id = (proj.get('custom_card_id') or '').strip()
        if custom_id:
            ids_by_name.setdefault(custom_id, proj['id'])
            if montar_start and custom_id not in montar_by_name:
                montar_by_name[custom_id] = montar_start
            keys.add(normalize_key(custom_id))

        code_match = PROJECT_TITLE_PATTERN.search(name)
        if not code_match and custom_id:
            code_match = PROJECT_TITLE_PATTERN.search(custom_id)
        if code_match:
            code_key = code_match.group(0)
            ids_by_name.setdefault(code_key, proj['id'])
            if montar_start and code_key not in montar_by_name:
                montar_by_name[code_key] = montar_start
            keys.add(normalize_key(code_key))

        for key in keys:
            if not key:
                continue
            if montar_start and key not in montar_by_key:
                montar_by_key[key] = montar_start
            ids_by_key.setdefault(key, proj['id'])

    enriched = []
    for item in links_table:
        entry = dict(item)
        montar_start = None
        pid = None

        candidate_values = []
        for field in ('project', 'title', 'display_title', 'custom_card_id'):
            value = (item.get(field) or '').strip()
            if value:
                candidate_values.append(value)
                split_value, _ = split_project_and_client(value)
                if split_value and split_value != value:
                    candidate_values.append(split_value)
        for value in list(candidate_values):
            code_match = PROJECT_TITLE_PATTERN.search(value)
            if code_match:
                candidate_values.append(code_match.group(0))

        for value in candidate_values:
            if montar_start and pid:
                break
            if not montar_start:
                montar_start = montar_by_name.get(value)
            if not montar_start:
                norm_key = normalize_key(value)
                if norm_key:
                    montar_start = montar_by_key.get(norm_key)
            if not pid:
                pid = ids_by_name.get(value)
            if not pid:
                norm_key = normalize_key(value)
                if norm_key:
                    pid = ids_by_key.get(norm_key)
        if montar_start:
            entry['montar_start'] = montar_start
        if pid:
            entry['pid'] = pid
        enriched.append(entry)
    return enriched


def compute_pedidos_entries(compras_raw, column_colors, today):
    pedidos = {}
    unconfirmed = []
    calendar_titles = set()

    for data in compras_raw.values():
        card = data['card']
        stored_date = data.get('stored_date')
        prev_date = data.get('prev_date')
        title = (card.get('title') or '').strip()
        if not title:
            continue

        _, client_name = split_project_and_client(title)
        custom_id = get_card_custom_id(card)

        column = (card.get('columnname') or card.get('columnName') or '').strip()
        lane_name = (card.get('lanename') or card.get('laneName') or '').strip()
        column_key = normalize_key(column)
        lane_key = normalize_key(lane_name)

        column_allowed = (
            column_key in PEDIDOS_ALLOWED_KEYS
            or column_key in PEDIDOS_UNCONFIRMED_KEYS
        )

        if not column_allowed or lane_key != PEDIDOS_SEGUIMIENTO_LANE_KEY:
            continue

        if column_key in PEDIDOS_HIDDEN_KEYS:
            continue

        cid = card.get('taskid') or card.get('cardId') or card.get('id')

        if stored_date:
            try:
                day, month = [int(x) for x in stored_date.split('/')]
                d = date(today.year, month, day)
            except Exception:
                d = parse_kanban_date(card.get('deadline'))
        elif column_key in PEDIDOS_UNCONFIRMED_KEYS:
            d = None
        else:
            m = re.search(r"\((\d{2})/(\d{2})\)", title)
            if m:
                day, month = int(m.group(1)), int(m.group(2))
                try:
                    d = date(today.year, month, day)
                except ValueError:
                    d = parse_kanban_date(card.get('deadline'))
            else:
                d = parse_kanban_date(card.get('deadline'))

        entry = {
            'project': title,
            'color': column_colors.get(column, '#999999'),
            'hours': None,
            'lane': lane_name,
            'client': client_name,
            'column': column,
            'cid': cid,
            'prev_date': prev_date,
            'custom_card_id': custom_id,
            'kanban_date': stored_date or card.get('deadline') or '',
        }

        if d:
            pedidos.setdefault(d, []).append(entry)
        else:
            unconfirmed.append(entry)

        calendar_titles.add(title)

    return pedidos, unconfirmed, calendar_titles


def filter_project_links_by_titles(links_table, valid_titles, valid_ids=None):
    if not links_table:
        return []

    valid_norms = {normalize_key(title) for title in (valid_titles or []) if title}
    valid_ids = {str(cid) for cid in (valid_ids or []) if cid}

    if not valid_norms and not valid_ids:
        return []

    filtered = []
    for item in links_table:
        link_titles = list(item.get('links') or [])
        link_ids = list(item.get('link_ids') or [])
        if len(link_ids) < len(link_titles):
            link_ids.extend([''] * (len(link_titles) - len(link_ids)))
        link_details = list(item.get('link_details') or [])

        matches = []
        kept_ids = []
        kept_details = []
        seen_norms = set()
        seen_ids = set()
        for idx, (title, cid) in enumerate(zip(link_titles, link_ids)):
            text = title or ''
            cid_str = str(cid).strip() if cid not in (None, '') else ''
            norm_link = normalize_key(text)
            allow = False
            if cid_str and cid_str in valid_ids and cid_str not in seen_ids:
                allow = True
            elif norm_link and norm_link in valid_norms and norm_link not in seen_norms:
                allow = True
            if allow:
                matches.append(text)
                kept_ids.append(cid_str)
                detail = link_details[idx] if idx < len(link_details) else None
                if isinstance(detail, dict):
                    detail_copy = {k: v for k, v in detail.items() if v not in (None, '')}
                else:
                    detail_copy = {}
                if 'title' not in detail_copy or not detail_copy['title']:
                    detail_copy['title'] = text
                if cid_str and ('id' not in detail_copy or not detail_copy['id']):
                    detail_copy['id'] = cid_str
                kept_details.append(detail_copy)
                if norm_link:
                    seen_norms.add(norm_link)
                if cid_str:
                    seen_ids.add(cid_str)
        if not matches:
            continue
        entry = dict(item)
        entry['links'] = matches
        if any(kept_ids):
            entry['link_ids'] = kept_ids
        else:
            entry.pop('link_ids', None)
        if kept_details:
            entry['link_details'] = kept_details
        else:
            entry.pop('link_details', None)
        filtered.append(entry)
    return filtered


def _extract_blocking_material_titles(entry, planned_day):
    """Return titles that block scheduling because of material deadlines."""

    if not entry or not isinstance(planned_day, date):
        return []

    details = entry.get('link_details')
    raw_titles = entry.get('links')
    if not details and not raw_titles:
        return []

    blocking = []
    seen = set()
    for detail, fallback in zip_longest(details or [], raw_titles or []):
        if isinstance(detail, dict):
            title = (detail.get('title') or fallback or '').strip()
            column = detail.get('column')
            deadline_str = detail.get('deadline')
        else:
            title = (fallback or '').strip()
            column = None
            deadline_str = None
        if not title:
            continue
        norm_title = normalize_key(title)
        if norm_title in seen:
            continue
        if column and normalize_key(column) in MATERIAL_EXCLUDED_COLUMNS:
            continue
        if not deadline_str:
            continue
        deadline = parse_kanban_date(deadline_str)
        if not isinstance(deadline, date):
            continue
        if deadline > planned_day:
            blocking.append(title)
            seen.add(norm_title)
    return blocking


def _find_link_entry_for_project(project, links_table):
    """Return the Columna 1 entry that corresponds to *project*."""

    if not project:
        return None

    keys = set()
    name = (project.get('name') or '').strip()
    if name:
        keys.add(normalize_key(name))
        proj_name, _ = split_project_and_client(name)
        if proj_name:
            keys.add(normalize_key(proj_name))
        code_match = re.search(r'OF\s*\d{4}', name, re.IGNORECASE)
        if code_match:
            keys.add(normalize_key(code_match.group(0)))

    custom = (project.get('custom_card_id') or '').strip()
    if custom:
        keys.add(normalize_key(custom))

    if not keys:
        return None

    for item in links_table or []:
        for field in ('project', 'title', 'display_title', 'custom_card_id'):
            value = item.get(field)
            if not value:
                continue
            if normalize_key(value) in keys:
                return item
    return None


def material_blockers_for_project(projects, pid, planned_day):
    """Return Kanban Seguimiento Compras titles that block *pid* on *planned_day*."""

    if not pid or not planned_day:
        return []

    if isinstance(planned_day, str):
        try:
            planned_date = date.fromisoformat(planned_day)
        except ValueError:
            return []
    elif isinstance(planned_day, date):
        planned_date = planned_day
    else:
        return []

    str_pid = str(pid)
    project = next((p for p in projects if str(p.get('id')) == str_pid), None)
    if not project:
        return []

    compras_raw, _ = load_compras_raw()
    base_links = build_project_links(compras_raw)
    enriched_links = attach_phase_starts(base_links, projects)
    entry = next(
        (item for item in enriched_links if str(item.get('pid')) == str_pid),
        None,
    )
    if not entry:
        entry = _find_link_entry_for_project(project, enriched_links)
    if not entry:
        entry = _find_link_entry_for_project(project, base_links)
    if not entry:
        return []

    return _extract_blocking_material_titles(entry, planned_date)


def load_column_colors():
    if os.path.exists(KANBAN_COLUMN_COLORS_FILE):
        with open(KANBAN_COLUMN_COLORS_FILE, 'r') as f:
            return json.load(f)
    return {}


def save_column_colors(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(KANBAN_COLUMN_COLORS_FILE, 'w') as f:
        json.dump(data, f)


def load_prefill_project():
    """Return the pending Kanbanize project data, if any."""
    if os.path.exists(KANBAN_PREFILL_FILE):
        with open(KANBAN_PREFILL_FILE, 'r') as f:
            try:
                return json.load(f)
            except Exception:
                return {}
    return {}


def save_prefill_project(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(KANBAN_PREFILL_FILE, 'w') as f:
        json.dump(data, f)


def clear_prefill_project():
    if os.path.exists(KANBAN_PREFILL_FILE):
        try:
            os.remove(KANBAN_PREFILL_FILE)
        except Exception:
            pass

def normalize_card(c):
    return {
        "taskid": c.get("card_id"),
        "title": c.get("title"),
        "customid": c.get("custom_id"),
        "columnid": c.get("column_id"),
        "laneid": c.get("lane_id"),
        "boardid": c.get("board_id"),
        "workflowid": c.get("workflow_id"),
        "columnname": c.get("column_name"),
        "lanename": c.get("lane_name"),
    }

def _decode_json(value):
    """Try to parse *value* as JSON, ignoring trailing text."""
    if isinstance(value, bytes):
        try:
            value = value.decode('utf-8', errors='ignore')
        except Exception:
            return value
    if isinstance(value, str):
        # Quita posibles %encoding y espacios
        value = urllib.parse.unquote(value).strip()
        try:
            obj, _ = json.JSONDecoder().raw_decode(value)
            return obj
        except Exception:
            return value
    return value


def _parse_kanban_payload(req):
    """Return payload dict from a webhook request."""
    data = req.get_json(silent=True)
    if isinstance(data, str):
        data = _decode_json(data)
    if not data:
        payload = (
            req.form.get('kanbanize_payload')
            or req.form.get('payload')
            or req.form.get('data')
        )
        if not payload:
            raw = req.get_data(as_text=True)
            payload = raw.strip() if raw else None
        if payload:
            if isinstance(payload, str):
                payload = urllib.parse.unquote(payload)
            data = _decode_json(payload)
    if isinstance(data, dict):
        return data
    return None
def build_calendar(start, end):
    """Return full days list, collapsed columns and week spans."""
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    cols = []
    i = 0
    while i < len(days):
        d = days[i]
        if d.weekday() == 5:
            wk = [d]
            if i + 1 < len(days) and days[i + 1].weekday() == 6:
                wk.append(days[i + 1])
            cols.append({"type": "weekend", "dates": wk})
            i += len(wk)
        else:
            cols.append({"type": "day", "dates": [d]})
            i += 1

    def weeks_in_year(year: int) -> int:
        """Return the number of ISO weeks in ``year``."""
        return date(year, 12, 28).isocalendar().week

    def wnum(day: date) -> int:
        """Return custom week number so 9 July is always week 28."""
        ref = date(day.year, 7, 9)
        ref_week = ref.isocalendar().week
        iso_year, iso_week, _ = day.isocalendar()
        if iso_year > day.year:
            diff = iso_week + weeks_in_year(day.year) - ref_week
        elif iso_year < day.year:
            diff = iso_week - weeks_in_year(day.year - 1) - ref_week
        else:
            diff = iso_week - ref_week
        return 28 + diff

    week_spans = []
    current_week = wnum(cols[0]["dates"][0])
    span = 0
    for c in cols:
        week = wnum(c["dates"][0])
        if week != current_week:
            week_spans.append({"week": current_week, "span": span})
            current_week = week
            span = 1
        else:
            span += 1
    week_spans.append({"week": current_week, "span": span})
    return days, cols, week_spans


def move_phase_date(
    projects,
    pid,
    phase,
    new_date,
    worker=None,
    part=None,
    *,
    save=True,
    mode="split",
    push_from=None,
    unblock=False,
    skip_block=False,
    start_hour=None,
    track=None,
):
    """Move ``phase`` of project ``pid`` so it starts on ``new_date``.

    ``mode`` controls how existing work is handled:

    * ``"split"`` (default) keeps other tasks in place, allowing the phase to
      be divided around them.
    * ``"push"`` shifts subsequent tasks for the same worker so the phase can
      remain continuous.

    Return tuple ``(day, warning, info)`` where ``day`` is the first day of the
    phase after rescheduling (``None`` when it could not be moved), ``warning``
    carries deadline or blocking messages, and ``info`` aggregates metadata
    about the operation.
    """
    def _fail(warn, info=None):
        return None, warn, info

    if part in (None, '', 'None'):
        part = None
    else:
        try:
            part = int(part)
        except Exception:
            part = None

    mapping = compute_schedule_map(projects)
    tasks = [t for t in mapping.get(pid, []) if t[2] == phase]
    if not tasks:
        return _fail('Fase no encontrada')
    if part is not None:
        tasks = [t for t in tasks if t[4] == part]
        if not tasks:
            return _fail('Fase no encontrada')
    proj = next((p for p in projects if p['id'] == pid), None)
    if not proj:
        return _fail('Proyecto no encontrado')
    if phase != 'pedidos' and any(
        t['phase'] == phase and (part is None or t.get('part') == part)
        for t in proj.get('frozen_tasks', [])
    ):
        return _fail('Fase congelada')

    vac_map = _schedule_mod._build_vacation_map()
    if (
        phase != 'pedidos'
        and worker
        and worker != 'Irene'
        and new_date in vac_map.get(worker, set())
    ):
        return _fail('Vacaciones en esa fecha')

    # Remember the originally requested day.  When ``start_hour`` exceeds the
    # daily limit we normally roll the phase to the next workday, but in push
    # mode we instead keep the phase on the requested day and start at hour 0 so
    # subsequent tasks can be shifted after it.
    target_day = new_date
    sched_day = new_date
    sched_hour = start_hour if start_hour is not None else 0
    limit = HOURS_LIMITS.get(worker, HOURS_PER_DAY)
    push_same_day = False
    if start_hour is not None and start_hour >= limit:
        if mode == "push":
            sched_hour = 0
            push_same_day = True
        else:
            sched_day = next_workday(sched_day)
            sched_hour = 0

    warning = None
    affected = track if track is not None else []
    if proj.get('due_date'):
        try:
            due_dt = date.fromisoformat(proj['due_date'])
            phase_hours = proj['phases'].get(phase)
            if isinstance(phase_hours, list):
                if part is None or part >= len(phase_hours):
                    return _fail('Fase no encontrada')
                hours = int(phase_hours[part])
            else:
                hours = int(phase_hours)
            days_needed = (hours + HOURS_PER_DAY - 1) // HOURS_PER_DAY
            test_end = sched_day
            for _ in range(days_needed - 1):
                test_end = next_workday(test_end)
            if test_end > due_dt:
                msg = CLIENT_DEADLINE_MSG if proj.get('due_confirmed') else DEADLINE_MSG
                warning = f"{msg}\n{proj['name']} - {proj['client']} - {due_dt.strftime('%Y-%m-%d')}"
        except Exception:
            pass
    if 'hours' not in locals():
        phase_val = proj['phases'].get(phase)
        if isinstance(phase_val, list):
            if part is None or part >= len(phase_val):
                return _fail('Fase no encontrada')
            hours = int(phase_val[part])
        else:
            hours = int(phase_val)
    # Apply the change to the real project list
    if part is None and not isinstance(proj['phases'].get(phase), list):
        seg_starts = proj.setdefault('segment_starts', {}).setdefault(phase, [None])
        seg_starts[0] = sched_day.isoformat()
        seg_hours = proj.setdefault('segment_start_hours', {}).setdefault(phase, [None])
        seg_hours[0] = sched_hour
        if worker:
            proj.setdefault('assigned', {})[phase] = worker
    else:
        seg_starts = proj.setdefault('segment_starts', {}).setdefault(
            phase, [None] * len(proj['phases'][phase])
        )
        idx = part if part is not None else 0
        while len(seg_starts) <= idx:
            seg_starts.append(None)
        seg_starts[idx] = sched_day.isoformat()
        seg_hours = proj.setdefault('segment_start_hours', {}).setdefault(
            phase, [None] * len(proj['phases'][phase])
        )
        if idx >= len(seg_hours):
            seg_hours.extend([None] * (idx + 1 - len(seg_hours)))
        seg_hours[idx] = sched_hour
        if worker:
            seg_workers = proj.setdefault('segment_workers', {}).setdefault(
                phase, [None] * len(proj['phases'][phase])
            )

            if idx >= len(seg_workers):
                seg_workers.extend([None] * (idx + 1 - len(seg_workers)))
            seg_workers[idx] = worker
    if worker:
        proj['planned'] = worker != UNPLANNED

    if mode == "push" and worker and worker != UNPLANNED:
        # Move other tasks for the worker after this phase so it stays
        # contiguous without splitting. Only phases starting from ``push_from``
        # (if provided) are shifted; otherwise, all tasks from ``new_date``
        # onward are moved.
        phase_val = proj['phases'].get(phase)
        if isinstance(phase_val, list):
            hours = int(phase_val[part or 0])
        else:
            hours = int(phase_val)

        # Determine the exact end of the moved phase taking into account
        # the worker's daily limit and vacations so subsequent phases can be
        # appended immediately afterwards.
        vac_days = _schedule_mod._build_vacation_map().get(worker, set())
        limit = HOURS_LIMITS.get(worker, HOURS_PER_DAY)
        end_day = sched_day
        end_hour = sched_hour
        remaining = hours
        while remaining > 0:
            if end_day in vac_days:
                end_day = next_workday(end_day)
                end_hour = 0
                continue
            free = limit - end_hour
            if remaining <= free:
                end_hour += remaining
                remaining = 0
            else:
                remaining -= free
                end_day = next_workday(end_day)
                end_hour = 0
        if end_hour >= limit:
            end_day = next_workday(end_day)
            end_hour = 0

        # `current_day`/`current_hour` mark the next free slot after inserting
        # the new phase. Pushed phases will be placed sequentially here.
        current_day = end_day
        current_hour = end_hour

        mapping = compute_schedule_map(projects)
        start_push = sched_day if push_same_day else next_workday(target_day)
        if push_from:
            pf_pid, pf_phase, pf_part = push_from
            selected = None
            for w, day_str, ph, hrs, prt in mapping.get(pf_pid, []):
                if (
                    w == worker
                    and ph == pf_phase
                    and (pf_part is None or prt == pf_part)
                ):
                    d = date.fromisoformat(day_str)
                    if d >= start_push and (selected is None or d < selected):
                        selected = d
            if selected is not None:
                start_push = selected
        seen = {}
        for opid, items in mapping.items():
            for w, day_str, ph, hrs, prt in items:
                if w != worker:
                    continue
                d = date.fromisoformat(day_str)
                if d < start_push:
                    continue
                if opid == pid and ph == phase and (part is None or prt == part):
                    continue
                key = (opid, ph, prt)
                if key not in seen or d < seen[key]:
                    seen[key] = d

        for start, opid, oph, oprt in sorted(
            (v, k[0], k[1], k[2]) for k, v in seen.items()
        ):
            other_proj = next((p for p in projects if p['id'] == opid), None)
            if not other_proj:
                while current_day in vac_days:
                    current_day = next_workday(current_day)
                    current_hour = 0
                continue
            if oph != 'pedidos' and any(
                t['phase'] == oph and (oprt is None or t.get('part') == oprt)
                for t in other_proj.get('frozen_tasks', [])
            ):
                if not unblock and not skip_block:
                    return _fail(
                        {
                            'pid': opid,
                            'phase': oph,
                            'part': oprt,
                            'name': other_proj.get('name', ''),
                        }
                    )
                if skip_block:
                    val = other_proj['phases'][oph]
                    if isinstance(val, list):
                        h = int(val[oprt])
                    else:
                        h = int(val)
                    rem = h
                    day = start
                    hour = 0
                    while rem > 0:
                        if day in vac_days:
                            day = next_workday(day)
                            hour = 0
                            continue
                        free = limit - hour
                        if rem <= free:
                            hour += rem
                            rem = 0
                        else:
                            rem -= free
                            day = next_workday(day)
                            hour = 0
                    current_day = day
                    current_hour = hour
                    if current_hour >= limit:
                        current_day = next_workday(current_day)
                        current_hour = 0
                    continue
                # unblock
                other_proj['frozen_tasks'] = [
                    t
                    for t in other_proj.get('frozen_tasks', [])
                    if not (t['phase'] == oph and (oprt is None or t.get('part') == oprt))
                ]
            while current_day in vac_days:
                current_day = next_workday(current_day)
                current_hour = 0
            move_phase_date(
                projects,
                opid,
                oph,
                current_day,
                worker,
                oprt,
                save=False,
                mode="split",
                start_hour=current_hour,
                track=affected,
            )
            affected.append({'pid': opid, 'phase': oph, 'part': oprt})
            val = other_proj['phases'][oph]
            if isinstance(val, list):
                h = int(val[oprt])
            else:
                h = int(val)
            rem = h
            day = current_day
            hour = current_hour
            while rem > 0:
                if day in vac_days:
                    day = next_workday(day)
                    hour = 0
                    continue
                free = limit - hour
                if rem <= free:
                    hour += rem
                    rem = 0
                else:
                    rem -= free
                    day = next_workday(day)
                    hour = 0
            current_day = day
            current_hour = hour
            if current_hour >= limit:
                current_day = next_workday(current_day)
                current_hour = 0

    if save:
        save_projects(projects)
    # Determine end of this phase for logging purposes. When ``mode`` was
    # ``push`` the values may already be available from the push calculation
    # above; otherwise compute them now.
    if "hours" in locals():
        vac_days = vac_map.get(worker, set())
        end_day = sched_day if 'end_day' not in locals() or end_day is None else end_day
        end_hour = sched_hour if 'end_hour' not in locals() or end_hour is None else end_hour
        if end_day == sched_day and end_hour == sched_hour:
            remaining = hours
            day = end_day
            hour = end_hour
            limit = HOURS_LIMITS.get(worker, HOURS_PER_DAY)
            while remaining > 0:
                if day in vac_days:
                    day = next_workday(day)
                    hour = 0
                    continue
                free = limit - hour
                if remaining <= free:
                    hour += remaining
                    remaining = 0
                else:
                    remaining -= free
                    day = next_workday(day)
                    hour = 0
            end_day = day
            end_hour = hour
            if end_hour >= limit:
                end_day = next_workday(end_day)
                end_hour = 0
    info = {
        'start_hour': sched_hour,
        'end_day': end_day.isoformat() if 'end_day' in locals() else sched_day.isoformat(),
        'end_hour': end_hour if 'end_hour' in locals() else sched_hour,
        'affected': track or [],
    }

    return sched_day.isoformat(), warning, info


def get_projects():
    projects = load_projects()
    changed = False
    color_index = 0
    inactive = set(load_inactive_workers())
    for p in projects:
        if p.get('source') == 'api':
            color = p.get('color')
            if not color or not re.fullmatch(r"#[0-9A-Fa-f]{6}", color):
                p['color'] = _next_api_color()
                changed = True
        else:
            if not p.get('color') or p.get('color') not in COLORS:
                p['color'] = COLORS[color_index % len(COLORS)]
                color_index += 1
                changed = True

        p.pop('frozen', None)
        p.setdefault('frozen_tasks', [])
        p.setdefault('blocked', False)
        p.setdefault('material_confirmed_date', '')
        p.setdefault('kanban_attachments', [])
        if not isinstance(p.get('kanban_display_fields'), dict):
            p['kanban_display_fields'] = {}
            changed = True
        column_value = p.get('kanban_column')
        if column_value is None:
            p['kanban_column'] = ''
            changed = True
        elif not isinstance(column_value, str):
            p['kanban_column'] = str(column_value)
            changed = True
        archived_value = p.get('kanban_archived')
        if isinstance(archived_value, bool):
            pass
        elif isinstance(archived_value, str):
            normalized = archived_value.strip().lower() in (
                'true', '1', 'yes', 'si', 'sí'
            )
            p['kanban_archived'] = normalized
            changed = True
        else:
            normalized = bool(archived_value)
            if archived_value is None:
                normalized = False
            p['kanban_archived'] = normalized
            changed = True
        p.setdefault('observations', '')
        p.setdefault('due_confirmed', False)
        p.setdefault('due_warning', False)
        if 'kanban_image' in p and not p['kanban_attachments']:
            old = p.pop('kanban_image')
            if isinstance(old, str) and old:
                p['kanban_attachments'] = [{'name': old, 'url': old}]
        for att in p['kanban_attachments']:
            url = att.get('url', '')
            if url and (url.startswith('/') or not re.match(r'https?://', url)):
                att['url'] = f"{KANBANIZE_BASE_URL.rstrip('/')}/{url.lstrip('/')}"
        if 'source' not in p:
            p['source'] = 'manual'
            changed = True

        if not p.get('planned', True):
            today_str = local_today().isoformat()
            if p.get('start_date') != today_str:
                p['start_date'] = today_str
                changed = True

        segs = p.get('segment_starts')
        if segs:
            for ph, val in list(segs.items()):
                if val and not isinstance(val, list):
                    segs[ph] = [val]

        assigned = p.setdefault('assigned', {})
        for ph, w in list(assigned.items()):
            if w in inactive:
                assigned[ph] = UNPLANNED
                changed = True

        # Update planned flag based on assigned workers
        if any(w != UNPLANNED for w in assigned.values()):
            if not p.get('planned', False):
                p['planned'] = True
                changed = True
        else:
            if p.get('planned', False):
                p['planned'] = False
                changed = True

        missing = [ph for ph in p['phases'] if ph not in p['assigned']]
        for ph in missing:
            p['assigned'][ph] = UNPLANNED
            changed = True
        total = len(p.get('phases', {}))
        planned = sum(
            1
            for ph in p.get('phases', {})
            if p['assigned'].get(ph) and p['assigned'][ph] != UNPLANNED
        )
        if planned == 0:
            p['plan_state'] = 'none'
        elif planned == total:
            p['plan_state'] = 'all'
        else:
            p['plan_state'] = 'partial'
    if changed:
        save_projects(projects)
    prune_orphan_uploads(projects)
    return projects


def _phase_value_has_hours(value):
    """Return ``True`` if *value* represents a positive amount of hours."""

    if isinstance(value, list):
        return any(_phase_value_has_hours(v) for v in value)
    if isinstance(value, dict):
        return any(_phase_value_has_hours(v) for v in value.values())
    if isinstance(value, bool):
        return bool(value)
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False


def project_has_hours(project):
    """Return ``True`` if any project phase has a positive number of hours."""

    phases = project.get('phases') or {}
    return any(_phase_value_has_hours(v) for v in phases.values())


def filter_visible_projects(projects):
    """Filter *projects* down to those with at least one phase with hours."""

    visible = []
    for p in projects:
        if not project_has_hours(p):
            continue
        if p.get('kanban_archived'):
            continue
        column = (p.get('kanban_column') or '').strip().lower()
        if column == 'ready to archive':
            continue
        visible.append(p)
    return visible


def get_visible_projects():
    """Return the list of projects that should appear in the UI tabs."""

    return filter_visible_projects(get_projects())


def expand_for_display(projects):
    """Return a list of project rows including extra ones for split phases."""
    rows = []
    for p in projects:
        base = copy.deepcopy(p)
        extras = []
        for ph, val in p.get('phases', {}).items():
            if isinstance(val, list) and len(val) > 1:
                base['phases'][ph] = val[0]
                for seg in val[1:]:
                    extra = copy.deepcopy(p)
                    extra['phases'] = {ph: seg}
                    if p.get('assigned'):
                        extra['assigned'] = {ph: p['assigned'].get(ph)}
                    else:
                        extra['assigned'] = {}
                    extras.append(extra)
        rows.append(base)
        rows.extend(extras)
    return rows


def split_markers(schedule):
    """Return set of tuples identifying split boundaries."""
    parts = {}
    for worker, days in schedule.items():
        for day, tasks in days.items():
            for t in tasks:
                if t.get('part') is None:
                    continue
                key = (t['pid'], t['phase'], t['part'])
                parts.setdefault(key, []).append(date.fromisoformat(day))
    starts = set()
    ends = set()
    grouped = {}
    for (pid, phase, part), days in parts.items():
        days.sort()
        grouped.setdefault((pid, phase), {})[part] = days
    for (pid, phase), segs in grouped.items():
        for idx, lst in segs.items():
            if idx > 0 and lst:
                starts.add(f"{pid}|{phase}|{lst[0].isoformat()}")
            if lst:
                ends.add(f"{pid}|{phase}|{lst[-1].isoformat()}")
    return starts.union(ends)


def _kanban_card_to_project(card):
    """Convert a Kanbanize card payload into a project dict."""
    fields_raw = card.get('customFields') or card.get('customfields')
    fields_raw = _decode_json(fields_raw) or {}
    if isinstance(fields_raw, list):
        fields = {f.get('name'): f.get('value') for f in fields_raw if isinstance(f, dict)}
    elif isinstance(fields_raw, dict):
        fields = dict(fields_raw)
    else:
        fields = {}
    fields.setdefault('CALDERERIA', fields.get('CALDERERÍA'))
    popup_raw = {field: fields.get(field) for field in KANBAN_POPUP_FIELDS}
    for k in ['Horas', 'MATERIAL', 'CALDERERIA', 'CALDERERÍA']:
        fields.pop(k, None)

    project_name = (
        card.get('customCardId')
        or fields.get('ID personalizado de tarjeta')
        or fields.get('ID personalizado')
        or card.get('customId')
        or card.get('taskid')
    )
    if not project_name:
        return None
    client = card.get('title', '')
    due = parse_input_date(fields.get('Fecha Cliente') or fields.get('Fecha cliente'))

    def h(name):
        try:
            return int(fields.get(name, 0))
        except Exception:
            return 0

    prep = h('Horas Preparación')
    mont = h('Horas Montaje')
    sold2 = h('Horas Soldadura 2º') or h('Horas Soldadura 2°')
    sold = h('Horas Soldadura')
    pint = h('Horas Acabado')
    mont2 = h('Horas Montaje 2º') or h('Horas Montaje 2°')
    phases = {}
    auto_hours = {}
    if (
        prep <= 0
        and mont <= 0
        and sold2 <= 0
        and sold <= 0
        and pint <= 0
        and mont2 <= 0
    ):
        phases['recepcionar material'] = 1
        auto_hours['recepcionar material'] = True
    else:
        if mont:
            phases['montar'] = mont
        if sold2:
            phases['soldar 2º'] = sold2
        if pint:
            phases['pintar'] = pint
        if mont2:
            phases['montar 2º'] = mont2
        if sold:
            phases['soldar'] = sold
        if prep:
            phases['recepcionar material'] = prep

    def _bool_flag(value):
        if isinstance(value, str):
            return value.strip().lower() not in ('', '0', 'false', 'no')
        return bool(value)

    def _clean_display_value(value):
        if value is None:
            return None
        if isinstance(value, str):
            text = value.strip()
            return text or None
        if isinstance(value, bool):
            return 'Sí' if value else None
        if isinstance(value, (int, float)):
            return str(value) if value != 0 else None
        text = str(value).strip()
        return text or None

    display_fields = {}
    for field in ('LANZAMIENTO', 'MATERIAL', 'CALDERERIA', 'PINTADO'):
        cleaned = _clean_display_value(popup_raw.get(field))
        if cleaned:
            display_fields[field] = cleaned
    if _bool_flag(popup_raw.get('MECANIZADO')):
        display_fields['MECANIZADO'] = _clean_display_value(popup_raw.get('MECANIZADO')) or 'Sí'
    if _bool_flag(popup_raw.get('TRATAMIENTO')):
        display_fields['TRATAMIENTO'] = _clean_display_value(popup_raw.get('TRATAMIENTO')) or 'Sí'

    project = {
        'id': str(uuid.uuid4()),
        'name': project_name,
        'client': client,
        'start_date': local_today().isoformat(),
        'due_date': due.isoformat() if due else '',
        'color': None,
        'phases': phases,
        # Ensure each phase is explicitly set to the unplanned worker so the
        # calendar always displays the tasks as soon as the project is created.
        'assigned': {ph: UNPLANNED for ph in phases},
        'auto_hours': auto_hours,
        'image': None,
        'kanban_attachments': [],
        'kanban_display_fields': display_fields,
        'planned': False,
        'source': 'api',
    }
    return project


def _fetch_kanban_card(card_id, with_links=False):
    """Retrieve card details from Kanbanize via the REST API."""
    url = f"{KANBANIZE_BASE_URL}/api/v2/boards/{KANBANIZE_BOARD_TOKEN}/cards/{card_id}"
    if with_links:
        url += "?withLinks=1"
    req = Request(url, headers={'apikey': KANBANIZE_API_KEY})
    try:
        with urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                data = json.load(resp)
                if isinstance(data, dict):
                    return data.get('data') or data
    except Exception as e:
        print('Kanbanize API error:', e)
    return None


@app.route('/')
def home():
    """Redirect to the combined view by default."""
    return redirect(url_for('complete'))


@app.route('/calendar')
def calendar_view():
    projects = get_visible_projects()
    schedule, conflicts = schedule_projects(projects)
    today = local_today()
    worker_notes_raw = load_worker_notes()
    unplanned_raw = []
    if UNPLANNED in schedule:
        for day, tasks in schedule.pop(UNPLANNED).items():
            for t in tasks:
                item = t.copy()
                item['day'] = day
                unplanned_raw.append(item)
    groups = {}
    for item in unplanned_raw:
        pid = item['pid']
        phase = item['phase']
        part = item.get('part')
        proj = groups.setdefault(
            pid,
            {
                'project': item['project'],
                'client': item['client'],
                'material_date': item.get('material_date'),
                'due_date': item.get('due_date'),
                'phases': {},
            },
        )
        phase_key = (phase, part) if part is not None else (phase, None)
        ph = proj['phases'].setdefault(
            phase_key,
            {
                'project': item['project'],
                'client': item['client'],
                'pid': pid,
                'phase': phase,
                'part': part,
                'color': item.get('color'),
                'due_date': item.get('due_date'),
                'start_date': item.get('start_date'),
                'day': item.get('day'),
                'hours': 0,
                'late': item.get('late', False),
                'due_status': item.get('due_status'),
                'blocked': item.get('blocked', False),
                'frozen': item.get('frozen', False),
                'auto': item.get('auto', False),
            },
        )
        ph['hours'] += item.get('hours', 0)
        if item.get('day') and (ph['day'] is None or item['day'] < ph['day']):
            ph['day'] = item['day']
        if item.get('start_date') and (
            ph['start_date'] is None or item['start_date'] < ph['start_date']
        ):
            ph['start_date'] = item['start_date']
        if item.get('due_date') and (
            ph['due_date'] is None or item['due_date'] < ph['due_date']
        ):
            ph['due_date'] = item['due_date']
        if item.get('late'):
            ph['late'] = True
        if item.get('blocked'):
            ph['blocked'] = True
        if item.get('frozen'):
            ph['frozen'] = True
        if item.get('auto'):
            ph['auto'] = True
    unplanned_list = []
    for pid, data in groups.items():
        unplanned_list.append(
            {
                'pid': pid,
                'project': data['project'],
                'client': data['client'],
                'material_date': data.get('material_date'),
                'due_date': data.get('due_date'),
                'tasks': list(data['phases'].values()),
            }
        )
    visible = set(active_workers(today))
    schedule = {w: d for w, d in schedule.items() if w in visible}
    for p in projects:
        if p.get('due_date'):
            try:
                p['met'] = date.fromisoformat(p['end_date']) <= date.fromisoformat(p['due_date'])
            except ValueError:
                p['met'] = False
        else:
            p['met'] = False
    notes = load_notes()
    extra = load_extra_conflicts()
    conflicts.extend(extra)
    dismissed = load_dismissed()
    conflicts = [
        c
        for c in conflicts
        if c['key'] not in dismissed and c.get('message') != 'No se cumple la fecha de entrega'
    ]

    project_filter = request.args.get('project', '').strip()
    client_filter = request.args.get('client', '').strip()
    filter_active = bool(project_filter or client_filter)

    def matches_filters(name, client):
        project_name = (name or '').lower()
        client_name = (client or '').lower()
        if project_filter and project_filter.lower() not in project_name:
            return False
        if client_filter and client_filter.lower() not in client_name:
            return False
        return True

    if filter_active:
        for worker, days_data in schedule.items():
            for day, tasks in days_data.items():
                for t in tasks:
                    t['filter_match'] = matches_filters(t['project'], t['client'])
        for g in unplanned_list:
            match = matches_filters(g['project'], g['client'])
            g['filter_match'] = match
            for t in g['tasks']:
                t['filter_match'] = matches_filters(t['project'], t['client'])

    # Ensure started phases appear before unstarted ones within each cell
    _sort_cell_tasks(schedule)

    points = split_markers(schedule)
    start = today - timedelta(days=90)
    end = today + timedelta(days=180)
    days, cols, week_spans = build_calendar(start, end)
    hours_map = load_daily_hours()

    unplanned_list.sort(key=lambda g: g.get('material_date') or '9999-12-31')
    unplanned_with = [g for g in unplanned_list if g.get('material_date')]
    unplanned_without = [g for g in unplanned_list if not g.get('material_date')]

    note_map = {}
    for n in notes:
        note_map.setdefault(n['date'], []).append(n['description'])
    worker_note_map = {}
    for w, info in worker_notes_raw.items():
        text = info.get('text', '')
        ts = info.get('edited')
        fmt = ''
        if ts:
            try:
                fmt = datetime.fromisoformat(ts).strftime('%H:%M %d/%m')
            except ValueError:
                fmt = ''
        worker_note_map[w] = {'text': text, 'edited': fmt}
    material_status_map = compute_material_status_map(projects)

    project_map = {}
    for p in projects:
        p.setdefault('kanban_attachments', [])
        p.setdefault('kanban_display_fields', {})
        pid = p.get('id')
        project_entry = {
            **p,
            'frozen_phases': sorted({t['phase'] for t in p.get('frozen_tasks', [])}),
            'phase_sequence': list((p.get('phases') or {}).keys()),
        }
        if pid:
            project_entry['material_status'] = material_status_map.get(str(pid), 'complete')
        project_map[p['id']] = project_entry
    start_map = phase_start_map(projects)

    return render_template(
        'index.html',
        schedule=schedule,
        cols=cols,
        week_spans=week_spans,
        conflicts=conflicts,
        workers=WORKERS,
        today=today,
        project_filter=project_filter,
        client_filter=client_filter,
        filter_active=filter_active,
        notes=note_map,
        project_data=project_map,
        start_map=start_map,
        phases=PHASE_ORDER,
        hours=hours_map,
        split_points=points,
        palette=COLORS,
        unplanned_with=unplanned_with,
        unplanned_without=unplanned_without,
        worker_notes=worker_note_map,
    )


@app.route('/calendario-pedidos')
def calendar_pedidos():
    today = local_today()
    compras_raw, column_colors = load_compras_raw()
    projects = get_visible_projects()
    raw_links = attach_phase_starts(build_project_links(compras_raw), projects)
    pedidos, unconfirmed, calendar_titles = compute_pedidos_entries(
        compras_raw, column_colors, today
    )
    calendar_ids = set()
    for entries in pedidos.values():
        for item in entries:
            cid = item.get('cid')
            if cid:
                calendar_ids.add(str(cid))
    for item in unconfirmed:
        cid = item.get('cid')
        if cid:
            calendar_ids.add(str(cid))
    links_table = filter_project_links_by_titles(
        raw_links, calendar_titles, calendar_ids
    )

    info_names = sorted({
        name.strip()
        for name in (item.get('board') for item in links_table)
        if name and name.strip()
    })
    info_title = ' / '.join(info_names)


    # --- ARMAR CALENDARIO SEMANAL ---
    start = today - timedelta(weeks=3)
    start -= timedelta(days=start.weekday())
    for d in list(pedidos.keys()):
        if d < start:
            pedidos.setdefault(start, []).extend(pedidos.pop(d))

    current_month_start = date(today.year, today.month, 1)
    months_ahead = 2
    end_month = current_month_start
    for _ in range(months_ahead):
        end_month = (end_month.replace(day=28) + timedelta(days=4)).replace(day=1)
    month_end = (end_month.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)

    MONTHS = [
        'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
        'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'
    ]

    weeks = []
    current = start
    while current <= month_end:
        week = {'number': current.isocalendar()[1], 'days': []}
        for i in range(5):  # solo lunes-viernes
            day = current + timedelta(days=i)
            month_label = ''
            first_weekday = date(day.year, day.month, 1).weekday()
            if first_weekday < 5:
                if day.day == 1:
                    month_label = MONTHS[day.month - 1].capitalize()
            else:
                if day.weekday() == 0 and 1 < day.day <= 7:
                    month_label = MONTHS[day.month - 1].capitalize()
            tasks = pedidos.get(day, []) if start <= day <= month_end else []
            week['days'].append(
                {
                    'date': day,
                    'day': f"{day.day:02d}",
                    'month': month_label,
                    'tasks': tasks,
                }
            )
        weeks.append(week)
        current += timedelta(weeks=1)

    material_status_map = compute_material_status_map(projects)

    project_map = {}
    for p in projects:
        p.setdefault('kanban_attachments', [])
        p.setdefault('kanban_display_fields', {})
        entry = {
            **p,
            'frozen_phases': sorted({t['phase'] for t in p.get('frozen_tasks', [])}),
            'phase_sequence': list((p.get('phases') or {}).keys()),
        }
        pid = p.get('id')
        if pid:
            entry['material_status'] = material_status_map.get(str(pid), 'complete')
        project_map[p['id']] = entry
    start_map = phase_start_map(projects)

    return render_template(
        'calendar_pedidos.html',
        weeks=weeks,
        today=today,
        unconfirmed=unconfirmed,
        project_links=links_table,
        project_data=project_map,
        start_map=start_map,
        phases=PHASE_ORDER,
        project_info_title=info_title,
    )


@app.route('/cronologico')
def cronologico_view():
    projects = get_visible_projects()
    schedule_map, _ = schedule_projects(copy.deepcopy(projects))
    today = local_today()
    week_start = today - timedelta(days=today.weekday())
    week_days = [week_start + timedelta(days=i) for i in range(5)]

    interesting_phases = {'montar', 'soldar', 'pintar', 'mecanizar', 'tratamiento'}
    phase_entries = {}
    for worker, days in schedule_map.items():
        if worker == UNPLANNED:
            continue
        for day_str, tasks in days.items():
            try:
                day_obj = date.fromisoformat(day_str)
            except ValueError:
                continue
            for task in tasks:
                phase = task.get('phase')
                if phase not in interesting_phases:
                    continue
                key = (task.get('pid'), phase, task.get('part'), worker)
                entry = phase_entries.setdefault(
                    key,
                    {
                        'project': task.get('project'),
                        'worker': worker,
                        'phase': phase,
                        'days': set(),
                    },
                )
                entry['days'].add(day_obj)

    start_templates = {
        'montar': '{worker} inicia la fase MONTAR del proyecto {project}',
        'soldar': '{worker} inicia la fase SOLDAR del proyecto {project}',
        'pintar': '{worker} inicia la fase PINTAR del proyecto {project}',
        'mecanizar': 'Llevar {project} a mecanizar.',
        'tratamiento': 'Llevar {project} a tratamiento.',
    }
    finish_templates = {
        'montar': '{worker} termina la fase MONTAR del proyecto {project}',
        'soldar': '{worker} termina la fase SOLDAR del proyecto {project}',
        'mecanizar': 'Recepcionar {project} del mecanizado.',
        'tratamiento': 'Recepcionar {project} del tratamiento.',
    }

    events_by_day = {d.isoformat(): [] for d in week_days}
    for entry in phase_entries.values():
        days = sorted(entry['days'])
        if not days:
            continue
        start_day = days[0]
        end_day = days[-1]
        project_name = entry['project'] or 'Sin nombre'
        worker_name = entry['worker'] or UNPLANNED
        if worker_name == UNPLANNED:
            continue
        phase = entry['phase']

        start_template = start_templates.get(phase)
        day_key = start_day.isoformat()
        if start_template and day_key in events_by_day:
            events_by_day[day_key].append((0, start_template.format(worker=worker_name, project=project_name)))

        finish_template = finish_templates.get(phase)
        finish_key = end_day.isoformat()
        if finish_template and finish_key in events_by_day:
            events_by_day[finish_key].append((1, finish_template.format(worker=worker_name, project=project_name)))

    for day_key, messages in events_by_day.items():
        messages.sort(key=lambda item: (item[0], item[1]))
        deduped = []
        seen = set()
        for _, message in messages:
            if message in seen:
                continue
            seen.add(message)
            deduped.append(message)
        events_by_day[day_key] = deduped

    return render_template(
        'cronologico.html',
        week_days=week_days,
        events_by_day=events_by_day,
        today=today,
    )


@app.route('/project_links')
def project_links_api():
    today = local_today()
    compras_raw, column_colors = load_compras_raw()
    raw_links = attach_phase_starts(
        build_project_links(compras_raw), get_visible_projects()
    )
    pedidos, unconfirmed, calendar_titles = compute_pedidos_entries(
        compras_raw, column_colors, today
    )
    calendar_ids = set()
    for entries in pedidos.values():
        for item in entries:
            cid = item.get('cid')
            if cid:
                calendar_ids.add(str(cid))
    for item in unconfirmed:
        cid = item.get('cid')
        if cid:
            calendar_ids.add(str(cid))
    links = filter_project_links_by_titles(
        raw_links, calendar_titles, calendar_ids
    )
    return jsonify(links)


@app.route('/orden-carpetas')
@app.route('/pndt-verificacion')
def orden_carpetas_view():
    projects = get_visible_projects()
    project_lookup = {}
    planned_starts = {}
    project_workers = {}

    for project in projects:
        pid = project.get('id')
        if not pid:
            continue
        pid_str = str(pid)
        project_lookup[pid_str] = project
        planned_starts[pid_str] = None
        project_workers[pid_str] = set()

    scheduled_projects = copy.deepcopy(projects)
    schedule_data, _ = schedule_projects(scheduled_projects)

    for worker, days in schedule_data.items():
        for tasks in days.values():
            for task in tasks:
                pid = task.get('pid')
                if not pid:
                    continue
                pid_str = str(pid)
                project_workers.setdefault(pid_str, set())
                if worker:
                    project_workers[pid_str].add(worker)
                task_worker = task.get('worker')
                if task_worker and task_worker != worker:
                    project_workers[pid_str].add(task_worker)
                if worker == UNPLANNED or task_worker == UNPLANNED:
                    continue
                start_day = _safe_iso_date(task.get('start_time'))
                if not start_day:
                    continue
                current = planned_starts.get(pid_str)
                if current is None or start_day < current:
                    planned_starts[pid_str] = start_day
                else:
                    planned_starts.setdefault(pid_str, start_day)
    all_unplanned_projects = {}
    for pid_str, workers in project_workers.items():
        cleaned = {w for w in workers if w}
        all_unplanned_projects[pid_str] = bool(cleaned) and all(
            w == UNPLANNED for w in cleaned
        )

    project_key_map = {}
    for project in projects:
        pid = project.get('id')
        if not pid:
            continue
        pid_str = str(pid)
        name = (project.get('name') or '').strip()
        if name:
            norm = normalize_key(name)
            if norm:
                project_key_map.setdefault(norm, pid_str)
            split_name, _ = split_project_and_client(name)
            if split_name:
                norm_split = normalize_key(split_name)
                if norm_split:
                    project_key_map.setdefault(norm_split, pid_str)
            code_match = PROJECT_TITLE_PATTERN.search(name)
            if code_match:
                code_key = normalize_key(code_match.group(0))
                if code_key:
                    project_key_map.setdefault(code_key, pid_str)
        custom = (project.get('custom_card_id') or '').strip()
        if custom:
            norm_custom = normalize_key(custom)
            if norm_custom:
                project_key_map.setdefault(norm_custom, pid_str)
            code_match = PROJECT_TITLE_PATTERN.search(custom)
            if code_match:
                code_key = normalize_key(code_match.group(0))
                if code_key:
                    project_key_map.setdefault(code_key, pid_str)

    compras_raw, _ = load_compras_raw()
    links_table = attach_phase_starts(build_project_links(compras_raw), projects)

    target_column_keys = {
        normalize_key('Pdte. Verificación'),
        normalize_key('Pendiente Verificación'),
        normalize_key('Pendiente de Verificación'),
    }
    pending_rows = []
    pending_seen = set()
    montaje_keys = {normalize_key('Planificado para montaje')}
    montaje_rows = {}

    for entry in links_table:
        pid_value = entry.get('pid')
        pid_str = str(pid_value) if pid_value not in (None, '') else ''
        if not pid_str:
            for field in ('project', 'title', 'display_title', 'custom_card_id'):
                candidate = entry.get(field)
                norm_candidate = normalize_key(candidate)
                if norm_candidate and norm_candidate in project_key_map:
                    pid_str = project_key_map[norm_candidate]
                    break
        def ensure_montaje_row():
            project = project_lookup.get(pid_str)
            project_title = ''
            project_description = ''
            if project:
                project_title = (project.get('name') or '').strip()
                project_description = (project.get('client') or '').strip()
            if not project_title:
                fallback = (
                    entry.get('project')
                    or entry.get('title')
                    or entry.get('display_title')
                    or ''
                )
                project_title = fallback.strip()
            if not project_description:
                project_description = (entry.get('client') or '').strip()
            key = pid_str or normalize_key(project_title)
            if not key or key in montaje_rows:
                return
            planned_date = None
            if pid_str and not all_unplanned_projects.get(pid_str, False):
                planned_date = planned_starts.get(pid_str)
            display_date = ''
            if isinstance(planned_date, date):
                display_date = planned_date.strftime('%d/%m/%Y')
            montaje_rows[key] = {
                'project_title': project_title,
                'project_description': project_description,
                'planned_date': display_date,
                'sort_key': planned_date if isinstance(planned_date, date) else None,
                'title_key': project_title.casefold() if project_title else '',
            }

        entry_column = normalize_key(entry.get('column'))
        if entry_column in montaje_keys:
            ensure_montaje_row()

        details = entry.get('link_details') or []
        for detail in details:
            if not isinstance(detail, dict):
                continue
            column_name = detail.get('column')
            normalized_column = normalize_key(column_name)
            if normalized_column in target_column_keys:
                title = (detail.get('title') or '').strip()
                if not title:
                    fallback = (
                        entry.get('project')
                        or entry.get('title')
                        or entry.get('display_title')
                        or ''
                    )
                    title = fallback.strip()
                card_id = str(detail.get('id') or '').strip()
                dedupe_key = (card_id or normalize_key(title), pid_str)
                if dedupe_key in pending_seen:
                    continue
                pending_seen.add(dedupe_key)
                planned_date = None
                if pid_str and not all_unplanned_projects.get(pid_str, False):
                    planned_date = planned_starts.get(pid_str)
                display_date = ''
                if isinstance(planned_date, date):
                    display_date = planned_date.strftime('%d/%m/%Y')
                project = project_lookup.get(pid_str)
                project_title = ''
                project_description = ''
                if project:
                    project_title = (project.get('name') or '').strip()
                    project_description = (project.get('client') or '').strip()
                if not project_title:
                    fallback = (
                        entry.get('project')
                        or entry.get('title')
                        or entry.get('display_title')
                        or ''
                    )
                    project_title = fallback.strip()
                if not project_description:
                    project_description = (entry.get('client') or '').strip()
                pending_rows.append(
                    {
                        'title': title,
                        'project_title': project_title,
                        'project_description': project_description,
                        'planned_date': display_date,
                        'sort_key': planned_date if isinstance(planned_date, date) else None,
                        'title_key': title.casefold() if title else '',
                    }
                )
            if normalized_column in montaje_keys:
                ensure_montaje_row()

    pending_rows.sort(
        key=lambda item: (
            item['sort_key'] is None,
            item['sort_key'] or date.max,
            item['title_key'],
        )
    )
    for item in pending_rows:
        item.pop('sort_key', None)
        item.pop('title_key', None)

    montaje_list = list(montaje_rows.values())
    montaje_list.sort(
        key=lambda item: (
            item['sort_key'] is None,
            item['sort_key'] or date.max,
            item['title_key'],
        )
    )
    for item in montaje_list:
        item.pop('sort_key', None)
        item.pop('title_key', None)

    return render_template(
        'orden_carpetas.html',
        pending_rows=pending_rows,
        montaje_rows=montaje_list,
    )


def _normalize_order_code(value):
    if not value:
        return ''
    text = str(value).strip()
    match = re.search(r'OF\s*(\d+)', text, re.IGNORECASE)
    if match:
        return f"OF {match.group(1)}"
    return text


def _pick_deadline_start(project):
    candidates = [
        project.get('due_date'),
        project.get('client_date'),
        project.get('client_due_date'),
        project.get('customer_date'),
    ]
    for value in candidates:
        if not value:
            continue
        text = str(value).strip()
        if not text:
            continue
        try:
            return date.fromisoformat(text).isoformat()
        except ValueError:
            parsed = parse_input_date(text)
            if parsed:
                return parsed.isoformat()
    display_fields = project.get('kanban_display_fields') or {}
    for label in ('Fecha Cliente', 'Fecha cliente'):
        raw = display_fields.get(label)
        if not raw:
            continue
        parsed = parse_input_date(str(raw).strip())
        if parsed:
            return parsed.isoformat()
    return ''


@app.route('/gantt')
def gantt_view():
    projects = get_visible_projects()
    sched, _ = schedule_projects(copy.deepcopy(projects))
    by_pid = {}
    project_workers = {}
    for worker, days in sched.items():
        for day, tasks in days.items():
            for t in tasks:
                pid = t.get('pid')
                if not pid:
                    continue
                if worker:
                    project_workers.setdefault(pid, set()).add(worker)
                if worker == UNPLANNED:
                    continue
                by_pid.setdefault(pid, []).append(t)

    all_unplanned_projects = {
        pid: bool(workers) and all(w == UNPLANNED for w in workers)
        for pid, workers in project_workers.items()
    }

    project_map = {}
    for p in projects:
        p.setdefault('kanban_attachments', [])
        p.setdefault('kanban_display_fields', {})
        project_map[p['id']] = {
            **p,
            'frozen_phases': sorted({t['phase'] for t in p.get('frozen_tasks', [])}),
            'phase_sequence': list((p.get('phases') or {}).keys()),
            'all_phases_unplanned': all_unplanned_projects.get(p['id'], False),
        }

    start_map = phase_start_map(projects)

    gantt_projects = []
    for p in projects:
        pid = p['id']
        tasks = by_pid.get(pid, [])
        if not tasks:
            continue
        start = min(t['start_time'] for t in tasks)
        end = max(t['end_time'] for t in tasks)
        phase_map = {}
        for t in tasks:
            key = t['phase']
            start_time = t.get('start_time')
            end_time = t.get('end_time')
            entry = phase_map.get(key)
            if not entry:
                entry = {
                    'id': f"{pid}-{key}",
                    'name': key,
                    'start': start_time,
                    'end': end_time,
                    'color': t.get('color', p.get('color')),
                    'worker': t.get('worker'),
                    'segments': [],
                    '_segment_map': {},
                }
                phase_map[key] = entry
            else:
                if start_time and (not entry['start'] or start_time < entry['start']):
                    entry['start'] = start_time
                if end_time and (not entry['end'] or end_time > entry['end']):
                    entry['end'] = end_time
                if not entry.get('worker') and t.get('worker'):
                    entry['worker'] = t.get('worker')

            seg_key = t.get('part')
            if seg_key is None:
                seg_key = '__default__'
            segment_map = entry['_segment_map']
            segment = segment_map.get(seg_key)
            if not segment:
                segment = {
                    'start': start_time,
                    'end': end_time,
                    'worker': t.get('worker'),
                    'part': t.get('part'),
                }
                segment_map[seg_key] = segment
                entry['segments'].append(segment)
            else:
                if start_time and segment['start'] and start_time < segment['start']:
                    segment['start'] = start_time
                if end_time and segment['end'] and end_time > segment['end']:
                    segment['end'] = end_time
                if not segment.get('worker') and t.get('worker'):
                    segment['worker'] = t.get('worker')

        phases = []
        for entry in phase_map.values():
            segments = entry.get('segments') or []
            segments.sort(key=lambda seg: (seg.get('start') or ''))
            starts = [seg.get('start') for seg in segments if seg.get('start')]
            ends = [seg.get('end') for seg in segments if seg.get('end')]
            if starts:
                entry['start'] = min(starts)
            if ends:
                entry['end'] = max(ends)
            entry.pop('_segment_map', None)
            phases.append(entry)
        gantt_projects.append({
            'id': pid,
            'name': p['name'],
            'client': p.get('client', ''),
            'start': start,
            'end': end,
            'due_date': p.get('due_date'),
            'color': p.get('color'),
            'deadline_start': _pick_deadline_start(p),
            'phases': phases,
            'all_phases_unplanned': all_unplanned_projects.get(pid, False),
        })
    return render_template(
        'gantt.html',
        projects=json.dumps(gantt_projects),
        project_data=project_map,
        start_map=start_map,
        phases=PHASE_ORDER,
        gantt_mode='phases',
        phase_actions_enabled=True,
    )


def _safe_iso_date(value):
    if not value:
        return None
    value = str(value).strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _extract_order_title_date(title, reference_day, fallback_year):
    if not title:
        return None
    match = re.search(r"\((\d{2})/(\d{2})\)", title)
    if not match:
        return None
    try:
        day = int(match.group(1))
        month = int(match.group(2))
    except ValueError:
        return None
    year = fallback_year
    if isinstance(reference_day, date):
        year = reference_day.year
    try:
        candidate = date(year, month, day)
    except ValueError:
        return None
    if isinstance(reference_day, date):
        delta_days = (candidate - reference_day).days
        if delta_days < -183:
            try:
                candidate = date(year + 1, month, day)
            except ValueError:
                pass
        elif delta_days > 183:
            try:
                candidate = date(year - 1, month, day)
            except ValueError:
                pass
    return candidate


def _parse_order_deadline(raw_value):
    if not raw_value:
        return None
    text = str(raw_value).strip()
    if not text:
        return None
    parsed = parse_input_date(text)
    if parsed:
        return parsed
    return parse_kanban_date(text)


def _resolve_unconfirmed_schedule_day(entry, planned_end, today):
    explicit = _parse_order_deadline(entry.get('kanban_date'))
    if explicit:
        return explicit
    if isinstance(planned_end, date):
        return _subtract_business_days(planned_end, 5)
    return today


def _subtract_business_days(day, count):
    if not isinstance(day, date) or count <= 0:
        return day
    current = day
    removed = 0
    while removed < count:
        current -= timedelta(days=1)
        if current.weekday() not in WEEKEND:
            removed += 1
    return current


def _should_highlight_order(order_day, planned_start, *, window=3, today=None):
    if not isinstance(order_day, date) or not isinstance(planned_start, date):
        return False

    highlight = False
    threshold = _subtract_business_days(planned_start, window)
    if threshold <= order_day <= planned_start:
        highlight = True

    if isinstance(today, date) and planned_start <= order_day <= today:
        highlight = True

    return highlight


@app.route('/gantt-pedidos')
def gantt_orders_view():
    today = local_today()
    compras_raw, column_colors = load_compras_raw()
    pedidos, unconfirmed, _ = compute_pedidos_entries(compras_raw, column_colors, today)
    base_links = build_project_links(compras_raw)

    order_to_code = {}
    for entry in base_links:
        code = _normalize_order_code(entry.get('custom_card_id'))
        if not code:
            code = _normalize_order_code(entry.get('display_title') or entry.get('title'))
        details = entry.get('link_details') or []
        for detail in details:
            if isinstance(detail, dict):
                cid = str(detail.get('id') or '').strip()
                if cid and code:
                    order_to_code.setdefault(cid, code)
        for cid in entry.get('link_ids') or []:
            cid = str(cid or '').strip()
            if cid and code:
                order_to_code.setdefault(cid, code)

    projects = get_visible_projects()
    scheduled_projects = copy.deepcopy(projects)
    schedule_data, _ = schedule_projects(scheduled_projects)

    planned_windows = {}
    project_workers = {}

    for project in scheduled_projects:
        pid = project.get('id')
        if not pid:
            continue
        planned_windows.setdefault(pid, {'start': None, 'end': None})

    for worker, days in schedule_data.items():
        for tasks in days.values():
            for task in tasks:
                pid = task.get('pid')
                if not pid:
                    continue
                if worker:
                    project_workers.setdefault(pid, set()).add(worker)
                if worker == UNPLANNED or task.get('worker') == UNPLANNED:
                    continue
                start_day = _safe_iso_date(task.get('start_time'))
                end_day = _safe_iso_date(task.get('end_time'))
                window = planned_windows.setdefault(pid, {'start': None, 'end': None})
                if start_day and (window['start'] is None or start_day < window['start']):
                    window['start'] = start_day
                if end_day and (window['end'] is None or end_day > window['end']):
                    window['end'] = end_day

    for project in scheduled_projects:
        pid = project.get('id')
        if not pid:
            continue
        window = planned_windows.setdefault(pid, {'start': None, 'end': None})
        if window['start'] is None:
            start_day = _safe_iso_date(project.get('start_date'))
            if start_day:
                window['start'] = start_day
        if window['end'] is None:
            end_day = _safe_iso_date(project.get('end_date'))
            if end_day:
                window['end'] = end_day

    all_unplanned_projects = {
        pid: bool(workers) and all(w == UNPLANNED for w in workers)
        for pid, workers in project_workers.items()
    }

    project_map = {}
    code_to_project = {}
    for p in projects:
        p.setdefault('kanban_attachments', [])
        p.setdefault('kanban_display_fields', {})
        plan_window = planned_windows.get(p['id']) or {}
        planned_start_iso = plan_window.get('start').isoformat() if plan_window.get('start') else ''
        planned_end_iso = plan_window.get('end').isoformat() if plan_window.get('end') else ''
        project_map[p['id']] = {
            **p,
            'frozen_phases': sorted({t['phase'] for t in p.get('frozen_tasks', [])}),
            'phase_sequence': list((p.get('phases') or {}).keys()),
            'planned_start': planned_start_iso,
            'planned_end': planned_end_iso,
            'all_phases_unplanned': all_unplanned_projects.get(p['id'], False),
        }
        code = _normalize_order_code(p.get('name'))
        if code:
            code_to_project[code] = p

    for entry in unconfirmed:
        cid = str(entry.get('cid') or '').strip()
        code = _normalize_order_code(entry.get('custom_card_id'))
        if not code and cid:
            code = order_to_code.get(cid, '')
        if not code:
            code = _normalize_order_code(entry.get('project'))
        planned_end = None
        if code:
            project = code_to_project.get(code)
            if project:
                window = planned_windows.get(project['id']) or {}
                planned_end = window.get('end')
        scheduled_day = _resolve_unconfirmed_schedule_day(entry, planned_end, today)
        pedidos.setdefault(scheduled_day, []).append(entry)

    orders_by_pid = {}
    pseudo_counter = 0

    for scheduled_day, entries in pedidos.items():
        if not isinstance(scheduled_day, date):
            continue
        day_iso = scheduled_day.isoformat()
        for entry in entries:
            cid = str(entry.get('cid') or '').strip()
            code = _normalize_order_code(entry.get('custom_card_id'))
            if not code and cid:
                code = order_to_code.get(cid, '')
            if not code:
                code = _normalize_order_code(entry.get('project'))

            project = code_to_project.get(code)
            entry_color = entry.get('color')
            if project:
                pid = project['id']
                name = project.get('name') or code or entry.get('project') or 'Pedido'
                client = project.get('client', '')
                color = project.get('color') or entry_color
                due = project.get('due_date')
                deadline_start = _pick_deadline_start(project)
            else:
                pseudo_counter += 1
                pid = f"pedido-{pseudo_counter}"
                name = code or entry.get('project') or f"Pedido {pseudo_counter}"
                client = entry.get('client') or ''
                color = entry_color or '#6c9ec1'
                due = ''
                deadline_start = ''
                if pid not in project_map:
                    project_map[pid] = {
                        'id': pid,
                        'name': name,
                        'client': client,
                        'kanban_display_fields': {},
                        'kanban_attachments': [],
                        'phase_sequence': [],
                        'frozen_phases': [],
                        'color': color,
                        'due_date': due,
                        'deadline_start': deadline_start,
                        'observations': '',
                        'planned_start': '',
                        'planned_end': '',
                    }

            plan_window = planned_windows.get(pid)
            planned_start_date = plan_window.get('start') if plan_window else None
            planned_end_date = plan_window.get('end') if plan_window else None
            planned_start_iso = planned_start_date.isoformat() if planned_start_date else ''
            planned_end_iso = planned_end_date.isoformat() if planned_end_date else ''

            proj_entry = orders_by_pid.setdefault(pid, {
                'id': pid,
                'name': name,
                'client': client,
                'start': planned_start_iso or day_iso,
                'end': planned_end_iso or day_iso,
                'due_date': due,
                'color': color or '#6c9ec1',
                'deadline_start': deadline_start,
                'planned_start': planned_start_iso,
                'planned_end': planned_end_iso,
                'order_dates': [],
                'phases': [],
                'all_phases_unplanned': all_unplanned_projects.get(pid, False),
            })

            proj_entry['all_phases_unplanned'] = all_unplanned_projects.get(pid, False)

            order_column = (entry.get('column') or '').strip()

            effective_day = scheduled_day
            title_date = _extract_order_title_date(entry.get('project'), scheduled_day, today.year)
            if title_date:
                effective_day = title_date
            order_column_key = normalize_key(order_column)
            if (
                planned_end_date
                and order_column_key in PEDIDOS_OFFSET_TO_PLAN_END_KEYS
            ):
                effective_day = _subtract_business_days(planned_end_date, 5)
            effective_iso = effective_day.isoformat()

            proj_entry['order_dates'].append(effective_iso)

            should_flag_order = False
            if planned_start_date and order_column not in {'Tratamiento', 'Tratamiento final'}:
                should_flag_order = _should_highlight_order(
                    effective_day,
                    planned_start_date,
                    today=today,
                )

            phase = {
                'id': f"{pid}-pedido-{cid or len(proj_entry['phases'])}",
                'name': entry.get('project') or 'Pedido',
                'start': effective_iso,
                'end': effective_iso,
                'color': entry.get('color') or color,
                'worker': order_column,
                'order_column': order_column,
                'order_lane': entry.get('lane') or '',
                'order_client': entry.get('client') or '',
                'order_code': code,
                'order_cid': cid,
                'order_prev_date': entry.get('prev_date') or '',
                'order_date': effective_iso,
                'order_kanban_date': entry.get('kanban_date') or '',
                'order_highlight': should_flag_order,
            }
            proj_entry['phases'].append(phase)

            if planned_start_iso:
                proj_entry['start'] = planned_start_iso
                proj_entry['planned_start'] = planned_start_iso
            if planned_end_iso:
                proj_entry['end'] = planned_end_iso
                proj_entry['planned_end'] = planned_end_iso

    final_projects = []
    for pid, proj_entry in orders_by_pid.items():
        order_dates = sorted(d for d in proj_entry.pop('order_dates', []) if d)
        plan_window = planned_windows.get(pid)
        planned_start_date = plan_window.get('start') if plan_window else None
        planned_end_date = plan_window.get('end') if plan_window else None
        if planned_start_date:
            planned_start_iso = planned_start_date.isoformat()
            proj_entry['planned_start'] = planned_start_iso
            proj_entry['start'] = planned_start_iso
        else:
            if order_dates:
                proj_entry['start'] = order_dates[0]
                proj_entry['planned_start'] = order_dates[0]
            else:
                proj_entry['planned_start'] = proj_entry.get('planned_start') or proj_entry.get('start', '')
                proj_entry['start'] = proj_entry['planned_start']
        if planned_end_date:
            planned_end_iso = planned_end_date.isoformat()
            proj_entry['planned_end'] = planned_end_iso
            proj_entry['end'] = planned_end_iso
        else:
            if order_dates:
                proj_entry['end'] = order_dates[-1]
                proj_entry['planned_end'] = order_dates[-1]
            else:
                proj_entry['planned_end'] = proj_entry.get('planned_end') or proj_entry.get('end', proj_entry['start'])
                proj_entry['end'] = proj_entry['planned_end']
        if pid in project_map:
            project_map[pid]['planned_start'] = proj_entry['planned_start']
            project_map[pid]['planned_end'] = proj_entry['planned_end']
            project_map[pid]['all_phases_unplanned'] = all_unplanned_projects.get(pid, False)
        proj_entry['phases'].sort(key=lambda ph: ph.get('start') or '')
        final_projects.append(proj_entry)

    gantt_projects = sorted(final_projects, key=lambda item: item.get('start') or item.get('planned_start') or '9999-12-31')

    return render_template(
        'gantt.html',
        projects=json.dumps(gantt_projects),
        project_data=project_map,
        start_map={},
        phases=PHASE_ORDER,
        gantt_mode='orders',
        phase_actions_enabled=False,
    )

@app.route('/projects')
def project_list():
    projects = get_visible_projects()
    # Compute deadlines to show whether each project meets its due date
    proj_copy = copy.deepcopy(projects)
    schedule_projects(proj_copy)
    end_dates = {p['id']: p['end_date'] for p in proj_copy}
    for p in projects:
        if p['id'] in end_dates:
            p['end_date'] = end_dates[p['id']]
            if p.get('due_date'):
                try:
                    p['met'] = date.fromisoformat(p['end_date']) <= date.fromisoformat(p['due_date'])
                except ValueError:
                    p['met'] = False
            else:
                p['met'] = False
        else:
            p['met'] = False
    project_filter = request.args.get('project', '').strip()
    client_filter = request.args.get('client', '').strip()
    sort_option = request.args.get('sort', 'created')

    orig_order = {p['id']: idx for idx, p in enumerate(projects)}

    if project_filter or client_filter:
        projects = [
            p for p in projects
            if (not project_filter or project_filter.lower() in p['name'].lower())
            and (not client_filter or client_filter.lower() in p['client'].lower())
        ]

    if sort_option == 'name':
        projects.sort(key=lambda p: p['name'].lower())
    else:
        projects.sort(key=lambda p: orig_order[p['id']], reverse=True)
    start_map = phase_start_map(projects)
    hours_map = load_daily_hours()
    projects = expand_for_display(projects)
    return render_template(
        'projects.html',
        projects=projects,
        phases=PHASE_ORDER,
        all_workers=active_workers(),
        project_filter=project_filter,
        client_filter=client_filter,
        sort_option=sort_option,
        start_map=start_map,
        hours=hours_map,
        palette=COLORS,
    )


@app.route('/add', methods=['GET', 'POST'])
def add_project():
    if request.method == 'POST':
        clear_prefill_project()
        data = request.form
        file = request.files.get('image')
        image_path = None
        if file and file.filename:
            ext = os.path.splitext(secure_filename(file.filename))[1]
            fname = f"{uuid.uuid4()}{ext}"
            save_path = os.path.join(UPLOAD_FOLDER, fname)
            file.save(save_path)
            image_path = f"uploads/{fname}"
        projects = get_projects()
        color = COLORS[len(projects) % len(COLORS)]
        due = parse_input_date(data['due_date'])
        project = {
            'id': str(uuid.uuid4()),
            'name': data['name'],
            'client': data['client'],
            'start_date': local_today().isoformat(),
            'due_date': due.isoformat() if due else '',
            'material_confirmed_date': '',
            'color': color,
            'phases': {},
            'assigned': {},
            'image': image_path,
            'kanban_attachments': [],
            'planned': False,
            'source': 'manual',
        }
        for phase in PHASE_ORDER:
            value_h = data.get(phase)
            value_d = data.get(f"{phase}_days")
            if phase == 'pedidos':
                if value_h:
                    val = parse_input_date(value_h)
                    if val:
                        project['phases'][phase] = val.isoformat()
                        project['assigned'][phase] = UNPLANNED
            else:
                hours = 0
                if value_h:
                    try:
                        hours += int(value_h)
                    except ValueError:
                        pass
                if value_d:
                    try:
                        hours += int(value_d) * HOURS_PER_DAY
                    except ValueError:
                        pass
                if hours:
                    project['phases'][phase] = hours
                    project['assigned'][phase] = UNPLANNED
        projects.append(project)
        save_projects(projects)
        return redirect(url_for('calendar_view', highlight=project['id']))
    prefill = load_prefill_project()
    return render_template(
        'add_project.html',
        phases=PHASE_ORDER,
        today=local_today().isoformat(),
        prefill=prefill,
    )


@app.route('/add_note', methods=['POST'])
def add_note():
    """Add a note with a unique id."""
    notes = load_notes()
    ndate = parse_input_date(request.form['date'])
    notes.append({
        'id': str(uuid.uuid4()),
        'description': request.form['description'],
        'date': ndate.isoformat() if ndate else '',
    })
    save_notes(notes)
    next_url = request.form.get('next') or url_for('complete')
    return redirect(next_url)


@app.route('/notes')
def note_list():
    notes = load_notes()
    return render_template('notes.html', notes=notes)


@app.route('/delete_note/<nid>', methods=['POST'])
def delete_note(nid):
    notes = load_notes()
    notes = [n for n in notes if n.get('id') != nid]
    save_notes(notes)
    next_url = request.form.get('next') or url_for('note_list')
    return redirect(next_url)


@app.route('/update_worker_note', methods=['POST'])
def update_worker_note():
    data = request.get_json() or {}
    worker = data.get('worker')
    text = data.get('text', '')
    if not worker:
        return jsonify({'error': 'Falta recurso'}), 400
    notes = load_worker_notes()
    notes[worker] = {
        'text': text,
        'edited': local_now().isoformat(timespec='minutes'),
    }
    save_worker_notes(notes)
    dt = datetime.fromisoformat(notes[worker]['edited'])
    return jsonify({'edited': dt.strftime('%H:%M %d/%m')})


@app.route('/update_pedido_date', methods=['POST'])
def update_pedido_date():
    data = request.get_json() or {}
    cid = data.get('cid')
    date_str = data.get('date')
    if not cid:
        return '', 400
    if date_str:
        try:
            d = date.fromisoformat(date_str)
        except Exception:
            return '', 400
        stored = f"{d.day:02d}/{d.month:02d}"
    else:
        stored = None
    cards = load_kanban_cards()
    cid = str(cid)
    updated = False
    for entry in cards:
        card = entry.get('card') or {}
        existing = card.get('taskid') or card.get('cardId') or card.get('id')
        if str(existing) == cid:
            if stored is not None:
                entry['stored_title_date'] = stored
                entry.pop('previous_title_date', None)
            else:
                prev = entry.get('stored_title_date')
                if not prev:
                    title = (card.get('title') or '').strip()
                    m = re.search(r"\((\d{2})/(\d{2})\)", title)
                    if m:
                        prev = f"{int(m.group(1)):02d}/{int(m.group(2)):02d}"
                    else:
                        d_dead = parse_kanban_date(card.get('deadline'))
                        if d_dead:
                            prev = f"{d_dead.day:02d}/{d_dead.month:02d}"
                entry['previous_title_date'] = prev
                entry['stored_title_date'] = None
                card['deadline'] = None
            updated = True
            break
    if updated:
        save_kanban_cards(cards)
        broadcast_event({'type': 'kanban_update'})
        return jsonify({'stored_date': stored})
    return '', 404


@app.route('/observaciones')
def observation_list():
    projects = [p for p in get_visible_projects() if p.get('observations')]
    return render_template('observations.html', projects=projects)


@app.route('/vacations', methods=['GET', 'POST'])
def vacation_list():
    vacations = load_vacations()
    if request.method == 'POST':
        start = parse_input_date(request.form['start'])
        end = parse_input_date(request.form['end'])
        vacations.append({
            'id': str(uuid.uuid4()),
            'worker': request.form['worker'],
            'start': start.isoformat() if start else '',
            'end': end.isoformat() if end else '',
        })
        save_vacations(vacations)
        return redirect(url_for('vacation_list'))
    return render_template('vacations.html', vacations=vacations, workers=active_workers(), today=local_today().isoformat())


@app.route('/delete_vacation/<vid>', methods=['POST'])
def delete_vacation(vid):
    vacations = load_vacations()
    vacations = [v for v in vacations if v.get('id') != vid]
    save_vacations(vacations)
    return redirect(url_for('vacation_list'))


@app.route('/remove_vacation', methods=['POST'])
def remove_vacation():
    worker = request.form['worker']
    day = date.fromisoformat(request.form['date'])
    vacations = load_vacations()
    new_list = []
    for v in vacations:
        if v['worker'] != worker:
            new_list.append(v)
            continue
        start = date.fromisoformat(v['start'])
        end = date.fromisoformat(v['end'])
        if day < start or day > end:
            new_list.append(v)
            continue
        if start == end == day:
            continue
        if start == day:
            v['start'] = (day + timedelta(days=1)).isoformat()
            new_list.append(v)
        elif end == day:
            v['end'] = (day - timedelta(days=1)).isoformat()
            new_list.append(v)
        else:
            before = v.copy()
            after = v.copy()
            before['end'] = (day - timedelta(days=1)).isoformat()
            after['start'] = (day + timedelta(days=1)).isoformat()
            before['id'] = str(uuid.uuid4())
            after['id'] = str(uuid.uuid4())
            new_list.extend([before, after])
    save_vacations(new_list)
    return ('', 204)


@app.route('/resources', methods=['GET', 'POST'])
def resources():
    workers = [w for w in WORKERS.keys() if w != UNPLANNED]
    inactive = set(load_inactive_workers())
    worker_overrides = load_worker_hours()
    if request.method == 'POST':
        if 'add_worker' in request.form:
            new_worker = request.form.get('new_worker', '').strip()
            if new_worker and new_worker not in WORKERS:
                _schedule_mod.add_worker(new_worker)
            return redirect(url_for('resources'))
        active = request.form.getlist('worker')
        inactive = [w for w in workers if w not in active]
        save_inactive_workers(inactive)
        order = request.form.getlist('order')
        if order:
            set_worker_order(order)
        hours_modified = False
        for key, changed in request.form.items():
            if not key.startswith('hours_changed__'):
                continue
            if changed != '1':
                continue
            idx = key.split('__', 1)[-1]
            worker = request.form.get(f'hours_worker__{idx}')
            if not worker:
                continue
            value = request.form.get(f'hours__{idx}', '').strip()
            if value == 'inf' or not value:
                if worker in worker_overrides:
                    worker_overrides.pop(worker, None)
                    hours_modified = True
                continue
            try:
                hours_val = int(value)
            except ValueError:
                continue
            if 1 <= hours_val <= 12:
                if worker_overrides.get(worker) != hours_val:
                    worker_overrides[worker] = hours_val
                    hours_modified = True
        if hours_modified:
            save_worker_hours(worker_overrides)
        get_projects()
        return redirect(url_for('resources'))
    worker_limits = {}
    for w in workers:
        limit = HOURS_LIMITS.get(w)
        if isinstance(limit, (int, float)) and limit == float('inf'):
            worker_limits[w] = 'inf'
        elif isinstance(limit, (int, float)):
            worker_limits[w] = int(limit)
        else:
            worker_limits[w] = HOURS_PER_DAY
    hour_options = list(range(1, 13))
    return render_template(
        'resources.html',
        workers=workers,
        inactive=inactive,
        worker_limits=worker_limits,
        hour_options=hour_options,
    )


@app.route('/complete')
def complete():
    projects = get_visible_projects()
    schedule, conflicts = schedule_projects(projects)
    today = local_today()
    worker_notes_raw = load_worker_notes()
    visible = set(active_workers(today))
    unplanned_raw = []
    if UNPLANNED in schedule:
        for day, tasks in schedule.pop(UNPLANNED).items():
            for t in tasks:
                item = t.copy()
                item['day'] = day
                unplanned_raw.append(item)
    groups = {}
    for item in unplanned_raw:
        pid = item['pid']
        phase = item['phase']
        part = item.get('part')
        proj = groups.setdefault(
            pid,
            {
                'project': item['project'],
                'client': item['client'],
                'material_date': item.get('material_date'),
                'due_date': item.get('due_date'),
                'phases': {},
            },
        )
        phase_key = (phase, part) if part is not None else (phase, None)
        ph = proj['phases'].setdefault(
            phase_key,
            {
                'project': item['project'],
                'client': item['client'],
                'pid': pid,
                'phase': phase,
                'part': part,
                'color': item.get('color'),
                'due_date': item.get('due_date'),
                'start_date': item.get('start_date'),
                'day': item.get('day'),
                'hours': 0,
                'late': item.get('late', False),
                'due_status': item.get('due_status'),
                'blocked': item.get('blocked', False),
                'frozen': item.get('frozen', False),
                'auto': item.get('auto', False),
            },
        )
        ph['hours'] += item.get('hours', 0)
        if item.get('day') and (ph['day'] is None or item['day'] < ph['day']):
            ph['day'] = item['day']
        if item.get('start_date') and (
            ph['start_date'] is None or item['start_date'] < ph['start_date']
        ):
            ph['start_date'] = item['start_date']
        if item.get('due_date') and (
            ph['due_date'] is None or item['due_date'] < ph['due_date']
        ):
            ph['due_date'] = item['due_date']
        if item.get('late'):
            ph['late'] = True
        if item.get('blocked'):
            ph['blocked'] = True
        if item.get('frozen'):
            ph['frozen'] = True
        if item.get('auto'):
            ph['auto'] = True
    unplanned_list = []
    for pid, data in groups.items():
        unplanned_list.append(
            {
                'pid': pid,
                'project': data['project'],
                'client': data['client'],
                'material_date': data.get('material_date'),
                'due_date': data.get('due_date'),
                'tasks': list(data['phases'].values()),
            }
        )
    schedule = {w: d for w, d in schedule.items() if w in visible}
    for p in projects:
        if p.get('due_date'):
            try:
                p['met'] = date.fromisoformat(p['end_date']) <= date.fromisoformat(p['due_date'])
            except ValueError:
                p['met'] = False
        else:
            p['met'] = False
    notes = load_notes()
    extra = load_extra_conflicts()
    conflicts.extend(extra)
    dismissed = load_dismissed()
    conflicts = [
        c
        for c in conflicts
        if c['key'] not in dismissed and c.get('message') != 'No se cumple la fecha de entrega'
    ]

    sort_option = request.args.get('sort', 'created')
    orig_order = {p['id']: idx for idx, p in enumerate(projects)}

    project_filter = request.args.get('project', '').strip()
    client_filter = request.args.get('client', '').strip()
    filter_active = bool(project_filter or client_filter)

    def matches_filters(name, client):
        project_name = (name or '').lower()
        client_name = (client or '').lower()
        if project_filter and project_filter.lower() not in project_name:
            return False
        if client_filter and client_filter.lower() not in client_name:
            return False
        return True

    if filter_active:
        for worker, days_data in schedule.items():
            for day, tasks in days_data.items():
                for t in tasks:
                    t['filter_match'] = matches_filters(t['project'], t['client'])
        filtered_projects = [
            p
            for p in projects
            if matches_filters(p['name'], p['client'])
        ]
        for g in unplanned_list:
            match = matches_filters(g['project'], g['client'])
            g['filter_match'] = match
            for t in g['tasks']:
                t['filter_match'] = matches_filters(t['project'], t['client'])
    else:
        filtered_projects = projects

    # Order phases within each day: started ones first
    _sort_cell_tasks(schedule)

    if sort_option == 'name':
        filtered_projects.sort(key=lambda p: p['name'].lower())
    else:
        filtered_projects.sort(key=lambda p: orig_order[p['id']], reverse=True)

    filtered_projects = expand_for_display(filtered_projects)

    unplanned_list.sort(key=lambda g: g.get('material_date') or '9999-12-31')
    unplanned_with = [g for g in unplanned_list if g.get('material_date')]
    unplanned_without = [g for g in unplanned_list if not g.get('material_date')]

    points = split_markers(schedule)

    today = local_today()
    start = today - timedelta(days=90)
    end = today + timedelta(days=180)
    days, cols, week_spans = build_calendar(start, end)
    hours_map = load_daily_hours()
    note_map = {}
    for n in notes:
        note_map.setdefault(n['date'], []).append(n['description'])
    worker_note_map = {}
    for w, info in worker_notes_raw.items():
        text = info.get('text', '')
        ts = info.get('edited')
        fmt = ''
        if ts:
            try:
                fmt = datetime.fromisoformat(ts).strftime('%H:%M %d/%m')
            except ValueError:
                fmt = ''
        worker_note_map[w] = {'text': text, 'edited': fmt}
    material_status_map = compute_material_status_map(projects)

    project_map = {}
    for p in projects:
        p.setdefault('kanban_attachments', [])
        p.setdefault('kanban_display_fields', {})
        entry = {
            **p,
            'frozen_phases': sorted({t['phase'] for t in p.get('frozen_tasks', [])}),
            'phase_sequence': list((p.get('phases') or {}).keys()),
        }
        pid = p.get('id')
        if pid:
            entry['material_status'] = material_status_map.get(str(pid), 'complete')
        project_map[p['id']] = entry
    start_map = phase_start_map(projects)

    return render_template(
        'complete.html',
        schedule=schedule,
        cols=cols,
        week_spans=week_spans,
        conflicts=conflicts,
        workers=WORKERS,
        project_filter=project_filter,
        client_filter=client_filter,
        filter_active=filter_active,
        projects=filtered_projects,
        sort_option=sort_option,
        today=today,
        phases=PHASE_ORDER,
        all_workers=active_workers(today),
        notes=note_map,
        project_data=project_map,
        start_map=start_map,
        hours=hours_map,
        split_points=points,
        palette=COLORS,
        unplanned_with=unplanned_with,
        unplanned_without=unplanned_without,
        worker_notes=worker_note_map,
    )



@app.route('/update_worker/<pid>/<phase>', methods=['POST'])
def update_worker(pid, phase):
    projects = get_projects()
    for p in projects:
        if p['id'] == pid:
            worker = request.form['worker']
            if worker in set(load_inactive_workers()):
                worker = UNPLANNED
            p.setdefault('assigned', {})[phase] = worker
            break
    save_projects(projects)
    next_url = request.form.get('next') or request.args.get('next') or url_for('project_list')
    return redirect(next_url)


@app.route('/update_phase_start', methods=['POST'])
def update_phase_start():
    data = request.get_json() or request.form
    pid = data.get('pid')
    phase = data.get('phase')
    date_str = data.get('date')
    next_url = data.get('next') or request.args.get('next') or url_for('project_list')
    if not pid or not phase or not date_str:
        return jsonify({'error': 'Datos incompletos'}), 400
    new_date = parse_input_date(date_str)
    if not new_date:
        return jsonify({'error': 'Fecha inválida'}), 400
    if new_date.weekday() in WEEKEND:
        return jsonify({'error': 'No se puede iniciar en fin de semana'}), 400
    if new_date < MIN_DATE or new_date > MAX_DATE:
        return jsonify({'error': 'Fecha fuera de rango'}), 400
    projects = get_projects()
    mapping = compute_schedule_map(projects)
    tasks = [t for t in mapping.get(pid, []) if t[2] == phase]
    if not tasks:
        return jsonify({'error': 'Fase no encontrada'}), 404
    proj = next((p for p in projects if p['id'] == pid), None)
    base = date.fromisoformat(proj['start_date'])
    offset = (date.fromisoformat(tasks[0][1]) - base).days
    proj['start_date'] = (new_date - timedelta(days=offset)).isoformat()
    if proj.get('segment_starts'):
        proj['segment_starts'].pop(phase, None)
    temp = copy.deepcopy(projects)
    new_map = compute_schedule_map(temp)
    new_tasks = [t for t in new_map.get(pid, []) if t[2] == phase]
    if not new_tasks or date.fromisoformat(new_tasks[0][1]) != new_date:
        return jsonify({'error': 'No se puede asignar esa fecha'}), 400
    save_projects(temp)
    if request.is_json:
        return jsonify({'date': new_tasks[0][1], 'pid': pid, 'phase': phase})
    return redirect(next_url)


@app.route('/update_due_date', methods=['POST'])
def update_due_date():
    """Modify a project's deadline."""
    data = request.get_json() or request.form
    pid = data.get('pid')
    date_str = data.get('due_date')
    next_url = data.get('next') or request.args.get('next') or url_for('project_list')
    if not pid or not date_str:
        return jsonify({'error': 'Datos incompletos'}), 400
    new_date = parse_input_date(date_str)
    if not new_date:
        return jsonify({'error': 'Fecha inválida'}), 400
    if new_date < MIN_DATE or new_date > MAX_DATE:
        return jsonify({'error': 'Fecha fuera de rango'}), 400
    projects = get_projects()
    proj = next((p for p in projects if p['id'] == pid), None)
    if not proj:
        return jsonify({'error': 'Proyecto no encontrado'}), 404
    proj['due_date'] = new_date.isoformat()
    proj['due_confirmed'] = True
    proj['due_warning'] = True
    save_projects(projects)
    if request.is_json:
        return '', 204
    return redirect(next_url)


@app.route('/clear_deadline', methods=['POST'])
def clear_deadline():
    data = request.get_json() or {}
    pid = data.get('pid')
    if not pid:
        return '', 400
    projects = load_projects()
    for p in projects:
        if p['id'] == pid:
            p['due_warning'] = False
            save_projects(projects)
            break
    return '', 204


@app.route('/update_start_date', methods=['POST'])
def update_start_date():
    """Modify a project's start date."""
    data = request.get_json() or request.form
    pid = data.get('pid')
    date_str = data.get('start_date') or data.get('date')
    next_url = data.get('next') or request.args.get('next') or url_for('project_list')
    if not pid or not date_str:
        return jsonify({'error': 'Datos incompletos'}), 400
    new_date = parse_input_date(date_str)
    if not new_date:
        return jsonify({'error': 'Fecha inválida'}), 400
    if new_date < MIN_DATE or new_date > MAX_DATE:
        return jsonify({'error': 'Fecha fuera de rango'}), 400
    projects = get_projects()
    proj = next((p for p in projects if p['id'] == pid), None)
    if not proj:
        return jsonify({'error': 'Proyecto no encontrado'}), 404
    proj['start_date'] = new_date.isoformat()
    save_projects(projects)
    if request.is_json:
        return '', 204
    return redirect(next_url)


@app.route('/update_phase_hours', methods=['POST'])
def update_phase_hours():
    """Modify hours for a specific phase."""
    data = request.get_json() or request.form
    pid = data.get('pid')
    phase = data.get('phase')
    hours_val = data.get('hours')
    next_url = data.get('next') or request.args.get('next') or url_for('project_list')
    if not pid or not phase or hours_val is None:
        return jsonify({'error': 'Datos incompletos'}), 400
    try:
        hours = int(hours_val)
    except Exception:
        return jsonify({'error': 'Horas inválidas'}), 400
    projects = get_projects()
    proj = next((p for p in projects if p['id'] == pid), None)
    if not proj:
        return jsonify({'error': 'Proyecto no encontrado'}), 404
    proj.setdefault('phases', {})
    if hours <= 0:
        if phase in proj['phases']:
            proj['phases'].pop(phase, None)
            if proj.get('assigned'):
                proj['assigned'].pop(phase, None)
            if proj.get('segment_starts'):
                proj['segment_starts'].pop(phase, None)
                if not proj['segment_starts']:
                    proj.pop('segment_starts')
            if proj.get('segment_workers'):
                proj['segment_workers'].pop(phase, None)
                if not proj['segment_workers']:
                    proj.pop('segment_workers')
            if not proj.get('phases'):
                remove_project_and_preserve_schedule(projects, pid)
                if request.is_json:
                    return '', 204
                return redirect(next_url)
            proj['frozen_tasks'] = [t for t in proj.get('frozen_tasks', []) if t['phase'] != phase]
    else:
        prev_val = proj['phases'].get(phase)
        was_list = isinstance(prev_val, list)
        prev_total = (
            sum(map(int, prev_val)) if isinstance(prev_val, list)
            else int(prev_val or 0)
        )
        proj['phases'][phase] = hours
        assigned = proj.setdefault('assigned', {})
        if prev_total <= 0:
            assigned[phase] = UNPLANNED
        else:
            assigned.setdefault(phase, UNPLANNED)
        if was_list:
            if proj.get('segment_starts'):
                proj['segment_starts'].pop(phase, None)
                if not proj['segment_starts']:
                    proj.pop('segment_starts')
            if proj.get('segment_workers'):
                proj['segment_workers'].pop(phase, None)
                if not proj['segment_workers']:
                    proj.pop('segment_workers')
    proj['frozen_tasks'] = [t for t in proj.get('frozen_tasks', []) if t['phase'] != phase]
    schedule_projects(projects)
    save_projects(projects)
    if request.is_json:
        return '', 204
    return redirect(next_url)

@app.route('/update_project_row', methods=['POST'])
def update_project_row():
    """Apply multiple field changes for a project in one request."""
    data = request.get_json() or {}
    pid = data.get('pid')
    if not pid:
        return jsonify({'error': 'Datos incompletos'}), 400
    projects = get_projects()
    proj = next((p for p in projects if p['id'] == pid), None)
    if not proj:
        return jsonify({'error': 'Proyecto no encontrado'}), 404

    modified = set()

    if 'start_date' in data:
        sd = parse_input_date(data['start_date'])
        if sd:
            proj['start_date'] = sd.isoformat()
    if 'due_date' in data:
        dd = parse_input_date(data['due_date'])
        proj['due_date'] = dd.isoformat() if dd else ''
    if 'client' in data:
        proj['client'] = data['client']
    if 'material_confirmed_date' in data:
        md = parse_input_date(data['material_confirmed_date'])
        proj['material_confirmed_date'] = md.isoformat() if md else ''
    if 'color' in data:
        proj['color'] = data['color']

    for ph, val in (data.get('phases') or {}).items():
        try:
            hours = int(val)
        except Exception:
            continue
        if hours <= 0:
            if ph in proj.get('phases', {}):
                proj['phases'].pop(ph, None)
                if proj.get('assigned'):
                    proj['assigned'].pop(ph, None)
                if proj.get('segment_starts'):
                    proj['segment_starts'].pop(ph, None)
                    if not proj['segment_starts']:
                        proj.pop('segment_starts')
                if proj.get('segment_workers'):
                    proj['segment_workers'].pop(ph, None)
                    if not proj['segment_workers']:
                        proj.pop('segment_workers')
                modified.add(ph)
            continue
        proj.setdefault('phases', {})
        prev = proj['phases'].get(ph)
        prev_total = (
            sum(map(int, prev)) if isinstance(prev, list)
            else int(prev) if prev is not None else None
        )
        was_list = isinstance(prev, list)
        proj['phases'][ph] = hours
        assigned = proj.setdefault('assigned', {})
        if prev_total in (None, 0):
            assigned[ph] = UNPLANNED
        else:
            assigned.setdefault(ph, UNPLANNED)
        if was_list:
            if proj.get('segment_starts'):
                proj['segment_starts'].pop(ph, None)
                if not proj['segment_starts']:
                    proj.pop('segment_starts')
            if proj.get('segment_workers'):
                proj['segment_workers'].pop(ph, None)
                if not proj['segment_workers']:
                    proj.pop('segment_workers')
        modified.add(ph)

    if data.get('phase_starts'):
        seg = proj.setdefault('segment_starts', {})
        for ph, d in data['phase_starts'].items():
            val = parse_input_date(d)
            if val:
                seg[ph] = [val.isoformat()]
                modified.add(ph)

    if data.get('workers'):
        ass = proj.setdefault('assigned', {})
        inactive = set(load_inactive_workers())
        for ph, w in data['workers'].items():
            ass[ph] = w if w not in inactive else UNPLANNED
            modified.add(ph)

    if not proj.get('phases'):
        remove_project_and_preserve_schedule(projects, pid)
        return jsonify({'status': 'ok'})

    if modified:
        proj['frozen_tasks'] = [t for t in proj.get('frozen_tasks', []) if t['phase'] not in modified]

    schedule_projects(projects)
    save_projects(projects)
    return jsonify({'status': 'ok'})


@app.route('/update_observations/<pid>', methods=['POST'])
def update_observations(pid):
    data = request.get_json() or {}
    projects = get_projects()
    for p in projects:
        if p['id'] == pid:
            p['observations'] = data.get('observations', '')
            save_projects(projects)
            return jsonify({'status': 'ok'})
    return jsonify({'error': 'Proyecto no encontrado'}), 404


@app.route('/update_image/<pid>', methods=['POST'])
def update_image(pid):
    """Attach or replace a project's image file."""
    projects = get_projects()
    proj = next((p for p in projects if p['id'] == pid), None)
    if not proj:
        return jsonify({'error': 'Proyecto no encontrado'}), 404
    file = request.files.get('image')
    next_url = request.form.get('next') or request.args.get('next') or url_for('project_list')
    if file and file.filename:
        ext = os.path.splitext(secure_filename(file.filename))[1]
        fname = f"{uuid.uuid4()}{ext}"
        save_path = os.path.join(UPLOAD_FOLDER, fname)
        file.save(save_path)
        previous_image = proj.get('image')
        proj['image'] = f"uploads/{fname}"
        if previous_image and previous_image != proj['image']:
            _remove_upload_file(previous_image)
        prune_orphan_uploads(projects)
        save_projects(projects)
    if request.is_json:
        return '', 204
    return redirect(next_url)


@app.route('/update_hours', methods=['POST'])
def update_hours():
    """Set working hours for a specific day (1-9)."""
    data = request.get_json() or request.form
    day = data.get('date')
    val = data.get('hours')
    try:
        hours = int(val)
    except Exception:
        return jsonify({'error': 'Horas invalidas'}), 400
    if not day or hours < 1 or hours > 9:
        return jsonify({'error': 'Datos invalidos'}), 400
    hours_map = load_daily_hours()
    if hours == HOURS_PER_DAY:
        hours_map.pop(day, None)
    else:
        hours_map[day] = hours
    save_daily_hours(hours_map)
    if request.is_json:
        return '', 204
    return redirect(request.referrer or url_for('calendar_view'))

@app.route('/delete_phase', methods=['POST'])
def delete_phase():
    data = request.get_json() or request.form
    pid = data.get('pid')
    phase = data.get('phase')
    if not pid or not phase:
        return '', 400
    projects = get_projects()
    for p in projects:
        if p['id'] == pid:
            if phase in p.get('phases', {}):
                p['phases'].pop(phase, None)
                if p.get('assigned'):
                    p['assigned'].pop(phase, None)
                if not p.get('phases'):
                    remove_project_and_preserve_schedule(projects, pid)
                else:
                    save_projects(projects)
            break
    return '', 204


@app.route('/split_phase', methods=['POST'])
def split_phase_route():
    data = request.get_json() or request.form
    pid = data.get('pid')
    phase = data.get('phase')
    date_str = data.get('date')
    part1_str = data.get('part1')
    part2_str = data.get('part2')
    if not pid or not phase or not date_str or part1_str is None or part2_str is None:
        return '', 400
    try:
        date.fromisoformat(date_str)
    except Exception:
        return '', 400
    try:
        part1 = int(part1_str)
        part2 = int(part2_str)
    except Exception:
        return '', 400

    projects = get_projects()
    proj = next((p for p in projects if p['id'] == pid), None)
    if not proj or phase not in proj.get('phases', {}):
        return '', 400

    val = proj['phases'][phase]
    total = sum(int(v) for v in val) if isinstance(val, list) else int(val)
    if part1 + part2 != total:
        return jsonify({'error': 'Las horas no coinciden con el total'}), 400

    proj['phases'][phase] = [part1, part2]
    proj.setdefault('segment_starts', {}).setdefault(phase, [None, None])
    worker = proj.get('assigned', {}).get(phase)
    proj.setdefault('segment_workers', {}).setdefault(phase, [worker, worker])
    save_projects(projects)
    return '', 204


@app.route('/unsplit_phase', methods=['POST'])
def unsplit_phase():
    data = request.get_json() or request.form
    pid = data.get('pid')
    phase = data.get('phase')
    if not pid or not phase:
        return '', 400
    projects = get_projects()
    proj = next((p for p in projects if p['id'] == pid), None)
    if not proj or phase not in proj.get('phases', {}):
        return '', 400
    val = proj['phases'][phase]
    if not isinstance(val, list) or len(val) <= 1:
        return '', 400
    total = sum(int(v) for v in val)
    mapping = compute_schedule_map(projects)
    part_hours = {}
    part_workers = {}
    for worker, day, ph, hrs, prt in mapping.get(pid, []):
        if ph == phase and prt is not None and prt < len(val):
            part_hours[prt] = part_hours.get(prt, 0) + hrs
            part_workers.setdefault(prt, worker)
    if part_hours:
        largest = max(part_hours.items(), key=lambda x: x[1])[0]
        worker = part_workers.get(largest)
        if worker:
            proj.setdefault('assigned', {})[phase] = worker
    proj['phases'][phase] = total
    segs = proj.get('segment_starts', {}).get(phase)
    if segs:
        proj['segment_starts'][phase] = [segs[0]]
        if not segs[0]:
            proj['segment_starts'].pop(phase)
    segw = proj.get('segment_workers', {}).get(phase)
    if segw is not None:
        proj['segment_workers'].pop(phase, None)
        if not proj['segment_workers']:
            proj.pop('segment_workers')
    save_projects(projects)
    return '', 204


@app.route('/move', methods=['POST'])
def move_phase():
    data = request.get_json() or request.form
    pid = data.get('pid')
    phase = data.get('phase')
    date_str = data.get('date')
    worker = data.get('worker')
    part = data.get('part')
    if part in (None, '', 'None'):
        part = None
    else:
        try:
            part = int(part)
        except Exception:
            part = None
    # 🔧 Respetamos el modo que viene en la petición
    mode = data.get('mode', 'split')
    push_pid = data.get('push_pid')
    push_phase = data.get('push_phase')
    push_part = data.get('push_part')
    push_from = None
    if push_pid and push_phase:
        push_from = (push_pid, push_phase, push_part if push_part not in (None, '', 'None') else None)
    unblock = str(data.get('unblock')).lower() == 'true'
    skip_block = str(data.get('skip_block')).lower() == 'true'
    ack_warning = str(data.get('ack_warning')).lower() == 'true'
    start = data.get('start')
    if start in (None, '', 'None'):
        start_hour = None
    else:
        try:
            start_hour = float(start)
        except Exception:
            start_hour = None
    if not pid or not phase or not date_str:
        return '', 400
    try:
        day = date.fromisoformat(date_str)
    except Exception:
        return '', 400

    projects = get_projects()
    original_projects = copy.deepcopy(projects)
    tracker_events = []
    new_day, warn, info = move_phase_date(
        projects,
        pid,
        phase,
        day,
        worker,
        part,
        mode=mode,   # 👉 aquí respetamos el valor recibido
        push_from=push_from,
        unblock=unblock,
        skip_block=skip_block,
        start_hour=start_hour,
        track=tracker_events,
    )
    if new_day is None:
        if isinstance(warn, dict):
            return jsonify({'blocked': warn}), 409
        return jsonify({'error': warn or 'No se pudo mover'}), 400

    # Revert move if the target day is already full and the phase was
    # scheduled elsewhere. This prevents the phase from jumping to the next
    # available day when the chosen cell has no remaining hours.
    mapping = compute_schedule_map(projects)
    actual_day = None
    for w, d, ph, hrs, prt in mapping.get(pid, []):
        if ph == phase and (part is None or prt == part):
            actual_day = d
            break
    if actual_day != date_str:
        projects[:] = original_projects
        save_projects(projects)
        return jsonify({'error': 'Jornada ocupada'}), 409

    # Build tracker entry with detailed reasoning
    proj = next((p for p in projects if p['id'] == pid), {})
    reason = build_move_reason(projects, pid, phase, part, mode, info)
    affected_entries = []
    for ev in tracker_events:
        p2 = next((p for p in projects if p['id'] == ev['pid']), None)
        if p2:
            affected_entries.append({
                'project': p2.get('name', ''),
                'client': p2.get('client', ''),
                'phase': ev['phase'],
            })
    logs = load_tracker()
    logs.append({
        'timestamp': local_now().isoformat(),
        'project': proj.get('name', ''),
        'client': proj.get('client', ''),
        'phase': phase,
        'reason': reason,
        'affected': affected_entries,
    })
    save_tracker(logs)

    blockers = material_blockers_for_project(projects, pid, new_day)

    resp = {
        'date': new_day,
        'pid': pid,
        'phase': phase,
        'part': part,
        'material_blockers': blockers,
    }
    if warn and not ack_warning:
        resp['warning'] = warn
    return jsonify(resp)



def remove_project_and_preserve_schedule(projects, pid):
    """Remove a project and keep other projects' schedules intact.

    Returns the removed project dictionary when found so callers can reuse
    metadata (e.g. project name or client) after the removal took place.
    """
    mapping = compute_schedule_map(projects)
    removed = None
    for p in projects:
        if p['id'] == pid:
            removed = p
            break
    if not removed:
        return None
    projects.remove(removed)
    _remove_upload_file(removed.get('image'))
    # Drop any persisted conflicts tied to the removed project so stale
    # warnings do not linger in the interface.
    extras = load_extra_conflicts()
    new_extras = [
        c for c in extras if c.get('pid') != pid and c.get('project') != removed.get('name')
    ]
    if len(new_extras) != len(extras):
        save_extra_conflicts(new_extras)

    dismissed = load_dismissed()
    prefix = f"{removed.get('name')}|"
    kanban_key = f"kanban-{pid}"
    new_dismissed = [
        k for k in dismissed if not (k.startswith(prefix) or k == kanban_key)
    ]
    if len(new_dismissed) != len(dismissed):
        save_dismissed(new_dismissed)
    for proj in projects:
        tasks = mapping.get(proj['id'])
        if not tasks:
            continue
        starts = {}
        for worker, day, phase, hours, part in tasks:
            key = (phase, part)
            if key not in starts or day < starts[key][1]:
                starts[key] = (worker, day)
        seg_starts = proj.setdefault('segment_starts', {})
        assigned = proj.setdefault('assigned', {})
        seg_workers = proj.setdefault('segment_workers', {})
        for (phase, part), (worker, day) in starts.items():
            if part is None:
                seg_starts.setdefault(phase, [None])[0] = day
                assigned[phase] = worker
            else:
                lst = seg_starts.setdefault(phase, [])
                while len(lst) <= part:
                    lst.append(None)
                lst[part] = day
                wl = seg_workers.setdefault(phase, [])
                while len(wl) <= part:
                    wl.append(None)
                wl[part] = worker
    save_projects(projects)
    prune_orphan_uploads(projects)
    return removed

@app.route('/delete_project/<pid>', methods=['POST'])
def delete_project(pid):
    projects = get_projects()
    remove_project_and_preserve_schedule(projects, pid)
    next_url = request.args.get('next') or url_for('project_list')
    return redirect(next_url)


@app.route('/delete_conflict/<path:key>', methods=['POST'])
def delete_conflict(key):
    dismissed = load_dismissed()
    if key not in dismissed:
        dismissed.append(key)
        save_dismissed(dismissed)
    extras = load_extra_conflicts()
    new_extras = [e for e in extras if e['key'] != key]
    if len(new_extras) != len(extras):
        save_extra_conflicts(new_extras)
    # Return to the page that issued the request so the user stays on the
    # same tab (e.g. "Completo") instead of always jumping back to the
    # calendar view.
    return redirect(request.referrer or url_for('complete'))


@app.route('/clear_conflicts', methods=['POST'])
def clear_conflicts():
    """Mark all current conflicts as dismissed and clear extras."""
    projects = get_projects()
    _, conflicts = schedule_projects(projects)
    conflicts = [c for c in conflicts if c.get('message') != 'No se cumple la fecha de entrega']
    extras = load_extra_conflicts()
    keys = [c['key'] for c in conflicts] + [e['key'] for e in extras]
    dismissed = load_dismissed()
    for k in keys:
        if k not in dismissed:
            dismissed.append(k)
    save_dismissed(dismissed)
    save_extra_conflicts([])
    return redirect(request.referrer or url_for('calendar_view'))


@app.route('/show_conflicts', methods=['POST'])
def show_conflicts():
    """Restore all dismissed conflicts so they appear again."""
    save_dismissed([])
    return redirect(request.referrer or url_for('calendar_view'))


@app.route('/toggle_freeze/<pid>/<phase>', methods=['POST'])
def toggle_freeze(pid, phase):
    def _task_positions(projs):
        sched, _ = schedule_projects(copy.deepcopy(projs))
        mapping = {}
        for w, days in sched.items():
            for d, tasks in days.items():
                for t in tasks:
                    key = (t['pid'], t['phase'], t.get('part'))
                    start = t.get('start', 0)
                    cur = mapping.get(key)
                    if not cur or d < cur['day'] or (d == cur['day'] and start < cur['start']):
                        mapping[key] = {'day': d, 'start': start}
        return mapping

    projects = get_projects()
    before = _task_positions(projects)
    proj = next((p for p in projects if p['id'] == pid), None)
    if not proj:
        return jsonify({'error': 'Proyecto no encontrado'}), 404
    frozen = proj.get('frozen_tasks', [])
    was_frozen = any(t['phase'] == phase for t in frozen)
    if was_frozen:
        proj['frozen_tasks'] = [t for t in frozen if t['phase'] != phase]
    else:
        # Recompute the schedule on a copy so freezing a phase does not
        # persistently modify the existing planning
        schedule, _ = schedule_projects(copy.deepcopy(projects))
        for w, days in schedule.items():
            for day, tasks in days.items():
                for t in tasks:
                    if t['pid'] == pid and t['phase'] == phase:
                        item = t.copy()
                        item['worker'] = w
                        item['day'] = day
                        item['frozen'] = True
                        frozen.append(item)
        proj['frozen_tasks'] = frozen

    after = _task_positions(projects)

    if was_frozen:
        for (p_id, ph, part), info in before.items():
            if p_id == pid and ph == phase:
                continue
            new = after.get((p_id, ph, part))
            if not new or new['day'] != info['day'] or new['start'] != info['start']:
                target = next((p for p in projects if p['id'] == p_id), None)
                if not target:
                    continue
                segs = target.setdefault('segment_starts', {}).setdefault(ph, [])
                hours = target.setdefault('segment_start_hours', {}).setdefault(ph, [])
                idx = part if part is not None else 0
                while len(segs) <= idx:
                    segs.append(None)
                while len(hours) <= idx:
                    hours.append(None)
                segs[idx] = info['day']
                hours[idx] = info['start']

    save_projects(projects)
    if request.is_json:
        return '', 204
    return redirect(request.referrer or url_for('calendar_view'))


@app.route('/toggle_block/<pid>', methods=['POST'])
def toggle_block(pid):
    """Toggle blocked state on a project."""
    projects = get_projects()
    proj = next((p for p in projects if p['id'] == pid), None)
    if not proj:
        return jsonify({'error': 'Proyecto no encontrado'}), 404
    proj['blocked'] = not proj.get('blocked', False)
    save_projects(projects)
    if request.is_json:
        return '', 204
    return redirect(request.referrer or url_for('calendar_view'))


@app.route('/kanbanize-webhook', methods=['POST'])
def kanbanize_webhook():
    """Convert incoming Kanbanize card data into a new project."""

    raw_body = request.get_data()

    data = None

    # 1. Intentar JSON directo
    if request.is_json:
        try:
            data = request.get_json()
        except Exception as e:
            print("Error leyendo JSON directo:", e)

    # 2. Intentar si vino como form-data o querystring
    if not data:
        payload = (
            request.form.get('kanbanize_payload')
            or request.form.get('payload')
            or request.form.get('data')
            or request.args.get('kanbanize_payload')
            or request.args.get('payload')
            or request.args.get('data')
        )
        if payload:
            data = _decode_json(payload)

    # 3. Último recurso: decodificar el body crudo
    if not data and raw_body:
        data = _decode_json(raw_body)

    if not isinstance(data, dict):
        return jsonify({'error': 'Error al procesar datos'}), 400

    # Si es un payload anidado dentro de "kanbanize_payload"
    if "kanbanize_payload" in data and isinstance(data["kanbanize_payload"], str):
        inner = _decode_json(data["kanbanize_payload"])
        if isinstance(inner, dict):
            data = inner

    print("Payload recibido:", data)

    card = data.get("card", {})

    payload_timestamp = data.get("timestamp")
    def pick(d, *keys):
        for k in keys:
            if k in d and d[k] is not None:
                return d[k]
        low = {k.lower(): v for k, v in d.items()}
        for k in keys:
            if k.lower() in low and low[k.lower()] is not None:
                return low[k.lower()]
        return None

    def norm(s):
        return re.sub(r'\s+', ' ', s or '').strip().lower()

    cid = pick(card, 'taskid', 'cardId', 'id')
    if cid:
        fetched = _fetch_kanban_card(cid, with_links=True)
        if isinstance(fetched, dict):
            card = fetched

    lane = pick(card, 'lanename', 'laneName', 'lane')
    column = pick(card, 'columnname', 'columnName', 'column')

    # Retrieve the most recent stored version of this card to detect which
    # fields actually changed in Kanbanize.
    prev_card = last_kanban_card(cid)

    print("Evento Kanbanize → lane:", lane, "column:", column, "cid:", cid)

    lane_norm = norm(lane)
    column_norm = norm(column)

    # Guardar tarjetas del lane Seguimiento compras
    if lane_norm == "seguimiento compras":
        cards = load_kanban_cards()
        cid_str = str(cid)
        prev = None
        new_cards = []
        for c in cards:
            existing_id = str(
                c.get('card', {}).get('taskid')
                or c.get('card', {}).get('cardId')
                or c.get('card', {}).get('id')
            )
            if existing_id == cid_str:
                prev = c
            else:
                new_cards.append(c)
        prev_date = prev.get('stored_title_date') if prev else None
        title = card.get('title') or ''
        m = re.search(r"\((\d{2})/(\d{2})\)", title)
        if m:
            stored_date = f"{m.group(1)}/{m.group(2)}"
        else:
            stored_date = prev_date
        new_cards.append({'timestamp': payload_timestamp, 'card': card, 'stored_title_date': stored_date})
        save_kanban_cards(new_cards)
        broadcast_event({"type": "kanban_update"})
        return jsonify({"mensaje": "Tarjeta procesada"}), 200

    # Lanes válidos para proyectos
    allowed_lanes_n = {norm(x) for x in ARCHIVE_LANES}
    if lane_norm not in allowed_lanes_n:
        return jsonify({"mensaje": f"Lane ignorada ({lane})"}), 200

    if column_norm == 'ready to archive':
        projects = load_projects()
        name_candidates = [
            pick(card, 'customCardId', 'effectiveCardId'),
            pick(card, 'title'),
        ]
        name_candidates = [n for n in name_candidates if n]

        pid = None
        matched_project = None
        for p in projects:
            if p.get('kanban_id') == cid or (name_candidates and p.get('name') in name_candidates):
                if cid and not p.get('kanban_id'):
                    p['kanban_id'] = cid
                pid = p['id']
                matched_project = p
                break
        if pid:
            removed_project = remove_project_and_preserve_schedule(projects, pid)
            save_projects(projects)

            archived_info = removed_project or matched_project or {}
            if name_candidates:
                fallback_name = name_candidates[0]
            elif cid:
                fallback_name = f"Tarjeta {cid}"
            else:
                fallback_name = 'Proyecto'
            project_name = archived_info.get('name') or fallback_name
            client_name = archived_info.get('client') or pick(card, 'client', 'Cliente', 'customer') or ''

            extras = load_extra_conflicts()
            conflict_id = str(uuid.uuid4())
            extras.insert(
                0,
                {
                    'id': conflict_id,
                    'project': project_name,
                    'client': client_name,
                    'message': 'Se ha archivado.',
                    'key': f"kanban-archived-{conflict_id}",
                    'source': 'kanbanize',
                },
            )
            save_extra_conflicts(extras)
            broadcast_event({"type": "kanban_update"})
            return jsonify({"mensaje": "Proyecto eliminado"}), 200
        else:
            print("Aviso: no se encontró proyecto para cid/nombre:", cid, name_candidates)
            return jsonify({"mensaje": "Evento recibido, proyecto no encontrado"}), 200


    print("Tarjeta recibida:")
    print(card)

    raw_custom = card.get('customFields') or {}
    if isinstance(raw_custom, list):
        custom = {
            f.get('name'): f.get('value')
            for f in raw_custom if isinstance(f, dict)
        }
    elif isinstance(raw_custom, dict):
        custom = dict(raw_custom)
    else:
        custom = {}
    custom.setdefault('CALDERERIA', custom.get('CALDERERÍA'))
    popup_raw = {field: custom.get(field) for field in KANBAN_POPUP_FIELDS}
    for k in ['Horas', 'MATERIAL', 'CALDERERIA', 'CALDERERÍA']:
        custom.pop(k, None)
    card['customFields'] = custom

    prev_raw_custom = prev_card.get('customFields') or {}
    if isinstance(prev_raw_custom, list):
        prev_custom = {
            f.get('name'): f.get('value')
            for f in prev_raw_custom if isinstance(f, dict)
        }
    elif isinstance(prev_raw_custom, dict):
        prev_custom = dict(prev_raw_custom)
    else:
        prev_custom = {}
    prev_custom.setdefault('CALDERERIA', prev_custom.get('CALDERERÍA'))
    for k in ['Horas', 'MATERIAL', 'CALDERERIA', 'CALDERERÍA']:
        prev_custom.pop(k, None)

    deadline_str = card.get('deadline')
    fecha_cli_str = (
        custom.get('Fecha Cliente')
        or custom.get('Fecha cliente')
        or custom.get('Fecha pedido')
    )
    if deadline_str:
        due_date_obj = parse_kanban_date(deadline_str)
        due_confirmed_flag = True
    else:
        due_date_obj = parse_kanban_date(fecha_cli_str)
        due_confirmed_flag = False
    mat_str = custom.get('Fecha material confirmado')
    material_date_obj = parse_kanban_date(mat_str)

    prev_deadline_str = prev_card.get('deadline')
    prev_fecha_cli_str = (
        prev_custom.get('Fecha Cliente')
        or prev_custom.get('Fecha cliente')
        or prev_custom.get('Fecha pedido')
    )
    if prev_deadline_str:
        prev_due_date_obj = parse_kanban_date(prev_deadline_str)
        prev_due_confirmed_flag = True
    else:
        prev_due_date_obj = parse_kanban_date(prev_fecha_cli_str)
        prev_due_confirmed_flag = False
    prev_mat_str = prev_custom.get('Fecha material confirmado')
    prev_material_date_obj = parse_kanban_date(prev_mat_str)

    def obtener_duracion(campo):
        valor = custom.get(campo)
        if valor in [None, ""]:
            return 0
        if isinstance(valor, str):
            match = re.search(r"\d+", valor)
            return int(match.group()) if match else 0
        try:
            return int(valor)
        except Exception:
            return 0

    def obtener_duracion_prev(campo):
        valor = prev_custom.get(campo)
        if valor in [None, ""]:
            return 0
        if isinstance(valor, str):
            match = re.search(r"\d+", valor)
            return int(match.group()) if match else 0
        try:
            return int(valor)
        except Exception:
            return 0

    prep_raw = obtener_duracion('Horas Preparación')
    mont_raw = obtener_duracion('Horas Montaje')
    sold2_raw = obtener_duracion('Horas Soldadura 2º') or obtener_duracion('Horas Soldadura 2°')
    sold_raw = obtener_duracion('Horas Soldadura')
    pint_raw = obtener_duracion('Horas Acabado')
    mont2_raw = obtener_duracion('Horas Montaje 2º') or obtener_duracion('Horas Montaje 2°')

    prev_prep_raw = obtener_duracion_prev('Horas Preparación')
    prev_mont_raw = obtener_duracion_prev('Horas Montaje')
    prev_sold2_raw = obtener_duracion_prev('Horas Soldadura 2º') or obtener_duracion_prev('Horas Soldadura 2°')
    prev_sold_raw = obtener_duracion_prev('Horas Soldadura')
    prev_pint_raw = obtener_duracion_prev('Horas Acabado')
    prev_mont2_raw = obtener_duracion_prev('Horas Montaje 2º') or obtener_duracion_prev('Horas Montaje 2°')

    def flag_val(campo):
        v = custom.get(campo)
        if isinstance(v, str):
            return v.strip().lower() not in ("", "0", "false", "no")
        return bool(v)

    def flag_val_prev(campo):
        v = prev_custom.get(campo)
        if isinstance(v, str):
            return v.strip().lower() not in ("", "0", "false", "no")
        return bool(v)

    mecan_flag = flag_val('MECANIZADO')
    trat_flag = flag_val('TRATAMIENTO')
    prev_mecan_flag = flag_val_prev('MECANIZADO')
    prev_trat_flag = flag_val_prev('TRATAMIENTO')

    # Working copies that may be adjusted for automatic phases
    prep_hours, mont_hours = prep_raw, mont_raw
    sold2_hours, sold_hours = sold2_raw, sold_raw
    pint_hours, mont2_hours = pint_raw, mont2_raw

    def _clean_display_value(value):
        if value is None:
            return None
        if isinstance(value, str):
            text = value.strip()
            return text or None
        if isinstance(value, bool):
            return 'Sí' if value else None
        if isinstance(value, (int, float)):
            return str(value) if value != 0 else None
        text = str(value).strip()
        return text or None

    display_fields = {}
    for field in ('LANZAMIENTO', 'MATERIAL', 'CALDERERIA', 'PINTADO'):
        cleaned = _clean_display_value(popup_raw.get(field))
        if cleaned:
            display_fields[field] = cleaned
    if mecan_flag:
        mecan_value = _clean_display_value(popup_raw.get('MECANIZADO')) or 'Sí'
        display_fields['MECANIZADO'] = mecan_value
    if trat_flag:
        trat_value = _clean_display_value(popup_raw.get('TRATAMIENTO')) or 'Sí'
        display_fields['TRATAMIENTO'] = trat_value

    phase_hours_new_raw = {
        'recepcionar material': prep_raw,
        'montar': mont_raw,
        'soldar 2º': sold2_raw,
        'soldar': sold_raw,
        'pintar': pint_raw,
        'montar 2º': mont2_raw,
        'mecanizar': 1 if mecan_flag else 0,
        'tratamiento': 1 if trat_flag else 0,
    }
    phase_hours_prev = {
        'recepcionar material': prev_prep_raw,
        'montar': prev_mont_raw,
        'soldar 2º': prev_sold2_raw,
        'soldar': prev_sold_raw,
        'pintar': prev_pint_raw,
        'montar 2º': prev_mont2_raw,
        'mecanizar': 1 if prev_mecan_flag else 0,
        'tratamiento': 1 if prev_trat_flag else 0,
    }
    auto_prep = False
    if (
        prep_hours <= 0
        and mont_hours <= 0
        and sold2_hours <= 0
        and sold_hours <= 0
        and pint_hours <= 0
        and mont2_hours <= 0
    ):
        prep_hours = 1
        auto_prep = True
    fases = []
    if auto_prep or prep_hours > 0:
        fases.append({'nombre': 'recepcionar material', 'duracion': prep_hours, 'auto': auto_prep})
    else:
        fases.append({'nombre': 'recepcionar material', 'duracion': prep_hours})
    if mont_hours > 0:
        fases.append({'nombre': 'montar', 'duracion': mont_hours})
    if sold2_hours > 0:
        fases.append({'nombre': 'soldar 2º', 'duracion': sold2_hours})
    if pint_hours > 0:
        fases.append({'nombre': 'pintar', 'duracion': pint_hours})
    if mont2_hours > 0:
        fases.append({'nombre': 'montar 2º', 'duracion': mont2_hours})
    if sold_hours > 0:
        fases.append({'nombre': 'soldar', 'duracion': sold_hours})
    if mecan_flag:
        fases.append({'nombre': 'mecanizar', 'duracion': 1, 'auto': True})
    if trat_flag:
        fases.append({'nombre': 'tratamiento', 'duracion': 1, 'auto': True})
    auto_flags = {f['nombre']: True for f in fases if f.get('auto')}

    task_id = card.get('taskid') or card.get('cardId') or card.get('id')
    nombre_proyecto = (
        card.get('customCardId')
        or card.get('effectiveCardId')
        or card.get('title')
        or f"Kanbanize-{task_id or uuid.uuid4()}"
    )
    cliente = card.get('title') or "Sin cliente"

    prev_task_id = (
        prev_card.get('taskid')
        or prev_card.get('cardId')
        or prev_card.get('id')
    )
    prev_nombre_proyecto = (
        prev_card.get('customCardId')
        or prev_card.get('effectiveCardId')
        or prev_card.get('title')
    )
    prev_cliente = prev_card.get('title') or "Sin cliente"

    attachments_raw = data.get('Attachments') or card.get('Attachments') or []
    kanban_files = []
    if isinstance(attachments_raw, list):
        for a in attachments_raw:
            if isinstance(a, dict):
                name = (a.get('name') or a.get('fileName') or a.get('filename') or '').strip()
                url = (a.get('url') or a.get('fileUrl') or a.get('link') or '').strip()
                if name and url:
                    if url.startswith('/') or not re.match(r'https?://', url):
                        url = f"{KANBANIZE_BASE_URL.rstrip('/')}/{url.lstrip('/')}"
                    kanban_files.append({'name': name, 'url': url})

    prev_attachments_raw = prev_card.get('Attachments') or []
    prev_kanban_files = []
    if isinstance(prev_attachments_raw, list):
        for a in prev_attachments_raw:
            if isinstance(a, dict):
                name = (a.get('name') or a.get('fileName') or a.get('filename') or '').strip()
                url = (a.get('url') or a.get('fileUrl') or a.get('link') or '').strip()
                if name and url:
                    if url.startswith('/') or not re.match(r'https?://', url):
                        url = f"{KANBANIZE_BASE_URL.rstrip('/')}/{url.lstrip('/')}"
                    prev_kanban_files.append({'name': name, 'url': url})

    image_path = None

    projects = load_projects()
    existing = next(
        (
            p
            for p in projects
            if p.get('source') == 'api' and p.get('name') == nombre_proyecto
        ),
        None,
    )

    new_phases = {f['nombre']: f['duracion'] for f in fases}
    new_auto = {f['nombre']: True for f in fases if f.get('auto')}
    if isinstance(column, str):
        clean_column = column.strip()
    elif column:
        clean_column = str(column).strip()
    else:
        clean_column = ''

    if existing:
        changed = False
        if existing.get('kanban_column') != clean_column:
            existing['kanban_column'] = clean_column
            changed = True
        if existing.get('kanban_archived'):
            existing['kanban_archived'] = False
            changed = True
        if existing.get('kanban_id') != task_id:
            existing['kanban_id'] = task_id
            changed = True
        if prev_nombre_proyecto != nombre_proyecto and existing.get('name') != nombre_proyecto:
            existing['name'] = nombre_proyecto
            changed = True
        if prev_cliente != cliente and existing.get('client') != cliente:
            existing['client'] = cliente
            changed = True
        if not existing.get('color') or not re.fullmatch(r"#[0-9A-Fa-f]{6}", existing.get('color', '')):
            existing['color'] = _next_api_color()
            changed = True
        if (prev_due_date_obj != due_date_obj) or (prev_due_confirmed_flag != due_confirmed_flag):
            if due_date_obj:
                existing['due_date'] = due_date_obj.isoformat()
                existing['due_confirmed'] = due_confirmed_flag
                existing['due_warning'] = False
            else:
                existing['due_date'] = ''
                existing['due_confirmed'] = False
            changed = True
        if prev_material_date_obj != material_date_obj:
            existing['material_confirmed_date'] = material_date_obj.isoformat() if material_date_obj else ''
            changed = True
        if image_path and existing.get('image') != image_path:
            existing['image'] = image_path
            changed = True
        if prev_kanban_files != kanban_files and existing.get('kanban_attachments') != kanban_files:
            existing['kanban_attachments'] = kanban_files
            changed = True
        if existing.get('kanban_display_fields') != display_fields:
            existing['kanban_display_fields'] = display_fields
            changed = True

        existing_phases = existing.setdefault('phases', {})
        existing_assigned = existing.setdefault('assigned', {})
        existing_auto = existing.setdefault('auto_hours', {})

        changed_phases = {}
        for ph, new_raw in phase_hours_new_raw.items():
            prev_raw = phase_hours_prev.get(ph, 0)
            if new_raw != prev_raw:
                changed_phases[ph] = new_phases.get(ph, 0)

        for ph, hours in changed_phases.items():
            if ph in ("mecanizar", "tratamiento") and hours == 1:
                existing_hours = existing_phases.get(ph)
                if existing_hours not in (None, 0, ''):
                    continue
            if hours > 0:
                if existing_phases.get(ph) != hours:
                    existing_phases[ph] = hours
                    changed = True
                if ph not in existing_assigned:
                    existing_assigned[ph] = UNPLANNED
                    changed = True
                if new_auto.get(ph):
                    if not existing_auto.get(ph):
                        existing_auto[ph] = True
                        changed = True
                else:
                    if existing_auto.pop(ph, None) is not None:
                        changed = True
            else:
                if existing_phases.pop(ph, None) is not None:
                    changed = True
                if existing_assigned.pop(ph, None) is not None:
                    changed = True
                if existing_auto.pop(ph, None) is not None:
                    changed = True

        if changed:
            save_projects(projects)
    else:
        project = {
            'id': str(uuid.uuid4()),
            'name': nombre_proyecto,
            'client': cliente,
            'start_date': local_today().isoformat(),
            'due_date': due_date_obj.isoformat() if due_date_obj else '',
            'material_confirmed_date': material_date_obj.isoformat() if material_date_obj else '',
            'color': _next_api_color(),
            'phases': new_phases,
            'assigned': {f['nombre']: UNPLANNED for f in fases},
            'auto_hours': new_auto,
            'image': image_path,
            'kanban_attachments': kanban_files,
            'kanban_display_fields': display_fields,
            'planned': False,
            'source': 'api',
            'kanban_id': task_id,
            'due_confirmed': due_confirmed_flag,
            'due_warning': False,
            'kanban_column': clean_column,
            'kanban_archived': False,
        }
        projects.append(project)
        save_projects(projects)

    cards = load_kanban_cards()
    cards.append({'timestamp': payload_timestamp, 'card': card})
    save_kanban_cards(cards)

    if not existing:
        extras = load_extra_conflicts()
        extras.append({
            'id': str(uuid.uuid4()),
            'project': project['name'],
            'client': project['client'],
            'message': 'Proyecto creado desde Kanbanize',
            'key': f"kanban-{project['id']}",
            'source': 'kanbanize',
            'pid': project['id'],
        })
        save_extra_conflicts(extras)
        broadcast_event({"type": "kanban_update"})
        return jsonify({"mensaje": "Proyecto creado"}), 200
    else:
        broadcast_event({"type": "kanban_update"})
        return jsonify({"mensaje": "Proyecto actualizado"}), 200


@app.route('/hours')
def hours():
    projects = get_visible_projects()
    schedule, _ = schedule_projects(copy.deepcopy(projects))
    rows = []
    for days in schedule.values():
        for tasks in days.values():
            for t in tasks:
                if t.get('phase') == 'vacaciones':
                    continue
                rows.append({
                    'project': t.get('project'),
                    'phase': t.get('phase'),
                    'start_time': t.get('start_time'),
                    'end_time': t.get('end_time'),
                })
    rows.sort(key=lambda r: r['start_time'])
    return render_template('hours.html', rows=rows)


@app.route('/tracker')
def tracker():
    logs = load_tracker()
    logs.sort(key=lambda l: l.get('timestamp', ''), reverse=True)
    return render_template('tracker.html', logs=logs)


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=9000)
