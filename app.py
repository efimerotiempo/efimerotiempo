from flask import Flask, render_template, request, redirect, url_for, jsonify, Response
from datetime import date, timedelta, datetime
import uuid
import os
import copy
import json
import re
import smtplib
from email.message import EmailMessage
from werkzeug.utils import secure_filename
from urllib.request import Request, urlopen
import urllib.parse
import sys
import importlib.util
import random
import requests

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
load_vacations = _schedule_mod.load_vacations
save_vacations = _schedule_mod.save_vacations
load_daily_hours = _schedule_mod.load_daily_hours
save_daily_hours = _schedule_mod.save_daily_hours
load_inactive_workers = _schedule_mod.load_inactive_workers
save_inactive_workers = _schedule_mod.save_inactive_workers
PRIORITY_ORDER = _schedule_mod.PRIORITY_ORDER
PHASE_ORDER = _schedule_mod.PHASE_ORDER
WORKERS = _schedule_mod.WORKERS
IGOR_END = _schedule_mod.IGOR_END
find_worker_for_phase = _schedule_mod.find_worker_for_phase
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
BUGS_FILE = os.path.join(DATA_DIR, 'bugs.json')
KANBAN_CARDS_FILE = os.path.join(DATA_DIR, 'kanban_cards.json')
KANBAN_PREFILL_FILE = os.path.join(DATA_DIR, 'kanban_prefill.json')
KANBAN_COLUMN_COLORS_FILE = os.path.join(DATA_DIR, 'kanban_column_colors.json')

# Kanbanize integration constants
KANBANIZE_API_KEY = os.getenv("jpQfMzS8AzdyD70zLkilBjP0Uig957mOATuM0BOE")
KANBANIZE_BASE_URL = 'https://caldereriacpk.kanbanize.com'
KANBANIZE_BOARD_TOKEN = os.environ.get('KANBANIZE_BOARD_TOKEN', '682d829a0aafe44469o50acd')
KANBANIZE_BOARD_ID = os.getenv("1")
KANBANIZE_API_KEY = "jpQfMzS8AzdyD70zLkilBjP0Uig957mOATuM0BOE"
KANBANIZE_SUBDOMAIN = "caldereriacpk"
KANBANIZE_BOARD_ID = "1"

KANBANIZE_URL = "https://caldereriacpk.kanbanize.com/api/v2/cards"

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
    'Plegado/curvado - Fabricación',
    'Material Incompleto',
    'Material NO CONFORME',
}

PEDIDOS_HIDDEN_COLUMNS = [
    "Ready to Archive",
    "Material recepcionado",
    "Pdte. Verificación",
]

PEDIDOS_UNCONFIRMED_COLUMNS = {
    'Tau',
    'Bekola',
    'AZ',
    'OTROS',
    'Tratamiento',
    'Planf. TAU',
    'Planif. OTROS',
}
# Mapping between local phase names and Kanbanize custom field names
PHASE_FIELD_MAP = {
    'recepcionar material': 'Horas Preparación',
    'montar': 'Horas Montaje',
    'soldar': 'Horas Soldadura',
    'pintar': 'Horas Acabado',
    'montaje final': 'Horas Montaje Final',
    'soldadura interior': 'Horas Soldadura Interior',
}


def _sync_project_to_kanbanize(proj, changed):
    """Send project updates to Kanbanize according to ``changed`` fields."""
    kanban_id = proj.get('kanban_id')
    if not kanban_id or not changed:
        return

    payload = {}
    custom = {}

    if 'client' in changed:
        payload['title'] = proj.get('client', '')
    if 'priority' in changed:
        payload['priority'] = proj.get('priority')
    if 'due_date' in changed:
        due = proj.get('due_date')
        if due:
            payload['deadline'] = due
            custom['Fecha Cliente'] = due
    if 'material_confirmed_date' in changed:
        mdate = proj.get('material_confirmed_date')
        if mdate:
            custom['Fecha material confirmado'] = mdate

    phases = proj.get('phases', {})
    for ph in changed:
        field = PHASE_FIELD_MAP.get(ph)
        if field and ph in phases:
            custom[field] = phases[ph]

    if custom:
        payload['customFields'] = custom
    if not payload:
        return

    url = f"{KANBANIZE_BASE_URL}/api/v2/boards/{KANBANIZE_BOARD_TOKEN}/cards/{kanban_id}"
    req = Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={'apikey': KANBANIZE_API_KEY, 'Content-Type': 'application/json'},
        method='PUT',
    )
    try:
        with urlopen(req, timeout=10) as resp:
            resp.read()
    except Exception as e:
        print('Kanbanize sync error:', e)


def active_workers(today=None):
    """Return the list of workers shown in the calendar."""
    if today is None:
        today = date.today()
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
            year = date.today().year
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


def load_bugs():
    if os.path.exists(BUGS_FILE):
        with open(BUGS_FILE, 'r') as f:
            return json.load(f)
    return []


