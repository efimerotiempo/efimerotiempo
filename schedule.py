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


def next_workday(d):
    d += timedelta(days=1)
    while d.weekday() in WEEKEND:
        d += timedelta(days=1)
    return d


def _build_vacation_map():
    """Return a mapping of worker to set of vacation days."""
    vac_map = {}
    vacations = load_vacations()
    for vac in vacations:
        worker = vac['worker']
        day = date.fromisoformat(vac['start'])
        end = date.fromisoformat(vac['end'])
        while day <= end:
            if day.weekday() not in WEEKEND:
                vac_map.setdefault(worker, set()).add(day)
            day += timedelta(days=1)
    return vac_map


def _worker_on_vacation(worker, start_day, days_needed, vac_map):
    """Return True if worker has vacation within ``days_needed`` workdays after ``start_day``."""
    d = start_day
    remaining = days_needed
    while remaining > 0:
        if d.weekday() not in WEEKEND:
            if d in vac_map.get(worker, set()):
                return True
            remaining -= 1
        d += timedelta(days=1)
    return False


def _vacation_days_in_range(worker, start_day, days_needed, vac_map):
    days = []
    d = start_day
    remaining = days_needed
    while remaining > 0:
        if d.weekday() not in WEEKEND:
            if d in vac_map.get(worker, set()):
                days.append(d)
            remaining -= 1
        d += timedelta(days=1)
    return days


def schedule_projects(projects):
    """Return schedule and conflicts after assigning all phases."""
    projects.sort(key=lambda p: (PRIORITY_ORDER.get(p['priority'], 4), p['start_date']))
    worker_schedule = {w: {} for w in WORKERS}
    vac_map = _build_vacation_map()
    for worker, days in vac_map.items():
        for day in days:
            if worker in worker_schedule:
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
                    'pid': f"vac-{worker}-{day.isoformat()}"
                })
    conflicts = []
    reassignments = []
    for project in projects:
        current = date.fromisoformat(project['start_date'])
        hour = 0
        end_date = current
        assigned = project.get('assigned', {})
        for phase in PHASE_ORDER:
            val = project['phases'].get(phase)
            if not val:
                continue
            if phase == 'pedidos' and isinstance(val, str) and '-' in val:
                days_needed = sum(
                    1
                    for i in range((date.fromisoformat(val) - current).days + 1)
                    if (current + timedelta(days=i)).weekday() not in WEEKEND
                )
            else:
                hours = int(val)
                days_needed = (hours + HOURS_PER_DAY - 1) // HOURS_PER_DAY

            worker = assigned.get(phase)
            if worker and _worker_on_vacation(worker, current, days_needed, vac_map):
                worker = None

            if not worker:
                worker = find_worker_for_phase(
                    phase,
                    worker_schedule,
                    project.get('priority'),
                    start_day=current,
                    days=days_needed,
                    vacations=vac_map,
                )
                if worker and assigned.get(phase) and worker != assigned.get(phase):
                    vac_days = _vacation_days_in_range(
                        assigned.get(phase), current, days_needed, vac_map
                    )
                    reassignments.append({
                        'project': project['name'],
                        'client': project['client'],
                        'old': assigned.get(phase),
                        'new': worker,
                        'phase': phase,
                        'dates': [d.isoformat() for d in vac_days],
                        'pid': project['id'],
                    })
                    assigned[phase] = worker

            if not worker or phase not in WORKERS.get(worker, []):
                msg = f'Sin recurso para fase {phase}'
                conflicts.append({
                    'id': len(conflicts) + 1,
                    'project': project['name'],
                    'message': msg,
                    'key': f"{project['name']}|{msg}",
                })
                continue
            if phase == 'pedidos' and isinstance(val, str) and '-' in val:
                current, hour, end_date = assign_pedidos(
                    worker_schedule[worker],
                    current,
                    date.fromisoformat(val),
                    project['name'],
                    project['client'],
                    project['due_date'],
                    project.get('color', '#ddd'),
                    project['start_date'],
                    project.get('priority'),
                    project['id'],
                )
            else:
                hours = int(val)
                current, hour, end_date = assign_phase(
                    worker_schedule[worker],
                    current,
                    hour,
                    phase,
                    project['name'],
                    project['client'],
                    hours,
                    project['due_date'],
                    project.get('color', '#ddd'),
                    worker,
                    project['start_date'],
                    project.get('priority'),
                    project['id'],
                )
        project['end_date'] = end_date.isoformat()
        if date.fromisoformat(project['end_date']) > date.fromisoformat(project['due_date']):
            msg = 'No se cumple la fecha de entrega'
            conflicts.append({
                'id': len(conflicts) + 1,
                'project': project['name'],
                'message': msg,
                'key': f"{project['name']}|{msg}",
            })
    for r in reassignments:
        proj = next((p for p in projects if p['id'] == r['pid']), None)
        if not proj:
            continue
        met = date.fromisoformat(proj['end_date']) <= date.fromisoformat(proj['due_date'])
        days = ', '.join(r['dates'])
        msg = (
            f"Vacaciones de {r['old']} ({days}); fase {r['phase']} reasignada a {r['new']}. "
            f"{'Cumple' if met else 'No cumple'} la fecha límite"
        )
        conflicts.append({
            'id': len(conflicts) + 1,
            'project': r['project'],
            'message': msg,
            'key': f"vac-{r['pid']}-{r['phase']}-{days}",
            'pid': r['pid'],
        })
    return worker_schedule, conflicts


