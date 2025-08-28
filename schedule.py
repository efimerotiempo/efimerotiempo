from datetime import date, timedelta
import json
import os
import copy

DATA_DIR = os.environ.get('EFIMERO_DATA_DIR', 'data')
PROJECTS_FILE = os.path.join(DATA_DIR, 'projects.json')
DISMISSED_FILE = os.path.join(DATA_DIR, 'dismissed_conflicts.json')
EXTRA_CONFLICTS_FILE = os.path.join(DATA_DIR, 'conflicts.json')
NOTES_FILE = os.path.join(DATA_DIR, 'notes.json')
VACATIONS_FILE = os.path.join(DATA_DIR, 'vacations.json')
DAILY_HOURS_FILE = os.path.join(DATA_DIR, 'daily_hours.json')
INACTIVE_WORKERS_FILE = os.path.join(DATA_DIR, 'inactive_workers.json')
EXTRA_WORKERS_FILE = os.path.join(DATA_DIR, 'extra_workers.json')

PHASE_ORDER = [
    'dibujo',
    'pedidos',
    'recepcionar material',
    'montar',
    'soldar',
    'soldadura interior',
    'pintar',
    'montaje final',
    'mecanizar',
    'tratamiento',
]
PRIORITY_ORDER = {'Alta': 1, 'Media': 2, 'Baja': 3, 'Sin prioridad': 4}

UNPLANNED = 'Sin planificar'

BASE_WORKERS = {
    'Pilar': ['dibujo'],
    'Joseba 1': ['dibujo'],
    'Irene': ['pedidos'],
    'Mikel': ['montar', 'montaje final', 'soldar', 'soldadura interior'],
    'Iban': ['montar', 'montaje final', 'soldar', 'soldadura interior'],
    'Joseba 2': ['montar', 'montaje final', 'soldar', 'soldadura interior'],
    'Naparra': ['montar', 'montaje final', 'soldar', 'soldadura interior'],
    'Unai': ['montar', 'montaje final', 'soldar', 'soldadura interior'],
    'Fabio': ['soldar', 'soldadura interior'],
    'Beltxa': ['soldar', 'soldadura interior', 'montar', 'montaje final'],
    'Igor': ['soldar', 'soldadura interior'],
    'Albi': ['recepcionar material', 'soldar', 'soldadura interior', 'montar', 'montaje final'],
    'Eneko': ['pintar', 'montar', 'montaje final', 'soldar', 'soldadura interior'],
}

TAIL_WORKERS = {
    'Mecanizar': ['mecanizar'],
    'Tratamiento': ['tratamiento'],
    UNPLANNED: PHASE_ORDER,
}


def load_extra_workers():
    if os.path.exists(EXTRA_WORKERS_FILE):
        with open(EXTRA_WORKERS_FILE, 'r') as f:
            return json.load(f)
    return []


def save_extra_workers(workers):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(EXTRA_WORKERS_FILE, 'w') as f:
        json.dump(workers, f)


def _build_workers(extra=None):
    workers = BASE_WORKERS.copy()
    if extra is None:
        extra = load_extra_workers()
    for w in extra:
        workers[w] = BASE_WORKERS['Eneko'][:]
    workers.update(TAIL_WORKERS)
    return workers


WORKERS = _build_workers()

# Igor deja de aparecer en el calendario a partir del 21 de julio
IGOR_END = date(2025, 7, 21)

HOURS_PER_DAY = 8
HOURS_LIMITS = {w: HOURS_PER_DAY for w in WORKERS}
HOURS_LIMITS['Irene'] = float('inf')
HOURS_LIMITS['Mecanizar'] = float('inf')
HOURS_LIMITS['Tratamiento'] = float('inf')
HOURS_LIMITS[UNPLANNED] = float('inf')
WEEKEND = {5, 6}  # Saturday=5, Sunday=6 in weekday()


