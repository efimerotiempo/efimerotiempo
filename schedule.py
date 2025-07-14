from datetime import date, timedelta
import json
import os
import copy

DATA_DIR = os.environ.get('EFIMERO_DATA_DIR', 'data')
PROJECTS_FILE = os.path.join(DATA_DIR, 'projects.json')
DISMISSED_FILE = os.path.join(DATA_DIR, 'dismissed_conflicts.json')
EXTRA_CONFLICTS_FILE = os.path.join(DATA_DIR, 'conflicts.json')
MILESTONES_FILE = os.path.join(DATA_DIR, 'milestones.json')
VACATIONS_FILE = os.path.join(DATA_DIR, 'vacations.json')
DAILY_HOURS_FILE = os.path.join(DATA_DIR, 'daily_hours.json')

PHASE_ORDER = [
    'dibujo',
    'pedidos',
    'recepcionar material',
    'montar',
    'soldar',
    'pintar',
    'mecanizar',
    'tratamiento',
]
PRIORITY_ORDER = {'Alta': 1, 'Media': 2, 'Baja': 3, 'Sin prioridad': 4}

WORKERS = {
    'Pilar': ['dibujo'],
    'Joseba 1': ['dibujo'],
    'Irene': ['pedidos'],
    'Joseba 2': ['montar', 'soldar'],
    'Mikel': ['montar', 'soldar'],
    'Iban': ['montar', 'soldar'],
    'Naparra': ['montar', 'soldar'],
    'Unai': ['montar', 'soldar'],
    'Fabio': ['soldar', 'montar'],
    'Beltxa': ['soldar', 'montar'],
    'Igor': ['soldar'],
    'Albi': ['recepcionar material', 'soldar', 'montar'],
    'Eneko': ['pintar', 'montar', 'soldar'],
    'Mecanizar': ['mecanizar'],
    'Tratamiento': ['tratamiento'],
}

HOURS_PER_DAY = 8
HOURS_LIMITS = {w: HOURS_PER_DAY for w in WORKERS}
HOURS_LIMITS['Irene'] = float('inf')
HOURS_LIMITS['Mecanizar'] = float('inf')
HOURS_LIMITS['Tratamiento'] = float('inf')
WEEKEND = {5, 6}  # Saturday=5, Sunday=6 in weekday()


def load_projects():
    if os.path.exists(PROJECTS_FILE):
        with open(PROJECTS_FILE, 'r') as f:
            return json.load(f)
    return []


def save_projects(projects):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(PROJECTS_FILE, 'w') as f:
        json.dump(projects, f)


def load_dismissed():
    if os.path.exists(DISMISSED_FILE):
        with open(DISMISSED_FILE, 'r') as f:
            return json.load(f)
    return []


