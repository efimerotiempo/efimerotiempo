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
load_milestones = _schedule_mod.load_milestones
save_milestones = _schedule_mod.save_milestones
load_vacations = _schedule_mod.load_vacations
save_vacations = _schedule_mod.save_vacations
load_daily_hours = _schedule_mod.load_daily_hours
save_daily_hours = _schedule_mod.save_daily_hours
PRIORITY_ORDER = _schedule_mod.PRIORITY_ORDER
PHASE_ORDER = _schedule_mod.PHASE_ORDER
WORKERS = _schedule_mod.WORKERS
IGOR_END = _schedule_mod.IGOR_END
find_worker_for_phase = _schedule_mod.find_worker_for_phase
compute_schedule_map = _schedule_mod.compute_schedule_map
previous_phase_end = _schedule_mod.previous_phase_end
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

app = Flask(__name__)

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
    if request.endpoint in ("static", "kanbanize_webhook"):
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
MIN_DATE = date(2024, 1, 1)
MAX_DATE = date(2026, 12, 31)
UPLOAD_FOLDER = os.path.join('static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
DATA_DIR = os.environ.get('EFIMERO_DATA_DIR', 'data')
BUGS_FILE = os.path.join(DATA_DIR, 'bugs.json')
KANBAN_CARDS_FILE = os.path.join(DATA_DIR, 'kanban_cards.json')
KANBAN_PREFILL_FILE = os.path.join(DATA_DIR, 'kanban_prefill.json')

# Kanbanize integration constants
KANBANIZE_API_KEY = os.environ.get('KANBANIZE_API_KEY', 'jpQfMzS8AzdyD70zLkilBjP0Uig957mOATuM0BOE')
KANBANIZE_BASE_URL = 'https://caldereriacpk.kanbanize.com'
KANBANIZE_BOARD_TOKEN = os.environ.get('KANBANIZE_BOARD_TOKEN', '682d829a0aafe44469o50acd')
KANBANIZE_BOARD_ID = os.environ.get('KANBANIZE_BOARD_ID', '1')


def active_workers(today=None):
    """Return the list of workers shown in the calendar."""
    if today is None:
        today = date.today()
    workers = list(WORKERS.keys())
    if today >= IGOR_END and 'Igor' in workers:
        workers.remove('Igor')
    return workers


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


def format_dd_mm(value):
    """Return 'dd-mm' string for a date or date string."""
    if not value:
        return ''
    if isinstance(value, str):
        value = parse_input_date(value)
    if isinstance(value, date):
        return f"{value.day:02d}-{value.month:02d}"
    return ''


def planning_status(schedule):
    """Return mapping pid -> True if fully scheduled."""
    status = {}
    unplanned = schedule.get(UNPLANNED, {})
    for tasks in unplanned.values():
        for t in tasks:
            status[t['pid']] = False
    for worker, days in schedule.items():
        if worker == UNPLANNED:
            continue
        for tasks in days.values():
            for t in tasks:
                status.setdefault(t['pid'], True)
    return status


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
    if os.path.exists(KANBAN_CARDS_FILE):
        with open(KANBAN_CARDS_FILE, 'r') as f:
            return json.load(f)
    return []


def save_kanban_cards(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(KANBAN_CARDS_FILE, 'w') as f:
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


def _decode_json(value):
    """Try to parse *value* as JSON, ignoring trailing text."""
    while isinstance(value, (bytes, str)):
        try:
            if isinstance(value, bytes):
                value = value.decode('utf-8')
            value, idx = json.JSONDecoder().raw_decode(value)
        except Exception:
            break
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


def attempt_reorganize(projects, pid, phase, days=30):
    """Try to move ``phase`` of project ``pid`` to an earlier slot.

    Return the new first day of the phase if it changes, otherwise ``None``.
    """
    mapping = compute_schedule_map(projects)
    tasks = [t for t in mapping.get(pid, []) if t[2] == phase]
    if not tasks:
        return False
    orig_start = date.fromisoformat(tasks[0][1])
    proj = next((p for p in projects if p['id'] == pid), None)
    if not proj:
        return False
    base = date.fromisoformat(proj['start_date'])
    best = orig_start
    best_date = base
    for delta in range(1, days + 1):
        cand = base - timedelta(days=delta)
        temp = copy.deepcopy(projects)
        for tp in temp:
            if tp['id'] == pid:
                tp['start_date'] = cand.isoformat()
                if tp.get('segment_starts'):
                    tp['segment_starts'].pop(phase, None)
                break
        new_map = compute_schedule_map(temp)
        new_tasks = [t for t in new_map.get(pid, []) if t[2] == phase]
        if not new_tasks:
            continue
        start2 = date.fromisoformat(new_tasks[0][1])
        if start2 < best:
            best = start2
            best_date = cand
    if best < orig_start:
        proj['start_date'] = best_date.isoformat()
        if proj.get('segment_starts'):
            proj['segment_starts'].pop(phase, None)
        save_projects(projects)
        return best.isoformat()
    return None


def move_phase_date(projects, pid, phase, new_date, worker=None, part=None):
    """Move ``phase`` of project ``pid`` so it starts on ``new_date``.

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
    if proj.get('frozen'):
        return None, 'Proyecto congelado'

    if worker and phase not in WORKERS.get(worker, []):
        return None, 'Trabajador sin esa fase'
    vac_map = _schedule_mod._build_vacation_map()
    if worker and worker != 'Irene' and new_date in vac_map.get(worker, set()):
        return None, 'Vacaciones en esa fecha'
    prev_end = previous_phase_end(projects, pid, phase, part)
    if prev_end and new_date <= prev_end:
        return None, 'No puede adelantarse a la fase previa'
    # Prepare a deep copy to test the new start without modifying real data yet
    temp = copy.deepcopy(projects)
    tproj = next((p for p in temp if p['id'] == pid), None)
    if part is None and not isinstance(tproj['phases'].get(phase), list):
        seg_starts = tproj.setdefault('segment_starts', {}).setdefault(phase, [None])
        seg_starts[0] = new_date.isoformat()
        if worker:
            tproj.setdefault('assigned', {})[phase] = worker
    else:
        seg_starts = tproj.setdefault('segment_starts', {}).setdefault(
            phase, [None] * len(tproj['phases'][phase])
        )
        idx = part if part is not None else 0
        if idx < len(seg_starts):
            seg_starts[idx] = new_date.isoformat()
        if worker:
            seg_workers = tproj.setdefault('segment_workers', {}).setdefault(
                phase, [None] * len(tproj['phases'][phase])
            )
            if idx >= len(seg_workers):
                seg_workers.extend([None] * (idx + 1 - len(seg_workers)))
            seg_workers[idx] = worker
    if worker:
        tproj['planned'] = worker != UNPLANNED

    new_map = compute_schedule_map(temp)
    new_tasks = [t for t in new_map.get(pid, []) if t[2] == phase]
    if part is not None:
        new_tasks = [t for t in new_tasks if t[4] == part]
    if not new_tasks or new_tasks[0][1] != new_date.isoformat():
        return None, 'El d\u00eda seleccionado no estaba disponible'

    # Apply the change to the real project list now that we know it's valid
    if part is None and not isinstance(proj['phases'].get(phase), list):
        seg_starts = proj.setdefault('segment_starts', {}).setdefault(phase, [None])
        seg_starts[0] = new_date.isoformat()
        if worker:
            proj.setdefault('assigned', {})[phase] = worker
    else:
        seg_starts = proj.setdefault('segment_starts', {}).setdefault(
            phase, [None] * len(proj['phases'][phase])
        )
        idx = part if part is not None else 0
        if idx < len(seg_starts):
            seg_starts[idx] = new_date.isoformat()
        if worker:
            seg_workers = proj.setdefault('segment_workers', {}).setdefault(
                phase, [None] * len(proj['phases'][phase])
            )
            if idx >= len(seg_workers):
                seg_workers.extend([None] * (idx + 1 - len(seg_workers)))
            seg_workers[idx] = worker
    if worker:
        proj['planned'] = worker != UNPLANNED
    save_projects(projects)
    return new_date.isoformat(), None


def get_projects():
    projects = load_projects()
    changed = False
    color_index = 0
    assigned_projects = []
    for p in projects:
        if not p.get('color'):
            p['color'] = COLORS[color_index % len(COLORS)]
            color_index += 1
            changed = True

        p.setdefault('frozen', False)
        p.setdefault('frozen_tasks', [])
        p.setdefault('blocked', False)
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

        p.setdefault('assigned', {})
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
        fields = fields_raw
    else:
        fields = {}

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

    phases = {}
    val = h('Horas Acabado')
    if val:
        phases['pintar'] = val
    val = h('Horas Montaje')
    if val:
        phases['montar'] = val
    val = h('Horas Preparación')
    if val:
        phases['recepcionar material'] = val
    val = h('Horas Soldadura')
    if val:
        phases['soldar'] = val

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
        'image': None,
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
    plan_map = planning_status(schedule)
    if date.today() >= IGOR_END:
        schedule.pop('Igor', None)
    for p in projects:
        if p.get('due_date'):
            try:
                p['met'] = date.fromisoformat(p['end_date']) <= date.fromisoformat(p['due_date'])
            except ValueError:
                p['met'] = False
        else:
            p['met'] = False
    milestones = load_milestones()
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
                    t for t in tasks
                    if (not project_filter or project_filter.lower() in t['project'].lower())
                    and (not client_filter or client_filter.lower() in t['client'].lower())
                ]

    points = split_markers(schedule)

    today = date.today()
    start = today - timedelta(days=90)
    end = today + timedelta(days=180)
    days, cols, week_spans = build_calendar(start, end)
    hours_map = load_daily_hours()

    milestone_map = {}
    for m in milestones:
        milestone_map.setdefault(m['date'], []).append(m['description'])

    project_map = {p['id']: p for p in projects}
    start_map = phase_start_map(projects)

    return render_template(
        'index.html',
        schedule=schedule,
        cols=cols,
        week_spans=week_spans,
        conflicts=conflicts,
        workers=active_workers(today),
        today=today,
        project_filter=project_filter,
        client_filter=client_filter,
        milestones=milestone_map,
        project_data=project_map,
        start_map=start_map,
        phases=PHASE_ORDER,
        hours=hours_map,
        split_points=points,
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
        schedule, _ = schedule_projects(projects)
        color = COLORS[len(projects) % len(COLORS)]
        due = parse_input_date(data['due_date'])
        project = {
            'id': str(uuid.uuid4()),
            'name': data['name'],
            'client': data['client'],
            'start_date': date.today().isoformat(),
            'due_date': due.isoformat() if due else '',
            'priority': data.get('priority', 'Sin prioridad'),
            'color': color,
            'phases': {},
            'assigned': {},
            'image': image_path,
            'planned': 'planned' in data,
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
                        project['assigned'][phase] = find_worker_for_phase(
                            phase, schedule, project['priority']
                        )
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
                    project['assigned'][phase] = find_worker_for_phase(
                        phase, schedule, project['priority']
                    )
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


@app.route('/add_milestone', methods=['POST'])
def add_milestone():
    """Add a milestone with a unique id."""
    milestones = load_milestones()
    mdate = parse_input_date(request.form['date'])
    milestones.append({
        'id': str(uuid.uuid4()),
        'description': request.form['description'],
        'date': mdate.isoformat() if mdate else '',
    })
    save_milestones(milestones)
    next_url = request.form.get('next') or url_for('complete')
    return redirect(next_url)


@app.route('/milestones')
def milestone_list():
    milestones = load_milestones()
    return render_template('milestones.html', milestones=milestones)


@app.route('/delete_milestone/<mid>', methods=['POST'])
def delete_milestone(mid):
    milestones = load_milestones()
    milestones = [m for m in milestones if m.get('id') != mid]
    save_milestones(milestones)
    next_url = request.form.get('next') or url_for('milestone_list')
    return redirect(next_url)


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


@app.route('/complete', methods=['GET', 'POST'])
def complete():
    projects = get_projects()
    if request.method == 'POST':
        data = request.form
        file = request.files.get('image')
        image_path = None
        if file and file.filename:
            ext = os.path.splitext(secure_filename(file.filename))[1]
            fname = f"{uuid.uuid4()}{ext}"
            save_path = os.path.join(UPLOAD_FOLDER, fname)
            file.save(save_path)
            image_path = f"uploads/{fname}"
        schedule, _ = schedule_projects(projects)
        color = COLORS[len(projects) % len(COLORS)]
        due = parse_input_date(data['due_date'])
        project = {
            'id': str(uuid.uuid4()),
            'name': data['name'],
            'client': data['client'],
            'start_date': date.today().isoformat(),
            'due_date': due.isoformat() if due else '',
            'priority': data.get('priority', 'Sin prioridad'),
            'color': color,
            'phases': {},
            'assigned': {},
            'image': image_path,
            'planned': 'planned' in data,
        }
        for phase in PHASE_ORDER:
            value_h = data.get(phase)
            value_d = data.get(f"{phase}_days")
            if phase == 'pedidos':
                if value_h:
                    val = parse_input_date(value_h)
                    if val:
                        project['phases'][phase] = val.isoformat()
                        project['assigned'][phase] = find_worker_for_phase(
                            phase, schedule, project['priority']
                        )
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
                    project['assigned'][phase] = find_worker_for_phase(
                        phase, schedule, project['priority']
                    )
        projects.append(project)
        save_projects(projects)
        return redirect(url_for('complete', highlight=project['id']))

    schedule, conflicts = schedule_projects(projects)
    plan_map = planning_status(schedule)
    if date.today() >= IGOR_END:
        schedule.pop('Igor', None)
    for p in projects:
        if p.get('due_date'):
            try:
                p['met'] = date.fromisoformat(p['end_date']) <= date.fromisoformat(p['due_date'])
            except ValueError:
                p['met'] = False
        else:
            p['met'] = False
    milestones = load_milestones()
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
                    t for t in tasks
                    if (not project_filter or project_filter.lower() in t['project'].lower())
                    and (not client_filter or client_filter.lower() in t['client'].lower())
                ]
        filtered_projects = [
            p for p in projects
            if (not project_filter or project_filter.lower() in p['name'].lower())
            and (not client_filter or client_filter.lower() in p['client'].lower())
        ]
    else:
        filtered_projects = projects

    if sort_option == 'name':
        filtered_projects.sort(key=lambda p: p['name'].lower())
    else:
        filtered_projects.sort(key=lambda p: orig_order[p['id']], reverse=True)

    filtered_projects = expand_for_display(filtered_projects)

    points = split_markers(schedule)

    today = date.today()
    start = today - timedelta(days=90)
    end = today + timedelta(days=180)
    days, cols, week_spans = build_calendar(start, end)
    hours_map = load_daily_hours()
    milestone_map = {}
    for m in milestones:
        milestone_map.setdefault(m['date'], []).append(m['description'])

    project_map = {p['id']: p for p in projects}
    start_map = phase_start_map(projects)

    return render_template(
        'complete.html',
        schedule=schedule,
        cols=cols,
        week_spans=week_spans,
        conflicts=conflicts,
        workers=active_workers(today),
        project_filter=project_filter,
        client_filter=client_filter,
        projects=filtered_projects,
        sort_option=sort_option,
        today=today,
        priorities=list(PRIORITY_ORDER.keys()),
        phases=PHASE_ORDER,
        all_workers=active_workers(today),
        milestones=milestone_map,
        project_data=project_map,
        start_map=start_map,
        hours=hours_map,
        plan_map=plan_map,
        split_points=points,
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
            p.setdefault('assigned', {})[phase] = request.form['worker']
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
    save_projects(projects)
    if request.is_json:
        return '', 204
    return redirect(next_url)


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
    if proj.get('due_date'):
        try:
            if new_date > date.fromisoformat(proj['due_date']):
                return jsonify({'error': 'Inicio posterior a la fecha límite'}), 400
        except ValueError:
            pass
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
        if hours <= 0:
            raise ValueError
    except Exception:
        return jsonify({'error': 'Horas inválidas'}), 400
    projects = get_projects()
    proj = next((p for p in projects if p['id'] == pid), None)
    if not proj:
        return jsonify({'error': 'Proyecto no encontrado'}), 404
    proj.setdefault('phases', {})
    prev_val = proj['phases'].get(phase)
    was_list = isinstance(prev_val, list)
    proj['phases'][phase] = hours
    if was_list:
        if proj.get('segment_starts'):
            proj['segment_starts'].pop(phase, None)
            if not proj['segment_starts']:
                proj.pop('segment_starts')
        if proj.get('segment_workers'):
            proj['segment_workers'].pop(phase, None)
            if not proj['segment_workers']:
                proj.pop('segment_workers')
    frozen = proj.get('frozen', False)
    if frozen:
        proj['frozen'] = False
    sched, _ = schedule_projects(projects)
    if frozen:
        frozen_tasks = []
        last = None
        for w, days in sched.items():
            for d, tasks in days.items():
                for t in tasks:
                    if t['pid'] == pid:
                        item = t.copy()
                        item['worker'] = w
                        item['day'] = d
                        item['frozen'] = True
                        frozen_tasks.append(item)
                        dt = date.fromisoformat(d)
                        if not last or dt > last:
                            last = dt
        proj['frozen'] = True
        proj['frozen_tasks'] = frozen_tasks
        if last:
            proj['end_date'] = last.isoformat()
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

    if 'start_date' in data:
        sd = parse_input_date(data['start_date'])
        if sd:
            if proj.get('due_date'):
                try:
                    if sd > date.fromisoformat(proj['due_date']):
                        return jsonify({'error': 'Inicio posterior a la fecha límite'}), 400
                except ValueError:
                    pass
            proj['start_date'] = sd.isoformat()
    if 'due_date' in data:
        dd = parse_input_date(data['due_date'])
        proj['due_date'] = dd.isoformat() if dd else ''
    if 'priority' in data:
        proj['priority'] = data['priority']

    was_frozen = proj.get('frozen', False)
    if was_frozen:
        proj['frozen'] = False

    for ph, val in (data.get('phases') or {}).items():
        try:
            hours = int(val)
            if hours <= 0:
                continue
        except Exception:
            continue
        proj.setdefault('phases', {})
        prev = proj['phases'].get(ph)
        was_list = isinstance(prev, list)
        proj['phases'][ph] = hours
        if was_list:
            if proj.get('segment_starts'):
                proj['segment_starts'].pop(ph, None)
                if not proj['segment_starts']:
                    proj.pop('segment_starts')
            if proj.get('segment_workers'):
                proj['segment_workers'].pop(ph, None)
                if not proj['segment_workers']:
                    proj.pop('segment_workers')

    if data.get('phase_starts'):
        seg = proj.setdefault('segment_starts', {})
        for ph, d in data['phase_starts'].items():
            val = parse_input_date(d)
            if val:
                seg[ph] = [val.isoformat()]

    if data.get('workers'):
        ass = proj.setdefault('assigned', {})
        for ph, w in data['workers'].items():
            ass[ph] = w

    sched, _ = schedule_projects(projects)
    if was_frozen:
        frozen_tasks = []
        last = None
        for w, days in sched.items():
            for d, tasks in days.items():
                for t in tasks:
                    if t['pid'] == pid:
                        item = t.copy()
                        item['worker'] = w
                        item['day'] = d
                        item['frozen'] = True
                        frozen_tasks.append(item)
                        dt = date.fromisoformat(d)
                        if not last or dt > last:
                            last = dt
        proj['frozen'] = True
        proj['frozen_tasks'] = frozen_tasks
        if last:
            proj['end_date'] = last.isoformat()

    save_projects(projects)
    return jsonify({'status': 'ok'})


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


@app.route('/reorganize', methods=['POST'])
def reorganize_phase():
    data = request.get_json() or request.form
    pid = data.get('pid')
    phase = data.get('phase')
    if not pid or not phase:
        return '', 400
    projects = get_projects()
    new_day = attempt_reorganize(projects, pid, phase)
    if new_day:
        return jsonify({'date': new_day, 'pid': pid, 'phase': phase, 'part': part})
    return '', 204


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
                save_projects(projects)
            break
    return '', 204


@app.route('/split_phase', methods=['POST'])
def split_phase_route():
    data = request.get_json() or request.form
    pid = data.get('pid')
    phase = data.get('phase')
    date_str = data.get('date')
    if not pid or not phase or not date_str:
        return '', 400
    try:
        cut = date.fromisoformat(date_str)
    except Exception:
        return '', 400
    projects = get_projects()
    proj = next((p for p in projects if p['id'] == pid), None)
    if not proj or phase not in proj.get('phases', {}):
        return '', 400

    mapping = compute_schedule_map(projects)
    tasks = [t for t in mapping.get(pid, []) if t[2] == phase]
    part1 = (
        sum(h for _, d, _, h, _ in tasks if date.fromisoformat(d) < cut)
        if tasks
        else 0
    )
    part2 = (
        sum(h for _, d, _, h, _ in tasks if date.fromisoformat(d) >= cut)
        if tasks
        else 0
    )

    if part1 == 0 or part2 == 0:
        val = proj['phases'][phase]
        total = sum(int(v) for v in val) if isinstance(val, list) else int(val)
        part1 = total // 2
        part2 = total - part1

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
    if not pid or not phase or not date_str:
        return '', 400
    try:
        day = date.fromisoformat(date_str)
    except Exception:
        return '', 400
    projects = get_projects()
    new_day, msg = move_phase_date(projects, pid, phase, day, worker, part)
    if new_day is None:
        return jsonify({'error': msg or 'No se pudo mover'}), 400
    response = {'date': new_day, 'pid': pid, 'phase': phase}
    if msg:
        response['message'] = msg
    return jsonify(response)


@app.route('/delete_project/<pid>', methods=['POST'])
def delete_project(pid):
    projects = get_projects()
    removed = None
    for p in projects:
        if p['id'] == pid:
            removed = p
            break
    if removed:
        projects.remove(removed)
        save_projects(projects)
        extras = load_extra_conflicts()
        msg = f"Proyecto {removed['name']} eliminado; la planificación se reorganizó"
        extras.append({
            'id': str(uuid.uuid4()),
            'project': removed['name'],
            'client': removed['client'],
            'message': msg,
            'key': f'del-{pid}',
        })
        save_extra_conflicts(extras)
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


@app.route('/toggle_freeze/<pid>', methods=['POST'])
def toggle_freeze(pid):
    projects = get_projects()
    proj = next((p for p in projects if p['id'] == pid), None)
    if not proj:
        return jsonify({'error': 'Proyecto no encontrado'}), 404
    if proj.get('frozen'):
        proj['frozen'] = False
        proj.pop('frozen_tasks', None)
    else:
        schedule, _ = schedule_projects(projects)
        frozen = []
        last = None
        for w, days in schedule.items():
            for day, tasks in days.items():
                for t in tasks:
                    if t['pid'] == pid:
                        item = t.copy()
                        item['worker'] = w
                        item['day'] = day
                        item['frozen'] = True
                        frozen.append(item)
                        d = date.fromisoformat(day)
                        if not last or d > last:
                            last = d
        proj['frozen'] = True
        proj['frozen_tasks'] = frozen
        if last:
            proj['end_date'] = last.isoformat()
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

    # Detect the last date contained anywhere in the request body. Kanbanize
    # sends extra data after the JSON payload where the final line represents
    # the project's due date, e.g. "2025-07-21".
    raw_text = raw_body.decode('utf-8', 'ignore') if isinstance(raw_body, bytes) else str(raw_body)
    date_matches = re.findall(r"\d{4}-\d{2}-\d{2}", raw_text)
    due_date_obj = parse_input_date(date_matches[-1]) if date_matches else date.today()

    try:
        data = request.get_json(force=True)
        raw_payload = data.get("kanbanize_payload", "")

        # Extraer el primer bloque JSON válido entre llaves
        match = re.search(r"\{.*\}", raw_payload)
        if not match:
            print("No se encontró JSON válido en kanbanize_payload")
            return jsonify({'error': 'JSON inválido'}), 400

        try:
            clean_payload = match.group(0)
            inner_data = json.loads(clean_payload)
        except Exception as e:
            print("Error al parsear JSON interno:", e)
            return jsonify({'error': 'Error al parsear JSON'}), 400
        card = inner_data.get("card", {})
        payload_timestamp = inner_data.get("timestamp")
    except Exception as e:
        print("Error procesando payload:", e)
        return jsonify({'error': 'Error al procesar datos'}), 400

    print("Tarjeta recibida:")
    print(card)

    custom = card.get('customFields', {})

    def obtener_duracion(campo):
        try:
            valor = custom.get(campo)
            return int(valor) if valor not in [None, ""] else 0
        except Exception:
            return 0

    fases = [
        {'nombre': 'montar', 'duracion': obtener_duracion('Horas Montaje')},
        {'nombre': 'soldar', 'duracion': obtener_duracion('Horas Soldadura')},
        {'nombre': 'pintar', 'duracion': obtener_duracion('Horas Acabado')},
    ]

    nombre_proyecto = card.get('customCardId') or "Sin datos"
    cliente = card.get('title') or "Sin datos"

    projects = load_projects()
    existing = next((p for p in projects
                     if p.get('source') == 'api' and p.get('name') == nombre_proyecto), None)

    new_phases = {f['nombre']: f['duracion'] for f in fases}

    if existing:
        changed = False
        if existing.get('client') != cliente:
            existing['client'] = cliente
            changed = True
        if existing.get('due_date') != due_date_obj.isoformat():
            existing['due_date'] = due_date_obj.isoformat()
            changed = True
        for ph, hours in new_phases.items():
            if existing.get('phases', {}).get(ph) != hours:
                existing.setdefault('phases', {})[ph] = hours
                changed = True
            if ph not in existing.get('assigned', {}):
                existing.setdefault('assigned', {})[ph] = UNPLANNED
                changed = True
        if changed:
            save_projects(projects)
    else:
        project = {
            'id': str(uuid.uuid4()),
            'name': nombre_proyecto,
            'client': cliente,
            'start_date': date.today().isoformat(),
            'due_date': due_date_obj.isoformat(),
            'priority': 'Sin prioridad',
            'color': None,
            'phases': new_phases,
            'assigned': {f['nombre']: UNPLANNED for f in fases},
            'image': None,
            'planned': False,
            'source': 'api',
        }
        if project.get('color') is None:
            project['color'] = COLORS[len(projects) % len(COLORS)]
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
    """Show table with all recorded bugs."""
    bugs = load_bugs()
    return render_template('bugs.html', bugs=bugs)


@app.route('/kanbanize')
def kanbanize_list():
    """Display all received Kanbanize cards."""
    cards = load_kanban_cards()
    return render_template('kanbanize.html', cards=cards)


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
