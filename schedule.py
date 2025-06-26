from datetime import date, timedelta
import json
import os

DATA_DIR = 'data'
PROJECTS_FILE = os.path.join(DATA_DIR, 'projects.json')
DISMISSED_FILE = os.path.join(DATA_DIR, 'dismissed_conflicts.json')

PHASE_ORDER = ['dibujo', 'recepcionar material', 'montar', 'soldar', 'pintar', 'mecanizar', 'tratamiento']
PRIORITY_ORDER = {'Alta': 1, 'Media': 2, 'Baja': 3, 'Sin prioridad': 4}

WORKERS = {
    'Pilar': ['dibujo'],
    'Joseba': ['dibujo', 'montar'],
    'Irene': ['recepcionar material'],
    'Mikel': ['montar'],
    'Iban': ['montar'],
    'Naparra': ['montar'],
    'Unai': ['montar', 'soldar'],
    'Fabio': ['soldar'],
    'Beltxa': ['soldar'],
    'Igor': ['soldar'],
    'Albi': ['recepcionar material', 'soldar', 'montar'],
    'Eneko': ['pintar', 'montar', 'soldar'],
    'Mecanizar': ['mecanizar'],
    'Tratamiento': ['tratamiento'],
}

HOURS_PER_DAY = 8
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


def next_workday(d):
    d += timedelta(days=1)
    while d.weekday() in WEEKEND:
        d += timedelta(days=1)
    return d


def schedule_projects(projects):
    # sort by priority and start date
    projects.sort(key=lambda p: (PRIORITY_ORDER.get(p['priority'], 4), p['start_date']))
    worker_schedule = {w: {} for w in WORKERS}
    conflicts = []
    for project in projects:
        current = date.fromisoformat(project['start_date'])
        end_date = current
        assigned = project.get('assigned', {})
        for phase in PHASE_ORDER:
            hours = project['phases'].get(phase)
            if not hours:
                continue
            worker = assigned.get(phase) or find_worker_for_phase(phase)
            if not worker or phase not in WORKERS.get(worker, []):
                msg = f'Sin recurso para fase {phase}'
                conflicts.append({
                    'id': len(conflicts) + 1,
                    'project': project['name'],
                    'message': msg,
                    'key': f"{project['name']}|{msg}",
                })
                continue
            current, end_date = assign_phase(
                worker_schedule[worker],
                current,
                phase,
                project['name'],
                project['client'],
                hours,
                project['due_date'],
                project.get('color', '#ddd'),
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
    return worker_schedule, conflicts


def assign_phase(schedule, start_day, phase, project_name, client, hours, due_date, color):
    day = start_day
    while day.weekday() in WEEKEND:
        day = next_workday(day)
    remaining = hours
    last_day = day
    while remaining > 0:
        if day.weekday() in WEEKEND:
            day = next_workday(day)
            continue
        day_str = day.isoformat()
        tasks = schedule.get(day_str, [])
        used = sum(t['hours'] for t in tasks)
        if used < HOURS_PER_DAY:
            allocate = min(remaining, HOURS_PER_DAY - used)
            late = day > date.fromisoformat(due_date)
            tasks.append({
                'project': project_name,
                'client': client,
                'phase': phase,
                'hours': allocate,
                'late': late,
                'color': color,
            })
            schedule[day_str] = tasks
            remaining -= allocate
            last_day = day
        if remaining > 0:
            day = next_workday(day)
    return next_workday(last_day), last_day


def find_worker_for_phase(phase):
    for worker, skills in WORKERS.items():
        if phase in skills:
            return worker
    return None