def save_dismissed(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(DISMISSED_FILE, 'w') as f:
        json.dump(data, f)


def load_extra_conflicts():
    if os.path.exists(EXTRA_CONFLICTS_FILE):
        with open(EXTRA_CONFLICTS_FILE, 'r') as f:
            return json.load(f)
    return []


def save_extra_conflicts(conflicts):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(EXTRA_CONFLICTS_FILE, 'w') as f:
        json.dump(conflicts, f)


def load_milestones():
    if os.path.exists(MILESTONES_FILE):
        with open(MILESTONES_FILE, 'r') as f:
            return json.load(f)
    return []


def save_milestones(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(MILESTONES_FILE, 'w') as f:
        json.dump(data, f)


def load_vacations():
    if os.path.exists(VACATIONS_FILE):
        with open(VACATIONS_FILE, 'r') as f:
            return json.load(f)
    return []


def save_vacations(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(VACATIONS_FILE, 'w') as f:
        json.dump(data, f)


def load_daily_hours():
    """Return a mapping of ISO date strings to workday hours."""
    if os.path.exists(DAILY_HOURS_FILE):
        with open(DAILY_HOURS_FILE, 'r') as f:
            return json.load(f)
    return {}


def save_daily_hours(hours):
    """Persist the per-day hours map."""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(DAILY_HOURS_FILE, 'w') as f:
        json.dump(hours, f)


BUGS_FILE = os.path.join(DATA_DIR, 'bugs.json')


def load_bugs():
    if os.path.exists(BUGS_FILE):
        with open(BUGS_FILE, 'r') as f:
            return json.load(f)
    return []


def save_bugs(bugs):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(BUGS_FILE, 'w') as f:
        json.dump(bugs, f)


def next_workday(d):
    d += timedelta(days=1)
    while d.weekday() in WEEKEND:
        d += timedelta(days=1)
    return d


def schedule_projects(projects):
    # sort by priority and start date
    projects.sort(key=lambda p: (PRIORITY_ORDER.get(p['priority'], 4), p['start_date']))
    worker_schedule = {w: {} for w in WORKERS}
    vacations = load_vacations()
    for vac in vacations:
        worker = vac['worker']
        day = date.fromisoformat(vac['start'])
        end = date.fromisoformat(vac['end'])
        while day <= end:
            if day.weekday() not in WEEKEND and worker in worker_schedule:
                ds = worker_schedule[worker].setdefault(day.isoformat(), [])
                ds.append({
                    'project': 'Vacaciones',
                    'client': '',
                    'phase': 'vacaciones',
                    'hours': HOURS_PER_DAY,
                    'late': False,
                    'color': '#ff9999',
                    'due_date': '',
                    'start_date': '',
                    'priority': '',
                    'pid': f"vac-{vac.get('id', '')}"
                })
            day += timedelta(days=1)
    conflicts = []
    for project in projects:
        current = date.fromisoformat(project['start_date'])
        end_date = current
        assigned = project.get('assigned', {})
        for phase in PHASE_ORDER:
            val = project['phases'].get(phase)
            if not val:
                continue
            segs = val if isinstance(val, list) else [val]
            workers = assigned.get(phase)
            if isinstance(workers, list):
                wlist = workers + [None] * (len(segs) - len(workers))
            else:
                wlist = [workers] * len(segs)
            new_workers = []
            for idx, seg_val in enumerate(segs):
                w = wlist[idx] or find_worker_for_phase(
                    phase, worker_schedule, project.get('priority')
                )
                if not w or phase not in WORKERS.get(w, []):
                    msg = f'Sin recurso para fase {phase}'
                    conflicts.append({
                        'id': len(conflicts) + 1,
                        'project': project['name'],
                        'message': msg,
                        'key': f"{project['name']}|{msg}",
                    })
                    new_workers.append(None)
                    continue
                if phase == 'pedidos' and isinstance(seg_val, str) and '-' in seg_val:
                    current, end_date = assign_pedidos(
                        worker_schedule[w],
                        current,
                        date.fromisoformat(seg_val),
                        project['name'],
                        project['client'],
                        project['due_date'],
                        project.get('color', '#ddd'),
                        project['start_date'],
                        project.get('priority'),
                        project['id'],
                    )
                else:
                    hours = int(seg_val)
                    current, end_date = assign_phase(
                        worker_schedule[w],
                        current,
                        phase,
                        project['name'],
                        project['client'],
                        hours,
                        project['due_date'],
                        project.get('color', '#ddd'),
                        w,
                        project['start_date'],
                        project.get('priority'),
                        project['id'],
                        seg=idx,
                    )
                new_workers.append(w)
            assigned[phase] = new_workers if len(new_workers) > 1 else new_workers[0]
        project['end_date'] = end_date.isoformat()
        if date.fromisoformat(project['end_date']) > date.fromisoformat(project['due_date']):
            msg = 'No se cumple la fecha de entrega'
            conflicts.append({
                'id': len(conflicts) + 1,
                'project': project['name'],
                'message': msg,
                'key': f"{project['name']}|{msg}",
            })
    return worker_schedule, conflicts


def assign_phase(schedule, start_day, phase, project_name, client, hours, due_date, color, worker, start_date, priority, pid, seg=0):
    day = start_day
    while day.weekday() in WEEKEND or any(t['phase'] == 'vacaciones' for t in schedule.get(day.isoformat(), [])):
        day = next_workday(day)
    remaining = hours
    last_day = day
    while remaining > 0:
        if day.weekday() in WEEKEND or any(t['phase'] == 'vacaciones' for t in schedule.get(day.isoformat(), [])):
            day = next_workday(day)
            continue
        day_str = day.isoformat()
        tasks = schedule.get(day_str, [])
        used = sum(t['hours'] for t in tasks)
        limit = HOURS_LIMITS.get(worker, HOURS_PER_DAY)
        if limit != float('inf'):
            if used >= limit:
                day = next_workday(day)
                continue
            available = min(limit - used, HOURS_PER_DAY)
        else:
            available = HOURS_PER_DAY
        if available > 0:
            allocate = min(remaining, available)
            late = day > date.fromisoformat(due_date)
            tasks.append({
                'project': project_name,
                'client': client,
                'phase': phase,
                'hours': allocate,
                'late': late,
                'color': color,
                'due_date': due_date,
                'start_date': start_date,
                'priority': priority,
                'pid': pid,
                'seg': seg,
            })
            schedule[day_str] = tasks
            remaining -= allocate
            last_day = day
        if remaining > 0:
            day = next_workday(day)
    return next_workday(last_day), last_day


def assign_pedidos(schedule, start_day, end_day, project_name, client, due_date, color, start_date, priority, pid):
    """Assign the 'pedidos' phase as a continuous range without hour limits."""
    day = start_day
    while day.weekday() in WEEKEND or any(t['phase'] == 'vacaciones' for t in schedule.get(day.isoformat(), [])):
        day = next_workday(day)
    last_day = day
    while day <= end_day:
        if day.weekday() in WEEKEND or any(t['phase'] == 'vacaciones' for t in schedule.get(day.isoformat(), [])):
            day += timedelta(days=1)
            continue
        day_str = day.isoformat()
        tasks = schedule.get(day_str, [])
        late = day > date.fromisoformat(due_date)
        tasks.append({
            'project': project_name,
            'client': client,
            'phase': 'pedidos',
            'hours': 0,
            'late': late,
            'color': color,
            'due_date': due_date,
            'start_date': start_date,
            'priority': priority,
            'pid': pid,
        })
        schedule[day_str] = tasks
        last_day = day
        day += timedelta(days=1)
    return next_workday(last_day), last_day


def _worker_load(schedule, worker):
    """Return total assigned hours for a worker."""
    return sum(
        t['hours']
        for day in schedule.get(worker, {}).values()
        for t in day
    )


def find_worker_for_phase(phase, schedule, priority=None, *, include_unai=False):
    """Choose the least busy worker that can perform the phase.

    By default Unai is excluded from automatic assignments so that he can
    only be seleccionado manualmente desde la vista de proyectos.
    """
    candidates = []
    for worker, skills in WORKERS.items():
        if not include_unai and worker == 'Unai':
            continue
        if phase in skills:
            load = _worker_load(schedule, worker)
            candidates.append((skills.index(phase), load, worker))
    if not candidates:
        return None
    if priority == 'Alta':
        prio = [c for c in candidates if c[0] == 0]
        if prio:
            candidates = prio
    candidates.sort(key=lambda c: (c[1], c[0]))
    return candidates[0][2]

import copy


def compute_schedule_map(projects):
    """Return a mapping of project id to scheduled tasks."""
    temp = copy.deepcopy(projects)
    schedule, _ = schedule_projects(temp)
    mapping = {}
    for worker, days in schedule.items():
        for day, tasks in days.items():
            for t in tasks:
                pid = t['pid']
                mapping.setdefault(pid, []).append((worker, day, t['phase'], t['hours'], t.get('seg', 0)))
    for lst in mapping.values():
        lst.sort()
    return mapping