def add_worker(name):
    """Add a new worker that behaves like Eneko."""
    name = name.strip()
    if not name or name in WORKERS:
        return
    extras = load_extra_workers()
    if name not in extras:
        extras.append(name)
        save_extra_workers(extras)
    new_workers = _build_workers(extras)
    WORKERS.clear()
    WORKERS.update(new_workers)
    HOURS_LIMITS[name] = HOURS_PER_DAY


def load_projects():
    if os.path.exists(PROJECTS_FILE):
        with open(PROJECTS_FILE, 'r') as f:
            data = json.load(f)
        filtered = [p for p in data if p.get('phases')]
        if len(filtered) != len(data):
            save_projects(filtered)
        return filtered
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


def load_notes():
    if os.path.exists(NOTES_FILE):
        with open(NOTES_FILE, 'r') as f:
            return json.load(f)
    return []


def save_notes(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(NOTES_FILE, 'w') as f:
        json.dump(data, f)


def load_vacations():
    if os.path.exists(VACATIONS_FILE):
        with open(VACATIONS_FILE, 'r') as f:
            data = json.load(f)
    else:
        data = []
    today = date.today()
    filtered = []
    for v in data:
        end = v.get('end')
        if end:
            try:
                if date.fromisoformat(end) < today:
                    continue
            except ValueError:
                pass
        filtered.append(v)
    if len(filtered) != len(data):
        save_vacations(filtered)
    return filtered


def save_vacations(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(VACATIONS_FILE, 'w') as f:
        json.dump(data, f)


def load_inactive_workers():
    if os.path.exists(INACTIVE_WORKERS_FILE):
        with open(INACTIVE_WORKERS_FILE, 'r') as f:
            return json.load(f)
    return []


def save_inactive_workers(workers):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(INACTIVE_WORKERS_FILE, 'w') as f:
        json.dump(workers, f)


def load_daily_hours():
    """Return mapping of day -> hours (1-9)."""
    if os.path.exists(DAILY_HOURS_FILE):
        with open(DAILY_HOURS_FILE, 'r') as f:
            return {k: int(v) for k, v in json.load(f).items()}
    return {}


def save_daily_hours(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(DAILY_HOURS_FILE, 'w') as f:
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


def schedule_projects(projects):
    """Return schedule and conflicts after assigning all phases."""
    projects.sort(key=lambda p: (PRIORITY_ORDER.get(p['priority'], 4), p['start_date']))
    worker_schedule = {w: {} for w in WORKERS}
    hours_map = load_daily_hours()
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
    # Place frozen phases first so other tasks respect their positions
    for p in projects:
        for t in p.get('frozen_tasks', []):
            w = t['worker']
            day = t['day']
            entry = t.copy()
            entry.pop('worker', None)
            entry.pop('day', None)
            worker_schedule.setdefault(w, {}).setdefault(day, []).append(entry)

    # Sort frozen tasks chronologically
    for w, days in worker_schedule.items():
        for d, lst in days.items():
            lst.sort(key=lambda x: x.get('start', 0))

    conflicts = []
    for project in projects:
        planned = project.get('planned', True)
        if not planned:
            current = date.today()
            project['start_date'] = current.isoformat()
        else:
            try:
                current = date.fromisoformat(project['start_date'])
            except Exception:
                current = date.today()
                project['start_date'] = current.isoformat()
        hour = 0
        frozen_end = {}
        for t in project.get('frozen_tasks', []):
            ph = t.get('phase')
            try:
                d = date.fromisoformat(t['day'])
            except Exception:
                continue
            if ph in PHASE_ORDER:
                prev = frozen_end.get(ph)
                if not prev or d > prev:
                    frozen_end[ph] = d
        end_date = current
        assigned = project.get('assigned', {})
        for phase in PHASE_ORDER:
            val = project['phases'].get(phase)
            if not val:
                continue
            if phase in frozen_end:
                current = next_workday(frozen_end[phase])
                end_date = max(end_date, frozen_end[phase])
                hour = 0
                continue

            if phase == 'pedidos' and isinstance(val, str) and '-' in val:
                start_overrides = project.get('segment_starts', {}).get(phase)
                if start_overrides and start_overrides[0]:
                    current = date.fromisoformat(start_overrides[0])
                days_needed = sum(
                    1
                    for i in range((date.fromisoformat(val) - current).days + 1)
                    if (current + timedelta(days=i)).weekday() not in WEEKEND
                )
                worker = assigned.get(phase) if planned else UNPLANNED
                if planned and not worker:
                    worker = find_worker_for_phase(
                        phase,
                        worker_schedule,
                        project.get('priority'),
                        start_day=current,
                        days=days_needed,
                        vacations=vac_map,
                        hours_map=hours_map,
                    )
                    if worker:
                        assigned[phase] = worker
                if not worker:
                    msg = f'Sin recurso para fase {phase}'
                    conflicts.append({
                        'id': len(conflicts) + 1,
                        'project': project['name'],
                        'client': project['client'],
                        'message': msg,
                        'key': f"{project['name']}|{msg}",
                    })
                    continue
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
                    worker,
                    project_blocked=project.get('blocked', False),
                    material_date=project.get('material_confirmed_date'),
                )
            else:
                segs = val if isinstance(val, list) else [val]
                seg_workers = project.get('segment_workers', {}).get(phase) if isinstance(val, list) else None
                start_overrides = project.get('segment_starts', {}).get(phase)
                for idx, seg in enumerate(segs):
                    hours = int(seg)
                    days_needed = (hours + HOURS_PER_DAY - 1) // HOURS_PER_DAY
                    if not planned:
                        worker = UNPLANNED
                    else:
                        worker = None
                        if seg_workers and idx < len(seg_workers):
                            worker = seg_workers[idx]
                        if not worker:
                            worker = assigned.get(phase)
                        if not worker:
                            worker = find_worker_for_phase(
                                phase,
                                worker_schedule,
                                project.get('priority'),
                                start_day=current,
                                days=days_needed,
                                vacations=vac_map,
                                hours_map=hours_map,
                            )
                            if seg_workers:
                                if len(seg_workers) <= idx:
                                    seg_workers.extend([None] * (idx + 1 - len(seg_workers)))
                                seg_workers[idx] = worker
                            else:
                                assigned[phase] = worker

                    if not worker:
                        msg = f'Sin recurso para fase {phase}'
                        conflicts.append({
                            'id': len(conflicts) + 1,
                            'project': project['name'],
                            'client': project['client'],
                            'message': msg,
                            'key': f"{project['name']}|{msg}",
                        })
                        continue

                    manual = False
                    if start_overrides and idx < len(start_overrides) and start_overrides[idx]:
                        override = date.fromisoformat(start_overrides[idx])
                        current = override
                        hour = 0
                        manual = True
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
                        hours_map,
                        part=idx if isinstance(val, list) else None,
                        manual=manual,
                        project_blocked=project.get('blocked', False),
                        material_date=project.get('material_confirmed_date'),
                        auto=project.get('auto_hours', {}).get(phase),
                    )
        project['end_date'] = end_date.isoformat()
        if project.get('due_date'):
            try:
                due_dt = date.fromisoformat(project['due_date'])
                if date.fromisoformat(project['end_date']) > due_dt:
                    msg = 'No se cumple la fecha de entrega'
                    conflicts.append({
                        'id': len(conflicts) + 1,
                        'project': project['name'],
                        'client': project['client'],
                        'message': msg,
                        'key': f"{project['name']}|{msg}",
                    })
            except ValueError:
                pass
    return worker_schedule, conflicts


def assign_phase(
    schedule,
    start_day,
    start_hour,
    phase,
    project_name,
    client,
    hours,
    due_date,
    color,
    worker,
    start_date,
    priority,
    pid,
    hours_map,
    part=None,
    *,
    manual=False,
    project_frozen=False,
    project_blocked=False,
    material_date=None,
    auto=False,
):
    # When scheduling 'montar', queue the task right after the worker finishes
    # the mounting phase of their previous project unless an explicit start was
    # requested. If there are free hours left that day, reuse them before moving
    # on to the next workday.
    if phase == 'montar' and not manual:
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
    while day.weekday() in WEEKEND or (
        any(t['phase'] == 'vacaciones' for t in schedule.get(day.isoformat(), []))
    ):
        day = next_workday(day)
        hour = 0
    remaining = hours
    last_day = day
    # Unplanned tasks ignore the daily limit but still split into 8h blocks.
    if worker == UNPLANNED:
        while remaining > 0:
            if day.weekday() in WEEKEND or any(t['phase'] == 'vacaciones' for t in schedule.get(day.isoformat(), [])):
                day = next_workday(day)
                continue
            day_str = day.isoformat()
            tasks = schedule.get(day_str, [])
            used = max((t.get('start', 0) + t['hours'] for t in tasks), default=0)
            allocate = min(remaining, HOURS_PER_DAY)
            late = False
            if due_date:
                try:
                    late = day > date.fromisoformat(due_date)
                except ValueError:
                    late = False
            tasks.append({
                'project': project_name,
                'client': client,
                'phase': phase,
                'hours': allocate,
                'start': used,
                'late': late,
                'color': color,
                'due_date': due_date,
                'start_date': start_date,
                'priority': priority,
                'pid': pid,
                'part': part,
                'frozen': project_frozen,
                'blocked': project_blocked,
                'material_date': material_date,
                'auto': auto,
            })
            tasks.sort(key=lambda t: t.get('start', 0))
            schedule[day_str] = tasks
            remaining -= allocate
            last_day = day
            day = next_workday(day)
            hour = 0
        return day, hour, last_day

    while remaining > 0:
        if day.weekday() in WEEKEND or (
            any(t['phase'] == 'vacaciones' for t in schedule.get(day.isoformat(), []))
        ):
            day = next_workday(day)
            continue
        day_str = day.isoformat()
        tasks = schedule.get(day_str, [])
        tasks.sort(key=lambda t: t.get('start', 0))
        used = max((t.get('start', 0) + t['hours'] for t in tasks), default=0)
        start = max(hour, used)
        limit = HOURS_LIMITS.get(worker, HOURS_PER_DAY)
        if limit != float('inf') and worker not in ('Irene', 'Mecanizar', 'Tratamiento') and phase not in ('mecanizar', 'tratamiento'):
            day_limit = hours_map.get(day_str, HOURS_PER_DAY)
            limit = min(limit, day_limit)
        if phase in ('tratamiento', 'mecanizar'):
            # These phases can accumulate unlimited projects per day but
            # each project aporta como mucho ocho horas diarias. Tras asignar
            # un bloque de trabajo se pasa al siguiente día.
            allocate = min(remaining, HOURS_PER_DAY)
            late = False
            if due_date:
                try:
                    late = day > date.fromisoformat(due_date)
                except ValueError:
                    late = False
            tasks.append({
                'project': project_name,
                'client': client,
                'phase': phase,
                'hours': allocate,
                'start': used,
                'late': late,
                'color': color,
                'due_date': due_date,
                'start_date': start_date,
                'priority': priority,
                'pid': pid,
                'part': part,
                'frozen': project_frozen,
                'blocked': project_blocked,
                'material_date': material_date,
                'auto': auto,
            })
            tasks.sort(key=lambda t: t.get('start', 0))
            schedule[day_str] = tasks
            remaining -= allocate
            last_day = day
            day = next_workday(day)
            hour = 0
            continue

        if limit != float('inf') and start >= limit:
            day = next_workday(day)
            hour = 0
            continue
        available = limit - start if limit != float('inf') else HOURS_PER_DAY
        if available > 0:
            allocate = min(remaining, available)
            late = False
            if due_date:
                try:
                    late = day > date.fromisoformat(due_date)
                except ValueError:
                    late = False
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
                'part': part,
                'frozen': project_frozen,
                'blocked': project_blocked,
                'material_date': material_date,
                'auto': auto,
            })
            tasks.sort(key=lambda t: t.get('start', 0))
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