def assign_phase(schedule, start_day, start_hour, phase, project_name, client, hours, due_date, color, worker, start_date, priority, pid):
    # When scheduling 'montar', queue the task right after the worker finishes
    # the mounting phase of their previous project. If there are free hours left
    # that day, reuse them before moving on to the next workday.
    if phase == 'montar':
        last, end_hour = _last_phase_info(schedule, 'montar')
        if last and start_day <= last:
            limit = HOURS_LIMITS.get(worker, HOURS_PER_DAY)
            if end_hour < limit:
                start_day = last
                start_hour = max(start_hour, end_hour)
            else:
                start_day = next_workday(last)
                start_hour = 0

    day = start_day
    hour = start_hour
    while day.weekday() in WEEKEND or any(t['phase'] == 'vacaciones' for t in schedule.get(day.isoformat(), [])):
        day = next_workday(day)
        hour = 0
    remaining = hours
    last_day = day
    while remaining > 0:
        if day.weekday() in WEEKEND or any(t['phase'] == 'vacaciones' for t in schedule.get(day.isoformat(), [])):
            day = next_workday(day)
            continue
        day_str = day.isoformat()
        tasks = schedule.get(day_str, [])
        tasks.sort(key=lambda t: t.get('start', 0))
        used = max((t.get('start', 0) + t['hours'] for t in tasks), default=0)
        start = max(hour, used)
        limit = HOURS_LIMITS.get(worker, HOURS_PER_DAY)
        if limit != float('inf') and start >= limit:
            day = next_workday(day)
            hour = 0
            continue
        available = limit - start if limit != float('inf') else HOURS_PER_DAY
        if available > 0:
            allocate = min(remaining, available)
            late = day > date.fromisoformat(due_date)
            tasks.append({
                'project': project_name,
                'client': client,
                'phase': phase,
                'hours': allocate,
                'start': start,
                'late': late,
                'color': color,
                'due_date': due_date,
                'start_date': start_date,
                'priority': priority,
                'pid': pid,
            })
            tasks.sort(key=lambda t: t['start'])
            schedule[day_str] = tasks
            remaining -= allocate
            last_day = day
            hour = start + allocate
            if hour >= limit and limit != float('inf'):
                day = next_workday(day)
                hour = 0
        else:
            day = next_workday(day)
            hour = 0
    next_day = day
    next_hour = hour
    return next_day, next_hour, last_day


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
    return next_workday(last_day), 0, last_day


def _last_phase_info(schedule, phase):
    """Return the day and hour when the last ``phase`` finished."""
    last_day = None
    end_hour = 0
    for d, tasks in schedule.items():
        for t in tasks:
            if t['phase'] == phase:
                dt = date.fromisoformat(d)
                finish = t.get('start', 0) + t['hours']
                if not last_day or dt > last_day or (dt == last_day and finish > end_hour):
                    last_day = dt
                    end_hour = finish
    if not last_day:
        return None, 0
    return last_day, end_hour


def _worker_load(schedule, worker):
    """Return total assigned hours for a worker."""
    return sum(
        t['hours']
        for day in schedule.get(worker, {}).values()
        for t in day
    )


def _next_free_day(schedule, worker, day, vacations=None):
    """Return the first workday after ``day`` with available hours."""
    vac = vacations.get(worker, set()) if vacations else set()
    sched = schedule.get(worker, {})
    while True:
        if day.weekday() in WEEKEND or day in vac:
            day = next_workday(day)
            continue
        used = sum(t['hours'] for t in sched.get(day.isoformat(), []))
        limit = HOURS_LIMITS.get(worker, HOURS_PER_DAY)
        if used < limit:
            return day
        day = next_workday(day)


def find_worker_for_phase(
    phase,
    schedule,
    priority=None,
    *,
    include_unai=False,
    start_day=None,
    days=0,
    vacations=None,
):
    """Choose the worker that can start the phase as soon as posible.

    By default Unai is excluded from automatic assignments so that he can
    only be seleccionado manualmente desde la vista de proyectos.
    """
    candidates = []
    for worker, skills in WORKERS.items():
        if not include_unai and worker == 'Unai':
            continue
        if phase not in skills:
            continue
        free = _next_free_day(schedule, worker, start_day or date.today(), vacations)
        load = _worker_load(schedule, worker)
        candidates.append((free, load, skills.index(phase), worker))
    if not candidates:
        return None
    if priority == 'Alta':
        earliest = min(candidates, key=lambda c: (c[0], c[1], c[2]))
        return earliest[3]
    candidates.sort(key=lambda c: (c[0], c[1], c[2]))
    return candidates[0][3]

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
                mapping.setdefault(pid, []).append((worker, day, t['phase'], t['hours']))
    for lst in mapping.values():
        lst.sort()
    return mapping


def phase_start_map(projects):
    """Return mapping of pid -> {phase: first_day}"""
    mapping = compute_schedule_map(projects)
    result = {}
    for pid, items in mapping.items():
        for worker, day, phase, hours in items:
            result.setdefault(pid, {}).setdefault(phase, day)
    return result
