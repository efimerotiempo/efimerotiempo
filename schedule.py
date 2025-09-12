from datetime import date, timedelta, datetime, time
import json
import os
import copy

DATA_DIR = os.environ.get('EFIMERO_DATA_DIR', 'data')
PROJECTS_FILE = os.path.join(DATA_DIR, 'projects.json')
DISMISSED_FILE = os.path.join(DATA_DIR, 'dismissed_conflicts.json')
EXTRA_CONFLICTS_FILE = os.path.join(DATA_DIR, 'conflicts.json')
NOTES_FILE = os.path.join(DATA_DIR, 'notes.json')
WORKER_NOTES_FILE = os.path.join(DATA_DIR, 'worker_notes.json')
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
    'montar 2º',
    'soldar 2º',
    'mecanizar',
    'tratamiento',
    'pintar',
]

UNPLANNED = 'Sin planificar'

BASE_WORKERS = {
    'Pilar': ['dibujo'],
    'Joseba 1': ['dibujo'],
    'Irene': ['pedidos'],
    'Mikel': ['montar', 'montar 2º', 'soldar', 'soldar 2º'],
    'Iban': ['montar', 'montar 2º', 'soldar', 'soldar 2º'],
    'Joseba 2': ['montar', 'montar 2º', 'soldar', 'soldar 2º'],
    'Naparra': ['montar', 'montar 2º', 'soldar', 'soldar 2º'],
    'Unai': ['montar', 'montar 2º', 'soldar', 'soldar 2º'],
    'Fabio': ['soldar', 'soldar 2º'],
    'Beltxa': ['soldar', 'soldar 2º', 'montar', 'montar 2º'],
    'Igor': ['soldar', 'soldar 2º'],
    'Albi': ['recepcionar material', 'soldar', 'soldar 2º', 'montar', 'montar 2º'],
    'Eneko': ['pintar', 'montar', 'montar 2º', 'soldar', 'soldar 2º'],
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
WORKDAY_START = 8
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


def load_worker_notes():
    if os.path.exists(WORKER_NOTES_FILE):
        with open(WORKER_NOTES_FILE, 'r') as f:
            return json.load(f)
    return {}


def save_worker_notes(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(WORKER_NOTES_FILE, 'w') as f:
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


def _calc_datetimes(day, start, hours):
    """Return ISO start and end datetimes for a task."""
    start_dt = datetime.combine(day, time(hour=WORKDAY_START)) + timedelta(hours=start)
    end_dt = start_dt + timedelta(hours=hours)
    return start_dt.isoformat(), end_dt.isoformat()


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
    projects.sort(key=lambda p: p['start_date'])
    inactive = set(load_inactive_workers())
    worker_schedule = {w: {} for w in WORKERS if w not in inactive}
    hours_map = load_daily_hours()
    vac_map = _build_vacation_map()
    for worker, days in vac_map.items():
        for day in days:
            if worker in worker_schedule:
                ds = worker_schedule[worker].setdefault(day.isoformat(), [])
                start_time, end_time = _calc_datetimes(day, 0, HOURS_PER_DAY)
                ds.append({
                    'project': 'Vacaciones',
                    'client': '',
                    'phase': 'vacaciones',
                    'hours': HOURS_PER_DAY,
                    'start': 0,
                    'start_time': start_time,
                    'end_time': end_time,
                    'late': False,
                    'color': '#ff9999',
                    'due_date': '',
                    'start_date': '',
                    'pid': f"vac-{worker}-{day.isoformat()}"
                })
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
        frozen_map = {}
        for t in project.get('frozen_tasks', []):
            frozen_map.setdefault(t.get('phase'), []).append(t)
        end_date = current
        assigned = project.get('assigned', {})
        for phase in PHASE_ORDER:
            val = project['phases'].get(phase)
            if not val:
                continue
            if phase in frozen_map:
                segs = frozen_map[phase]
                last_day = date.min
                for seg in segs:
                    w = seg['worker']
                    day = seg['day']
                    entry = seg.copy()
                    entry.pop('worker', None)
                    entry.pop('day', None)
                    try:
                        d_obj = date.fromisoformat(day)
                    except Exception:
                        d_obj = date.today()
                    start_time, end_time = _calc_datetimes(
                        d_obj, entry.get('start', 0), entry.get('hours', 0)
                    )
                    entry.setdefault('start', 0)
                    entry['start_time'] = start_time
                    entry['end_time'] = end_time
                    worker_schedule.setdefault(w, {}).setdefault(day, []).append(entry)
                    worker_schedule[w][day].sort(key=lambda x: x.get('start', 0))
                    try:
                        d = date.fromisoformat(day)
                    except Exception:
                        d = date.today()
                    if d > last_day:
                        last_day = d
                current = next_workday(last_day)
                end_date = max(end_date, last_day)
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
                if not worker or worker in inactive:
                    worker = UNPLANNED
                current, hour, end_date = assign_pedidos(
                    worker_schedule[worker],
                    current,
                    date.fromisoformat(val),
                    project['name'],
                    project['client'],
                    project['due_date'],
                    project.get('due_confirmed'),
                    project.get('color', '#ddd'),
                    project['start_date'],
                    project['id'],
                    worker,
                    project_blocked=project.get('blocked', False),
                    material_date=project.get('material_confirmed_date'),
                )
            else:
                segs = val if isinstance(val, list) else [val]
                seg_workers = project.get('segment_workers', {}).get(phase) if isinstance(val, list) else None
                start_overrides = project.get('segment_starts', {}).get(phase)
                start_hour_overrides = project.get('segment_start_hours', {}).get(phase)
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
                        if not worker or worker in inactive:
                            worker = UNPLANNED
                            if seg_workers:
                                if len(seg_workers) <= idx:
                                    seg_workers.extend([None] * (idx + 1 - len(seg_workers)))
                                seg_workers[idx] = UNPLANNED
                            else:
                                assigned[phase] = UNPLANNED

                    override = None
                    hour_override = None
                    if start_overrides and idx < len(start_overrides) and start_overrides[idx]:
                        override = date.fromisoformat(start_overrides[idx])
                    if start_hour_overrides and idx < len(start_hour_overrides):
                        hour_override = start_hour_overrides[idx]
                    test_start = override or current
                    test_end = test_start
                    for _ in range(days_needed - 1):
                        test_end = next_workday(test_end)
                    # Allow scheduling even if the phase exceeds a confirmed due date.
                    # Previously, phases moved past a client deadline were treated as
                    # unplanned and removed from the calendar. This prevented them
                    # from being visualized after the move. By removing the forced
                    # ``UNPLANNED`` assignment, phases remain in the schedule and are
                    # displayed in the selected cell while still triggering the
                    # appropriate deadline warning elsewhere.
                    manual = False
                    if override:
                        current = override
                        hour = hour_override or 0
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
                        project['id'],
                        hours_map,
                        part=idx if isinstance(val, list) else None,
                        manual=manual,
                        project_blocked=project.get('blocked', False),
                        material_date=project.get('material_confirmed_date'),
                        auto=project.get('auto_hours', {}).get(phase),
                        due_confirmed=project.get('due_confirmed'),
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
    pid,
    hours_map,
    part=None,
    *,
    manual=False,
    project_frozen=False,
    project_blocked=False,
    material_date=None,
    auto=False,
    due_confirmed=False,
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
    phase_entries = []
    due_dt = None
    if due_date:
        try:
            due_dt = date.fromisoformat(due_date)
        except ValueError:
            due_dt = None
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
            late = bool(due_dt and day > due_dt)
            start_time, end_time = _calc_datetimes(day, used, allocate)
            task = {
                'project': project_name,
                'client': client,
                'phase': phase,
                'hours': allocate,
                'start': used,
                'start_time': start_time,
                'end_time': end_time,
                'late': late,
                'color': color,
                'due_date': due_date,
                'start_date': start_date,
                'pid': pid,
                'part': part,
                'frozen': project_frozen,
                'blocked': project_blocked,
                'material_date': material_date,
                'auto': auto,
            }
            tasks.append(task)
            phase_entries.append((task, day))
            tasks.sort(key=lambda t: t.get('start', 0))
            schedule[day_str] = tasks
            remaining -= allocate
            last_day = day
            day = next_workday(day)
            hour = 0
        project_late = bool(due_dt and last_day > due_dt)
        for task, t_day in phase_entries:
            if due_dt:
                if project_late:
                    task['due_status'] = 'after' if t_day > due_dt else 'before'
                else:
                    task['due_status'] = 'met'
            else:
                task['due_status'] = None
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
        limit = HOURS_LIMITS.get(worker, HOURS_PER_DAY)
        if limit != float('inf') and worker not in ('Irene', 'Mecanizar', 'Tratamiento') and phase not in ('mecanizar', 'tratamiento'):
            day_limit = hours_map.get(day_str, HOURS_PER_DAY)
            limit = min(limit, day_limit)

        if phase in ('tratamiento', 'mecanizar'):
            start = 0
            available = HOURS_PER_DAY
        else:
            start = hour
            next_task_start = None
            for t in tasks:
                if start + 1e-9 <= t.get('start', 0):
                    next_task_start = t.get('start', 0)
                    break
                start = max(start, t.get('start', 0) + t['hours'])
            if next_task_start is None:
                next_task_start = limit if limit != float('inf') else HOURS_PER_DAY
            if limit != float('inf') and start >= limit:
                day = next_workday(day)
                hour = 0
                continue
            available = next_task_start - start
            if limit != float('inf'):
                available = min(available, limit - start)
            if available <= 0:
                day = next_workday(day)
                hour = 0
                continue

        allocate = min(remaining, available)
        if phase in ('tratamiento', 'mecanizar'):
            # These phases can accumulate unlimited projects per day but
            # each project aporta como mucho ocho horas diarias. Tras asignar
            # un bloque de trabajo se pasa al siguiente día.
            allocate = min(allocate, HOURS_PER_DAY)
            late = bool(due_dt and day > due_dt)
            start_time, end_time = _calc_datetimes(day, start, allocate)
            task = {
                'project': project_name,
                'client': client,
                'phase': phase,
                'hours': allocate,
                'start': start,
                'start_time': start_time,
                'end_time': end_time,
                'late': late,
                'color': color,
                'due_date': due_date,
                'start_date': start_date,
                'pid': pid,
                'part': part,
                'frozen': project_frozen,
                'blocked': project_blocked,
                'material_date': material_date,
                'auto': auto,
            }
            tasks.append(task)
            phase_entries.append((task, day))
            tasks.sort(key=lambda t: t.get('start', 0))
            schedule[day_str] = tasks
            remaining -= allocate
            last_day = day
            day = next_workday(day)
            hour = 0
            continue

        late = bool(due_dt and day > due_dt)
        start_time, end_time = _calc_datetimes(day, start, allocate)
        task = {
            'project': project_name,
            'client': client,
            'phase': phase,
            'hours': allocate,
            'start': start,
            'start_time': start_time,
            'end_time': end_time,
            'late': late,
            'color': color,
            'due_date': due_date,
            'start_date': start_date,
            'pid': pid,
            'part': part,
            'frozen': project_frozen,
            'blocked': project_blocked,
            'material_date': material_date,
            'auto': auto,
        }
        tasks.append(task)
        phase_entries.append((task, day))
        tasks.sort(key=lambda t: t.get('start', 0))
        schedule[day_str] = tasks
        remaining -= allocate
        last_day = day
        hour = start + allocate
        if hour >= limit and limit != float('inf'):
            day = next_workday(day)
            hour = 0
    project_late = bool(due_dt and last_day > due_dt)
    for task, t_day in phase_entries:
        if due_dt:
            if project_late:
                task['due_status'] = 'after' if t_day > due_dt else 'before'
            else:
                task['due_status'] = 'met'
        else:
            task['due_status'] = None
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
    due_confirmed,
    color,
    start_date,
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
    phase_entries = []
    due_dt = None
    if due_date:
        try:
            due_dt = date.fromisoformat(due_date)
        except ValueError:
            due_dt = None
    while day <= end_day:
        if day.weekday() in WEEKEND or (
            any(t['phase'] == 'vacaciones' for t in schedule.get(day.isoformat(), []))
        ):
            day += timedelta(days=1)
            continue
        day_str = day.isoformat()
        tasks = schedule.get(day_str, [])
        late = bool(due_dt and day > due_dt)
        start_time, end_time = _calc_datetimes(day, 0, 0)
        task = {
            'project': project_name,
            'client': client,
            'phase': 'pedidos',
            'hours': 0,
            'start': 0,
            'start_time': start_time,
            'end_time': end_time,
            'late': late,
            'color': color,
            'due_date': due_date,
            'start_date': start_date,
            'pid': pid,
            'frozen': project_frozen,
            'blocked': project_blocked,
            'material_date': material_date,
        }
        tasks.append(task)
        phase_entries.append((task, day))
        schedule[day_str] = tasks
        last_day = day
        day += timedelta(days=1)
    project_late = bool(due_dt and last_day > due_dt)
    for task, t_day in phase_entries:
        if due_dt:
            if project_late:
                task['due_status'] = 'after' if t_day > due_dt else 'before'
            else:
                task['due_status'] = 'met'
        else:
            task['due_status'] = None
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