def assign_pedidos(
    schedule,
    start_day,
    end_day,
    project_name,
    client,
    due_date,
    color,
    start_date,
    priority,
    pid,
    worker=None,
    *,
    project_frozen=False,
    project_blocked=False,
    material_date=None,
):
    """Assign the 'pedidos' phase as a continuous range without hour limits."""
    day = start_day
    while day.weekday() in WEEKEND or (
        any(t['phase'] == 'vacaciones' for t in schedule.get(day.isoformat(), []))
    ):
        day = next_workday(day)
    last_day = day
    while day <= end_day:
        if day.weekday() in WEEKEND or (
            any(t['phase'] == 'vacaciones' for t in schedule.get(day.isoformat(), []))
        ):
            day += timedelta(days=1)
            continue
        day_str = day.isoformat()
        tasks = schedule.get(day_str, [])
        late = False
        if due_date:
            try:
                late = day > date.fromisoformat(due_date)
            except ValueError:
                late = False
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
            'frozen': project_frozen,
            'blocked': project_blocked,
            'material_date': material_date,
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



def _continuous_free_start(schedule, worker, day, days_needed, vacations=None, hours_map=None):
    """Return the first day with ``days_needed`` consecutive free workdays."""
    vac = vacations.get(worker, set()) if vacations else set()
    sched = schedule.get(worker, {})
    d = day
    while True:
        test = d
        remaining = days_needed
        ok = True
        while remaining > 0:
            if test.weekday() in WEEKEND:
                test = next_workday(test)
                continue
            if test in vac:
                ok = False
                break
            used = sum(t['hours'] for t in sched.get(test.isoformat(), []))
            if used > 0:
                ok = False
                break
            remaining -= 1
            test = next_workday(test)
        if ok:
            return d
        d = next_workday(d)