def save_bugs(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(BUGS_FILE, 'w') as f:
        json.dump(data, f)


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


def sync_all_cards():
    headers = {"apikey": KANBANIZE_API_KEY, "accept": "application/json"}
    url_cards = f"https://{KANBANIZE_SUBDOMAIN}.kanbanize.com/api/v2/cards"
    url_columns = f"https://{KANBANIZE_SUBDOMAIN}.kanbanize.com/api/v2/boards/{KANBANIZE_BOARD_ID}/columns"
    url_lanes = f"https://{KANBANIZE_SUBDOMAIN}.kanbanize.com/api/v2/boards/{KANBANIZE_BOARD_ID}/lanes"

    # columnas
    resp_cols = requests.get(url_columns, headers=headers)
    print("Columns response:", resp_cols.status_code, resp_cols.text[:200])
    cols_json = resp_cols.json()
    cols = cols_json.get("data", [])
    column_names = {c["column_id"]: c["name"] for c in cols}

    # lanes
    resp_lanes = requests.get(url_lanes, headers=headers)
    print("Lanes response:", resp_lanes.status_code, resp_lanes.text[:200])
    lanes_json = resp_lanes.json()
    lanes = lanes_json.get("data", [])
    lane_names = {l["lane_id"]: l["name"] for l in lanes}

    # tarjetas
    params = {"boardid": KANBANIZE_BOARD_ID}
    r = requests.get(url_cards, headers=headers, params=params)
    print("Cards response:", r.status_code, r.text[:200])
    r.raise_for_status()
    cards = r.json()["data"]["data"]

    now = datetime.utcnow().isoformat()
    payload = []
    for c in cards:
        payload.append({
            "timestamp": now,
            "card": {
                "taskid": c.get("card_id"),
                "title": c.get("title"),
                "customid": c.get("custom_id"),
                "columnid": c.get("column_id"),
                "laneid": c.get("lane_id"),
                "boardid": c.get("board_id"),
                "workflowid": c.get("workflow_id"),
                "columnname": column_names.get(c.get("column_id")),
                "lanename": lane_names.get(c.get("lane_id")),
            }
        })

    save_kanban_cards(payload)
    print(f"Sincronizadas {len(cards)} tarjetas desde Kanbanize")





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


def send_bug_report(bug):
    msg = EmailMessage()
    msg['Subject'] = f"BUG {bug['id']} - {bug['tab']}"
    sender = os.environ.get('BUG_SENDER', 'planificador@example.com')
    msg['From'] = sender
    msg['To'] = 'irodriguez@caldereria-cpk.es'
    body = (
        f"Registrado por: {bug['user']}\n"
        f"Pesta\u00f1a: {bug['tab']}\n"
        f"Frecuencia: {bug['freq']}\n\n"
        f"{bug['detail']}\n"
        f"Fecha: {bug['date']}"
    )
    msg.set_content(body)
    host = os.environ.get('BUG_SMTP_HOST', 'localhost')
    port = int(os.environ.get('BUG_SMTP_PORT', 25))
    user = os.environ.get('BUG_SMTP_USER')
    password = os.environ.get('BUG_SMTP_PASS')
    use_ssl = os.environ.get('BUG_SMTP_SSL') == '1'
    try:
        if use_ssl:
            server = smtplib.SMTP_SSL(host, port)
        else:
            server = smtplib.SMTP(host, port)
        if user and password:
            if not use_ssl:
                server.starttls()
            server.login(user, password)
        server.send_message(msg)
        server.quit()
    except Exception as e:
        print('Error sending bug report:', e)


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
):
    """Move ``phase`` of project ``pid`` so it starts on ``new_date``.

    ``mode`` controls how existing work is handled:

    * ``"split"`` (default) keeps other tasks in place, allowing the phase to
      be divided around them.
    * ``"push"`` shifts subsequent tasks for the same worker so the phase can
      remain continuous.

    Return tuple ``(day, error)`` where ``day`` is the first day of the phase
    after rescheduling, or ``None`` if it could not be moved. ``error`` provides
    a message explaining the failure when applicable.
    """
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
        return None, 'Fase no encontrada'
    if part is not None:
        tasks = [t for t in tasks if t[4] == part]
        if not tasks:
            return None, 'Fase no encontrada'
    proj = next((p for p in projects if p['id'] == pid), None)
    if not proj:
        return None, 'Proyecto no encontrado'
    if phase != 'pedidos' and any(
        t['phase'] == phase and (part is None or t.get('part') == part)
        for t in proj.get('frozen_tasks', [])
    ):
        return None, 'Fase congelada'

    vac_map = _schedule_mod._build_vacation_map()
    if (
        phase != 'pedidos'
        and worker
        and worker != 'Irene'
        and new_date in vac_map.get(worker, set())
    ):
        return None, 'Vacaciones en esa fecha'
    warning = None
    if proj.get('due_date'):
        try:
            due_dt = date.fromisoformat(proj['due_date'])
            phase_hours = proj['phases'].get(phase)
            if isinstance(phase_hours, list):
                if part is None or part >= len(phase_hours):
                    return None, 'Fase no encontrada'
                hours = int(phase_hours[part])
            else:
                hours = int(phase_hours)
            days_needed = (hours + HOURS_PER_DAY - 1) // HOURS_PER_DAY
            test_end = new_date
            for _ in range(days_needed - 1):
                test_end = next_workday(test_end)
            if test_end > due_dt:
                msg = CLIENT_DEADLINE_MSG if proj.get('due_confirmed') else DEADLINE_MSG
                warning = f"{msg}\n{proj['name']} - {proj['client']} - {due_dt.strftime('%Y-%m-%d')}"
        except Exception:
            pass
    # Apply the change to the real project list
    if part is None and not isinstance(proj['phases'].get(phase), list):
        seg_starts = proj.setdefault('segment_starts', {}).setdefault(phase, [None])
        seg_starts[0] = new_date.isoformat()
        seg_hours = proj.setdefault('segment_start_hours', {}).setdefault(phase, [None])
        seg_hours[0] = start_hour
        if worker:
            proj.setdefault('assigned', {})[phase] = worker
    else:
        seg_starts = proj.setdefault('segment_starts', {}).setdefault(
            phase, [None] * len(proj['phases'][phase])
        )
        idx = part if part is not None else 0
        while len(seg_starts) <= idx:
            seg_starts.append(None)
        seg_starts[idx] = new_date.isoformat()
        seg_hours = proj.setdefault('segment_start_hours', {}).setdefault(
            phase, [None] * len(proj['phases'][phase])
        )
        if idx >= len(seg_hours):
            seg_hours.extend([None] * (idx + 1 - len(seg_hours)))
        seg_hours[idx] = start_hour
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
        days_needed = (hours + HOURS_PER_DAY - 1) // HOURS_PER_DAY
        next_start = new_date
        for _ in range(days_needed):
            next_start = next_workday(next_start)

        mapping = compute_schedule_map(projects)
        start_push = new_date
        if push_from:
            pf_pid, pf_phase, pf_part = push_from
            for w, day_str, ph, hrs, prt in mapping.get(pf_pid, []):
                if (
                    w == worker
                    and ph == pf_phase
                    and (pf_part is None or prt == pf_part)
                ):
                    d = date.fromisoformat(day_str)
                    if d < start_push:
                        start_push = d
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
        vac_days = _schedule_mod._build_vacation_map().get(worker, set())
        for start, opid, oph, oprt in sorted(
            (v, k[0], k[1], k[2]) for k, v in seen.items()
        ):
            other_proj = next((p for p in projects if p['id'] == opid), None)
            if not other_proj:
                while next_start in vac_days:
                    next_start = next_workday(next_start)
                continue
            if oph != 'pedidos' and any(
                t['phase'] == oph and (oprt is None or t.get('part') == oprt)
                for t in other_proj.get('frozen_tasks', [])
            ):
                if not unblock and not skip_block:
                    return None, {
                        'pid': opid,
                        'phase': oph,
                        'part': oprt,
                        'name': other_proj.get('name', ''),
                    }
                if skip_block:
                    val = other_proj['phases'][oph]
                    if isinstance(val, list):
                        h = int(val[oprt])
                    else:
                        h = int(val)
                    d_needed = (h + HOURS_PER_DAY - 1) // HOURS_PER_DAY
                    ns = start
                    for _ in range(d_needed):
                        ns = next_workday(ns)
                    next_start = ns
                    continue
                # unblock
                other_proj['frozen_tasks'] = [
                    t
                    for t in other_proj.get('frozen_tasks', [])
                    if not (t['phase'] == oph and (oprt is None or t.get('part') == oprt))
                ]
            while next_start in vac_days:
                next_start = next_workday(next_start)
            move_phase_date(
                projects,
                opid,
                oph,
                next_start,
                worker,
                oprt,
                save=False,
                mode="split",
            )
            val = other_proj['phases'][oph]
            if isinstance(val, list):
                h = int(val[oprt])
            else:
                h = int(val)
            d_needed = (h + HOURS_PER_DAY - 1) // HOURS_PER_DAY
            for _ in range(d_needed):
                next_start = next_workday(next_start)

    if save:
        save_projects(projects)
    return new_date.isoformat(), warning