def find_worker_for_phase(
    phase,
    schedule,
    priority=None,
    *,
    start_day=None,
    days=0,
    vacations=None,
    hours_map=None,
):
    """Choose the worker that can start the phase as soon as posible.

    Unai is always excluded from automatic assignments so that he can only
    be seleccionado manualmente desde la vista de proyectos.
    """
    candidates = []
    for worker in WORKERS:
        if worker in ('Unai', UNPLANNED):
            continue
        start = start_day or date.today()
        if worker == 'Igor' and start >= IGOR_END:
            continue
        if phase == 'montar':
            last, end = _last_phase_info(schedule.get(worker, {}), 'montar')
            if last and start <= last:
                limit = HOURS_LIMITS.get(worker, HOURS_PER_DAY)
                start = last if end < limit else next_workday(last)
        free = _continuous_free_start(
            schedule,
            worker,
            start,
            days or 1,
            vacations,
            hours_map,
        )
        load = _worker_load(schedule, worker)
        candidates.append((free, load, worker))
    if not candidates:
        return None
    if priority == 'Alta':
        earliest = min(candidates, key=lambda c: (c[0], c[1]))
        return earliest[2]
    candidates.sort(key=lambda c: (c[0], c[1]))
    return candidates[0][2]

def compute_schedule_map(projects):
    """Return a mapping of project id to scheduled tasks."""
    temp = copy.deepcopy(projects)
    schedule, _ = schedule_projects(temp)
    mapping = {}
    for worker, days in schedule.items():
        for day, tasks in days.items():
            for t in tasks:
                pid = t['pid']
                mapping.setdefault(pid, []).append((worker, day, t['phase'], t['hours'], t.get('part')))
    for lst in mapping.values():
        lst.sort()
    return mapping


def phase_start_map(projects):
    """Return mapping of pid -> {phase: first_day}"""
    mapping = compute_schedule_map(projects)
    result = {}
    for pid, items in mapping.items():
        for worker, day, phase, hours, _ in items:
            result.setdefault(pid, {}).setdefault(phase, day)
    return result