def get_projects():
    projects = load_projects()
    changed = False
    color_index = 0
    assigned_projects = []
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
            today_str = date.today().isoformat()
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
        if missing:
            schedule, _ = schedule_projects(assigned_projects)
            for ph in missing:
                worker = find_worker_for_phase(
                    ph, {w: schedule.get(w, {}) for w in WORKERS}, p.get('priority')
                )
                if worker:
                    p['assigned'][ph] = worker
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
        assigned_projects.append(p)
    if changed:
        save_projects(projects)
    return projects


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
    for k in ['Horas', 'MATERIAL', 'CALDERERÍA']:
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
    sold = h('Horas Soldadura')
    pint = h('Horas Acabado')
    mont_final = h('Horas Montaje Final')
    sold_int = h('Horas Soldadura Interior')
    phases = {}
    auto_hours = {}
    if (
        prep <= 0
        and mont <= 0
        and sold <= 0
        and pint <= 0
        and mont_final <= 0
        and sold_int <= 0
    ):
        phases['recepcionar material'] = 1
        auto_hours['recepcionar material'] = True
    else:
        if pint:
            phases['pintar'] = pint
        if mont_final:
            phases['montaje final'] = mont_final
        if mont:
            phases['montar'] = mont
        if prep:
            phases['recepcionar material'] = prep
        if sold_int:
            phases['soldadura interior'] = sold_int
        if sold:
            phases['soldar'] = sold

    project = {
        'id': str(uuid.uuid4()),
        'name': project_name,
        'client': client,
        'start_date': date.today().isoformat(),
        'due_date': due.isoformat() if due else '',
        'priority': 'Sin prioridad',
        'color': None,
        'phases': phases,
        # Ensure each phase is explicitly set to the unplanned worker so the
        # calendar always displays the tasks as soon as the project is created.
        'assigned': {ph: UNPLANNED for ph in phases},
        'auto_hours': auto_hours,
        'image': None,
        'kanban_attachments': [],
        'planned': False,
        'source': 'api',
    }
    return project


def _fetch_kanban_card(card_id):
    """Retrieve card details from Kanbanize via the REST API."""
    url = f"{KANBANIZE_BASE_URL}/api/v2/boards/{KANBANIZE_BOARD_TOKEN}/cards/{card_id}"
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
    projects = get_projects()
    schedule, conflicts = schedule_projects(projects)
    today = date.today()
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
        ph = proj['phases'].setdefault(
            phase,
            {
                'project': item['project'],
                'client': item['client'],
                'pid': pid,
                'phase': phase,
                'color': item.get('color'),
                'priority': item.get('priority'),
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
    conflicts = [c for c in conflicts if c['key'] not in dismissed]

    project_filter = request.args.get('project', '').strip()
    client_filter = request.args.get('client', '').strip()

    # filter tasks by project and client
    if project_filter or client_filter:
        for worker, days_data in schedule.items():
            for day, tasks in days_data.items():
                schedule[worker][day] = [
                    t
                    for t in tasks
                    if (not project_filter or project_filter.lower() in t['project'].lower())
                    and (not client_filter or client_filter.lower() in t['client'].lower())
                ]
        unplanned_list = [
            g
            for g in unplanned_list
            if (not project_filter or project_filter.lower() in g['project'].lower())
            and (not client_filter or client_filter.lower() in g['client'].lower())
        ]

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
    project_map = {}
    for p in projects:
        p.setdefault('kanban_attachments', [])
        project_map[p['id']] = {
            **p,
            'frozen_phases': sorted({t['phase'] for t in p.get('frozen_tasks', [])}),
        }
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
        notes=note_map,
        project_data=project_map,
        start_map=start_map,
        phases=PHASE_ORDER,
        hours=hours_map,
        split_points=points,
        palette=COLORS,
        unplanned_with=unplanned_with,
        unplanned_without=unplanned_without,
    )


@app.route('/calendario-pedidos')
def calendar_pedidos():
    today = date.today()

    # --- CARGAR TARJETAS DE KANBANIZE ---
    compras_raw = {}
    kanban_columns = {}
    column_colors = load_column_colors()
    updated_colors = False
    allowed_lanes = [
        'seguimiento compras',
        'acero al carbono',
        'inoxidable - aluminio',
    ]

    for entry in load_kanban_cards():
        if not isinstance(entry, dict):
            continue
        card = entry.get('card') or {}
        if not isinstance(card, dict):
            continue

        lane_name = (card.get('lanename') or '').strip()
        if lane_name.lower() not in allowed_lanes:
            continue

        column = (card.get('columnname') or card.get('columnName') or '').strip()
        cid = card.get('taskid') or card.get('cardId') or card.get('id')
        if not cid:
            continue

        compras_raw[cid] = card
        kanban_columns[str(cid)] = column

        if column and column not in column_colors:
            column_colors[column] = _next_api_color()
            updated_colors = True

    if updated_colors:
        save_column_colors(column_colors)

    # --- CONSTRUIR PEDIDOS Y NO CONFIRMADOS ---
    pedidos = {}
    unconfirmed = []
    links_table = []
    seen_links = set()

    for card in compras_raw.values():
        title = (card.get('title') or '').strip()
        project_name = title
        client_name = ''
        if ' - ' in title:
            project_name, client_name = [p.strip() for p in title.split(' - ', 1)]
        # Buscar fecha (dd/mm) en el título o usar deadline
        m = re.search(r"\((\d{2})/(\d{2})\)", title)
        if m:
            day, month = int(m.group(1)), int(m.group(2))
            try:
                d = date(today.year, month, day)
            except ValueError:
                d = parse_kanban_date(card.get('deadline'))
        else:
            d = parse_kanban_date(card.get('deadline'))

        column = (card.get('columnname') or card.get('columnName') or '').strip()
        lane_name = (card.get('lanename') or '').strip()

        entry = {
            'project': title,
            'color': column_colors.get(column, '#999999'),
            'hours': None,
            'lane': lane_name,
            'client': client_name,
            'column': column,
        }

        # --- CALENDARIO PRINCIPAL ---
        if (
            lane_name.strip().lower() == "seguimiento compras"
            and column not in PEDIDOS_HIDDEN_COLUMNS
            and (
                column in PEDIDOS_ALLOWED_COLUMNS
                or column in PEDIDOS_UNCONFIRMED_COLUMNS
            )
        ):
            if d:  # con fecha
                pedidos.setdefault(d, []).append(entry)

        # --- LISTA SIN FECHA CONFIRMADA ---
        if (
            lane_name.strip() == "Seguimiento compras"
            and column in PEDIDOS_UNCONFIRMED_COLUMNS
            and not d
        ):
            unconfirmed.append(entry)

        # --- TABLA DERECHA (otros lanes archivables) ---
        if (
            lane_name.strip() in ["Acero al Carbono", "Inoxidable - Aluminio"]
            and column not in ["Ready to Archive", "Hacer Albaran"]
        ):
            if project_name not in seen_links:
                child_links = []
                links_info = card.get('links') or {}
                children = links_info.get('children') if isinstance(links_info, dict) else []
                if isinstance(children, list):
                    for ch in children:
                        if isinstance(ch, dict):
                            t = ch.get('title')
                            if t:
                                child_links.append(t)
                links_table.append({'project': project_name, 'client': client_name, 'links': child_links})
                seen_links.add(project_name)

    # --- ARMAR CALENDARIO MENSUAL ---
    current_month_start = date(today.year, today.month, 1)
    month_start = (current_month_start - timedelta(days=1)).replace(day=1)
    start = month_start - timedelta(days=month_start.weekday())

    # Mostrar mes anterior, mes actual y dos meses siguientes
    months_to_show = 4
    end_month = month_start
    for _ in range(months_to_show - 1):
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
            tasks = pedidos.get(day, []) if month_start <= day <= month_end else []
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

    return render_template(
        'calendar_pedidos.html',
        weeks=weeks,
        today=today,
        unconfirmed=unconfirmed,
        project_links=links_table,
    )

@app.route('/projects')
def project_list():
    projects = get_projects()
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
        priorities=list(PRIORITY_ORDER.keys()),
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
            'start_date': date.today().isoformat(),
            'due_date': due.isoformat() if due else '',
            'material_confirmed_date': '',
            'priority': data.get('priority', 'Sin prioridad'),
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
        today=date.today().isoformat(),
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


@app.route('/observaciones')
def observation_list():
    projects = [p for p in get_projects() if p.get('observations')]
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
    return render_template('vacations.html', vacations=vacations, workers=active_workers(), today=date.today().isoformat())


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
    if request.method == 'POST':
        if 'add_worker' in request.form:
            new_worker = request.form.get('new_worker', '').strip()
            if new_worker and new_worker not in WORKERS:
                _schedule_mod.add_worker(new_worker)
            return redirect(url_for('resources'))
        active = request.form.getlist('worker')
        inactive = [w for w in workers if w not in active]
        save_inactive_workers(inactive)
        get_projects()
        return redirect(url_for('resources'))
    return render_template('resources.html', workers=workers, inactive=inactive)


@app.route('/complete')
def complete():
    projects = get_projects()
    schedule, conflicts = schedule_projects(projects)
    today = date.today()
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
        ph = proj['phases'].setdefault(
            phase,
            {
                'project': item['project'],
                'client': item['client'],
                'pid': pid,
                'phase': phase,
                'color': item.get('color'),
                'priority': item.get('priority'),
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
    conflicts = [c for c in conflicts if c['key'] not in dismissed]

    sort_option = request.args.get('sort', 'created')
    orig_order = {p['id']: idx for idx, p in enumerate(projects)}

    project_filter = request.args.get('project', '').strip()
    client_filter = request.args.get('client', '').strip()

    if project_filter or client_filter:
        for worker, days_data in schedule.items():
            for day, tasks in days_data.items():
                schedule[worker][day] = [
                    t
                    for t in tasks
                    if (not project_filter or project_filter.lower() in t['project'].lower())
                    and (not client_filter or client_filter.lower() in t['client'].lower())
                ]
        filtered_projects = [
            p
            for p in projects
            if (not project_filter or project_filter.lower() in p['name'].lower())
            and (not client_filter or client_filter.lower() in p['client'].lower())
        ]
        unplanned_list = [
            g
            for g in unplanned_list
            if (not project_filter or project_filter.lower() in g['project'].lower())
            and (not client_filter or client_filter.lower() in g['client'].lower())
        ]
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

    today = date.today()
    start = today - timedelta(days=90)
    end = today + timedelta(days=180)
    days, cols, week_spans = build_calendar(start, end)
    hours_map = load_daily_hours()
    note_map = {}
    for n in notes:
        note_map.setdefault(n['date'], []).append(n['description'])
    project_map = {}
    for p in projects:
        p.setdefault('kanban_attachments', [])
        project_map[p['id']] = {
            **p,
            'frozen_phases': sorted({t['phase'] for t in p.get('frozen_tasks', [])}),
        }
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
        projects=filtered_projects,
        sort_option=sort_option,
        today=today,
        priorities=list(PRIORITY_ORDER.keys()),
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
    )


@app.route('/update_priority/<pid>', methods=['POST'])
def update_priority(pid):
    projects = get_projects()
    old_map = compute_schedule_map(projects)
    changed_proj = None
    old_priority = None
    for p in projects:
        if p['id'] == pid:
            changed_proj = p
            old_priority = p['priority']
            p['priority'] = request.form['priority']
            break
    save_projects(projects)
    new_map = compute_schedule_map(projects)

    changed_ids = []
    for pr in projects:
        if pr['id'] == pid:
            continue
        if old_map.get(pr['id']) != new_map.get(pr['id']):
            changed_ids.append(pr['id'])

    if changed_proj and changed_ids:
        projects_copy = copy.deepcopy(projects)
        sched, _ = schedule_projects(projects_copy)
        end_dates = {p['id']: p['end_date'] for p in projects_copy}
        start_dates = {}
        for worker, days in sched.items():
            for day, tasks in days.items():
                for t in tasks:
                    d = day
                    pid2 = t['pid']
                    if pid2 not in start_dates or d < start_dates[pid2]:
                        start_dates[pid2] = d
        details = []
        for cid in changed_ids:
            pr = next(p for p in projects if p['id'] == cid)
            if pr.get('due_date'):
                try:
                    met = date.fromisoformat(end_dates[cid]) <= date.fromisoformat(pr['due_date'])
                except ValueError:
                    met = False
            else:
                met = False
            start_offset = (date.fromisoformat(start_dates[cid]) - MIN_DATE).days if cid in start_dates else 0
            details.append({'id': pr['id'], 'name': pr['name'], 'client': pr['client'], 'met': met, 'offset': start_offset})
        if pid in start_dates:
            changed_start = (date.fromisoformat(start_dates[pid]) - MIN_DATE).days
        else:
            changed_start = (date.fromisoformat(changed_proj['start_date']) - MIN_DATE).days

        extras = load_extra_conflicts()
        msg = (
            f"Prioridad de {changed_proj['name']} (cliente {changed_proj['client']}) "
            f"cambiada de {old_priority} a {changed_proj['priority']}"
        )
        extras.append({
            'id': str(uuid.uuid4()),
            'project': changed_proj['name'],
            'client': changed_proj['client'],
            'message': msg,
            'changes': details,
            'key': f'prio-{pid}-{len(extras)}',
            'pid': changed_proj['id'],
            'offset': changed_start,
        })
        save_extra_conflicts(extras)

    next_url = request.form.get('next') or request.args.get('next') or url_for('project_list')
    return redirect(next_url)


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
    _sync_project_to_kanbanize(proj, {'due_date'})
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
    _sync_project_to_kanbanize(proj, {phase})
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

    changed = set()
    modified = set()

    if 'start_date' in data:
        sd = parse_input_date(data['start_date'])
        if sd:
            proj['start_date'] = sd.isoformat()
    if 'due_date' in data:
        dd = parse_input_date(data['due_date'])
        proj['due_date'] = dd.isoformat() if dd else ''
        if dd:
            changed.add('due_date')
    if 'priority' in data:
        proj['priority'] = data['priority']
        changed.add('priority')
    if 'client' in data:
        proj['client'] = data['client']
        changed.add('client')
    if 'material_confirmed_date' in data:
        md = parse_input_date(data['material_confirmed_date'])
        proj['material_confirmed_date'] = md.isoformat() if md else ''
        if md:
            changed.add('material_confirmed_date')
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
        changed.add(ph)

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
    _sync_project_to_kanbanize(proj, changed)
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
        proj['image'] = f"uploads/{fname}"
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
    before = compute_schedule_map(projects)
    used_hours = 0
    for opid, items in before.items():
        for w, day_str, ph, hrs, prt in items:
            if w == worker and day_str == date_str:
                if opid == pid and ph == phase and (part is None or prt == part):
                    continue
                used_hours += hrs
    new_day, warn = move_phase_date(
        projects,
        pid,
        phase,
        day,
        worker,
        part,
        mode=mode,
        push_from=push_from,
        unblock=unblock,
        skip_block=skip_block,
        start_hour=start_hour if start_hour is not None else (used_hours if mode == 'split' else None),
    )
    if new_day is None:
        if isinstance(warn, dict):
            return jsonify({'blocked': warn}), 409
        return jsonify({'error': warn or 'No se pudo mover'}), 400
    resp = {'date': new_day, 'pid': pid, 'phase': phase}
    if warn and not ack_warning:
        resp['warning'] = warn
    return jsonify(resp)


@app.route('/check_move', methods=['POST'])
def check_move():
    data = request.get_json() or {}
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
    before = compute_schedule_map(projects)
    used_hours = 0
    for opid, items in before.items():
        for w, day_str, ph, hrs, prt in items:
            if w == worker and day_str == date_str:
                if opid == pid and ph == phase and (part is None or prt == part):
                    continue
                used_hours += hrs
    limit = HOURS_LIMITS.get(worker, HOURS_PER_DAY)
    free_hours = max(0, limit - used_hours)
    temp = copy.deepcopy(projects)
    new_day, warn = move_phase_date(
        temp,
        pid,
        phase,
        day,
        worker,
        part,
        save=False,
        mode="split",
        start_hour=start_hour if start_hour is not None else used_hours,
    )
    if new_day is None:
        return jsonify({'error': warn or 'No se pudo mover'}), 400

    schedule_after, _ = schedule_projects(copy.deepcopy(temp))
    after = {}
    for w, days in schedule_after.items():
        for dstr, tasks in days.items():
            for t in tasks:
                after.setdefault(t['pid'], []).append((w, dstr, t['phase'], t['hours'], t.get('part')))
    for lst in after.values():
        lst.sort()

    def build_map(mapping):
        res = {}
        for opid, items in mapping.items():
            for w, day_str, ph, hrs, prt in items:
                key = (opid, w, ph, prt)
                res.setdefault(key, []).append(date.fromisoformat(day_str))
        return res

    before_map = build_map(before)
    after_map = build_map(after)

    preview = []
    for t in schedule_after.get(worker, {}).get(date_str, []):
        proj = next((p for p in temp if p['id'] == t['pid']), None)
        if not proj:
            continue
        frozen = any(
            ft.get('phase') == t['phase'] and (t.get('part') is None or ft.get('part') == t.get('part'))
            for ft in proj.get('frozen_tasks', [])
        )
        preview.append(
            {
                'pid': t['pid'],
                'phase': t['phase'],
                'part': t.get('part'),
                'project': proj.get('name', ''),
                'client': proj.get('client', ''),
                'color': proj.get('color', ''),
                'priority': proj.get('priority', ''),
                'due_date': proj.get('due_date', ''),
                'start_date': proj.get('start_date', ''),
                'frozen': frozen,
            }
        )

    def is_contiguous(days):
        if not days:
            return True
        days.sort()
        prev = days[0]
        for d in days[1:]:
            if d != next_workday(prev):
                return False
            prev = d
        return True

    split = False
    moved_key = (pid, worker, phase, part)
    if moved_key not in after_map:
        for key in after_map:
            if key[0] == pid and key[2] == phase and key[3] == part:
                moved_key = key
                break
    if moved_key in after_map and not is_contiguous(after_map[moved_key]):
        split = True
    if not split and used_hours > 0:
        # Only flag a conflict if the target day already contains hours from
        # other phases; otherwise allow the move silently.
        split = True
    if not split:
        # Check if moving this phase would alter any other task on the target
        # worker, either by shifting it to different days or by adding/removing
        # tasks on that worker.
        related = set(
            k
            for k in before_map
            if k[1] == worker and not (k[0] == pid and k[2] == phase and k[3] == part)
        )
        related.update(
            k
            for k in after_map
            if k[1] == worker and not (k[0] == pid and k[2] == phase and k[3] == part)
        )
        for key in related:
            if before_map.get(key, []) != after_map.get(key, []):
                split = True
                break
    options = []
    auto = None
    if split:
        for opid, items in before.items():
            for w, day_str, ph, hrs, prt in items:
                if w == worker and day_str == date_str:
                    proj = next((p for p in projects if p['id'] == opid), None)
                    txt = f"{proj.get('name','')} - {ph}" if proj else ph
                    options.append({'pid': opid, 'phase': ph, 'part': prt, 'text': txt})
        if not options:
            future = []
            for opid, items in before.items():
                for w, day_str, ph, hrs, prt in items:
                    d = date.fromisoformat(day_str)
                    if w == worker and d > day:
                        future.append((d, opid, ph, prt))
            if future:
                future.sort()
                _, opid, ph, prt = future[0]
                auto = {'pid': opid, 'phase': ph, 'part': prt}
    resp = {'split': split, 'options': options, 'auto': auto, 'free': free_hours, 'preview': preview}
    if warn:
        resp['warning'] = warn
    return jsonify(resp)


def remove_project_and_preserve_schedule(projects, pid):
    """Remove a project and keep other projects' schedules intact."""
    mapping = compute_schedule_map(projects)
    removed = None
    for p in projects:
        if p['id'] == pid:
            removed = p
            break
    if not removed:
        return
    projects.remove(removed)
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


@app.route('/report_bug', methods=['POST'])
def report_bug():
    user = request.form.get('user')
    tab = request.form.get('tab')
    freq = request.form.get('freq')
    detail = request.form.get('detail', '').strip()
    if not all([user, tab, freq, detail]):
        return redirect(request.referrer or url_for('complete'))
    bugs = load_bugs()
    bug_id = len(bugs) + 1
    bug = {
        'id': bug_id,
        'user': user,
        'tab': tab,
        'freq': freq,
        'detail': detail,
        'date': datetime.now().isoformat(timespec='seconds'),
    }
    bugs.append(bug)
    save_bugs(bugs)
    send_bug_report(bug)
    return redirect(request.referrer or url_for('complete'))


@app.route('/delete_bug/<bid>', methods=['POST'])
def delete_bug(bid):
    bugs = load_bugs()
    bugs = [b for b in bugs if str(b.get('id')) != bid]
    save_bugs(bugs)
    return redirect(url_for('bug_list'))


@app.route('/toggle_freeze/<pid>/<phase>', methods=['POST'])
def toggle_freeze(pid, phase):
    projects = get_projects()
    proj = next((p for p in projects if p['id'] == pid), None)
    if not proj:
        return jsonify({'error': 'Proyecto no encontrado'}), 404
    frozen = proj.get('frozen_tasks', [])
    if any(t['phase'] == phase for t in frozen):
        proj['frozen_tasks'] = [t for t in frozen if t['phase'] != phase]
    else:
        schedule, _ = schedule_projects(projects)
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
    print("Raw body:", raw_body)

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
    lane = pick(card, 'lanename', 'laneName', 'lane')
    column = pick(card, 'columnname', 'columnName', 'column')

    print("Evento Kanbanize → lane:", lane, "column:", column, "cid:", cid)

    lane_norm = norm(lane)
    column_norm = norm(column)

    # Guardar tarjetas del lane Seguimiento compras
    if lane_norm == "seguimiento compras":
        cards = load_kanban_cards()
        cards = [
            c for c in cards
            if (c.get('card', {}).get('taskid') or c.get('card', {}).get('cardId') or c.get('card', {}).get('id')) != cid
        ]
        cards.append({'timestamp': payload_timestamp, 'card': card})
        save_kanban_cards(cards)
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
        for p in projects:
            if p.get('kanban_id') == cid or (name_candidates and p.get('name') in name_candidates):
                if cid and not p.get('kanban_id'):
                    p['kanban_id'] = cid
                pid = p['id']
                break
        if pid:
            remove_project_and_preserve_schedule(projects, pid)
            save_projects(projects)
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
    for k in ['Horas', 'MATERIAL', 'CALDERERÍA']:
        custom.pop(k, None)
    card['customFields'] = custom

    deadline_str = card.get('deadline')
    pedido_str = custom.get('Fecha pedido')
    if deadline_str:
        due_date_obj = parse_kanban_date(deadline_str)
        due_confirmed_flag = True
    else:
        due_date_obj = parse_kanban_date(pedido_str)
        due_confirmed_flag = False
    mat_str = custom.get('Fecha material confirmado')
    material_date_obj = parse_kanban_date(mat_str)

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

    prep_hours = obtener_duracion('Horas Preparación')
    mont_hours = obtener_duracion('Horas Montaje')
    sold_hours = obtener_duracion('Horas Soldadura')
    pint_hours = obtener_duracion('Horas Acabado')
    mont_final_hours = obtener_duracion('Horas Montaje Final')
    sold_int_hours = obtener_duracion('Horas Soldadura Interior')
    auto_prep = False
    if (
        prep_hours <= 0
        and mont_hours <= 0
        and sold_hours <= 0
        and pint_hours <= 0
        and mont_final_hours <= 0
        and sold_int_hours <= 0
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
    if sold_hours > 0:
        fases.append({'nombre': 'soldar', 'duracion': sold_hours})
    if sold_int_hours > 0:
        fases.append({'nombre': 'soldadura interior', 'duracion': sold_int_hours})
    if pint_hours > 0:
        fases.append({'nombre': 'pintar', 'duracion': pint_hours})
    if mont_final_hours > 0:
        fases.append({'nombre': 'montaje final', 'duracion': mont_final_hours})
    auto_flags = {f['nombre']: True for f in fases if f.get('auto')}

    task_id = card.get('taskid') or card.get('cardId') or card.get('id')
    nombre_proyecto = (
        card.get('customCardId')
        or card.get('effectiveCardId')
        or card.get('title')
        or f"Kanbanize-{task_id or uuid.uuid4()}"
    )
    cliente = card.get('title') or "Sin cliente"
    kanban_priority = (card.get('priority') or '').lower()
    priority_map = {
        'critical': 'Alta',
        'high': 'Alta',
        'average': 'Media',
        'low': 'Baja',
    }
    proj_priority = priority_map.get(kanban_priority, 'Sin prioridad')

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

    if existing:
        changed = False
        if existing.get('kanban_id') != task_id:
            existing['kanban_id'] = task_id
            changed = True
        if existing.get('name') != nombre_proyecto:
            existing['name'] = nombre_proyecto
            changed = True
        if existing.get('client') != cliente:
            existing['client'] = cliente
            changed = True
        if existing.get('priority') != proj_priority:
            existing['priority'] = proj_priority
            changed = True
        if not existing.get('color') or not re.fullmatch(r"#[0-9A-Fa-f]{6}", existing.get('color', '')):
            existing['color'] = _next_api_color()
            changed = True
        if due_date_obj:
            iso = due_date_obj.isoformat()
            if existing.get('due_date') != iso or existing.get('due_confirmed') != due_confirmed_flag:
                existing['due_date'] = iso
                existing['due_confirmed'] = due_confirmed_flag
                existing['due_warning'] = True
                changed = True
        elif existing.get('due_date') or existing.get('due_confirmed'):
            existing['due_date'] = ''
            existing['due_confirmed'] = False
            changed = True
        if material_date_obj and existing.get('material_confirmed_date') != material_date_obj.isoformat():
            existing['material_confirmed_date'] = material_date_obj.isoformat()
            changed = True
        if image_path and existing.get('image') != image_path:
            existing['image'] = image_path
            changed = True
        if existing.get('kanban_attachments') != kanban_files:
            existing['kanban_attachments'] = kanban_files
            changed = True
        existing_phases = existing.setdefault('phases', {})
        existing_assigned = existing.setdefault('assigned', {})
        existing_auto = existing.setdefault('auto_hours', {})
        restricted = {
            'recepcionar material',
            'montar',
            'soldar',
            'pintar',
            'montaje final',
            'soldadura interior',
        }
        # Si la fase de recepcionar material fue generada automáticamente
        # (1h en rojo) y ahora la tarjeta tiene horas reales, eliminarla o
        # actualizarla según corresponda.
        had_auto_prep = existing_auto.get('recepcionar material')
        incoming_auto_prep = new_auto.get('recepcionar material')
        incoming_prep_hours = new_phases.get('recepcionar material')
        if had_auto_prep and not incoming_auto_prep:
            if incoming_prep_hours and incoming_prep_hours > 0:
                existing_phases['recepcionar material'] = incoming_prep_hours
            else:
                existing_phases.pop('recepcionar material', None)
                existing_assigned.pop('recepcionar material', None)
            existing_auto.pop('recepcionar material', None)
            changed = True
        for ph, hours in new_phases.items():
            if ph not in existing_phases:
                if hours > 0:
                    existing_phases[ph] = hours
                    existing_assigned[ph] = UNPLANNED
                    if new_auto.get(ph):
                        existing_auto[ph] = True
                    changed = True
                continue
            if ph in restricted:
                if existing_phases.get(ph) in [0, '', None] and existing_phases.get(ph) != hours:
                    existing_phases[ph] = hours
                    changed = True
            elif existing_phases.get(ph) != hours:
                existing_phases[ph] = hours
                changed = True
            if ph not in existing_assigned:
                existing_assigned[ph] = UNPLANNED
                changed = True
            if new_auto.get(ph):
                if not existing_auto.get(ph):
                    existing_auto[ph] = True
                    changed = True
            elif existing_auto.pop(ph, None) is not None:
                changed = True
        if changed:
            save_projects(projects)
    else:
        project = {
            'id': str(uuid.uuid4()),
            'name': nombre_proyecto,
            'client': cliente,
            'start_date': date.today().isoformat(),
            'due_date': due_date_obj.isoformat() if due_date_obj else '',
            'material_confirmed_date': material_date_obj.isoformat() if material_date_obj else '',
            'priority': proj_priority,
            'color': _next_api_color(),
            'phases': new_phases,
            'assigned': {f['nombre']: UNPLANNED for f in fases},
            'auto_hours': new_auto,
            'image': image_path,
            'kanban_attachments': kanban_files,
            'planned': False,
            'source': 'api',
            'kanban_id': task_id,
            'due_confirmed': due_confirmed_flag,
            'due_warning': bool(due_date_obj),
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
        return jsonify({"mensaje": "Proyecto creado"}), 200
    else:
        return jsonify({"mensaje": "Proyecto actualizado"}), 200


@app.route('/bugs')
def bug_list():
    bugs = load_bugs()
    return render_template('bugs.html', bugs=bugs)


if __name__ == '__main__':
    sync_all_cards()
    print("Rutas registradas:")
    for rule in app.url_map.iter_rules():
        print(f"{sorted(rule.methods)}  {rule.rule}")
    app.run(debug=True, host='0.0.0.0', port=9000)
