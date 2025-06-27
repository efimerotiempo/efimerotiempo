from flask import Flask, render_template, request, redirect, url_for
from datetime import date, timedelta
import uuid
from schedule import (
    load_projects,
    save_projects,
    schedule_projects,
    load_dismissed,
    save_dismissed,
    PRIORITY_ORDER,
    PHASE_ORDER,
    WORKERS,
    find_worker_for_phase,
)

app = Flask(__name__)

COLORS = [
    '#f8b195', '#c06c84', '#355c7d', '#6c5b7b', '#f67280', '#99b898',
    '#ff8c94', '#ffc857', '#698f3f', '#f4a259', '#51adcf', '#e63946',
    '#8d99ae', '#a8dadc', '#457b9d', '#ffb4a2', '#b5838d', '#5e548e',
    '#3a86ff', '#8338ec', '#ff006e', '#fb5607', '#ffbe0b', '#ff7f50',
]
MIN_DATE = date(2024, 1, 1)
MAX_DATE = date(2026, 12, 31)


def get_projects():
    projects = load_projects()
    if not projects:
        return []
    return projects


@app.route('/')
def index():
    projects = load_projects()
    schedule, conflicts = schedule_projects(projects)
    dismissed = load_dismissed()
    conflicts = [c for c in conflicts if c['key'] not in dismissed]

    default_start = date.today() - timedelta(days=date.today().weekday())
    default_offset = (default_start - MIN_DATE).days
    max_offset = (MAX_DATE - MIN_DATE).days - 13

    try:
        offset = int(request.args.get('offset', default_offset))
    except ValueError:
        offset = default_offset
    offset = max(0, min(offset, max_offset))

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

    start = MIN_DATE + timedelta(days=offset)
    days = [start + timedelta(days=i) for i in range(14)]

    today_offset = (date.today() - MIN_DATE).days

    return render_template(
        'index.html',
        schedule=schedule,
        days=days,
        conflicts=conflicts,
        workers=WORKERS,
        offset=offset,
        max_offset=max_offset,
        today_offset=today_offset,
        project_filter=project_filter,
        client_filter=client_filter,
    )


@app.route('/projects')
def project_list():
    projects = load_projects()
    return render_template(
        'projects.html',
        projects=projects,
        priorities=list(PRIORITY_ORDER.keys()),
        phases=PHASE_ORDER,
        all_workers=list(WORKERS.keys()),
    )


@app.route('/add', methods=['GET', 'POST'])
def add_project():
    if request.method == 'POST':
        data = request.form
        projects = load_projects()
        schedule, _ = schedule_projects(projects)
        color = COLORS[len(projects) % len(COLORS)]
        project = {
            'id': str(uuid.uuid4()),
            'name': data['name'],
            'client': data['client'],
            'start_date': date.today().isoformat(),
            'due_date': data['due_date'],
            'priority': data.get('priority', 'Sin prioridad'),
            'color': color,
            'phases': {},
            'assigned': {}
        }
        for phase in PHASE_ORDER:
            hours = data.get(phase)
            if hours:
                try:
                    project['phases'][phase] = int(hours)
                    project['assigned'][phase] = find_worker_for_phase(
                        phase, schedule, project['priority']
                    )
                except ValueError:
                    pass
        projects.append(project)
        save_projects(projects)
        return redirect(url_for('project_list'))
    return render_template('add_project.html')


@app.route('/complete', methods=['GET', 'POST'])
def complete():
    projects = load_projects()
    if request.method == 'POST':
        data = request.form
        schedule, _ = schedule_projects(projects)
        color = COLORS[len(projects) % len(COLORS)]
        project = {
            'id': str(uuid.uuid4()),
            'name': data['name'],
            'client': data['client'],
            'start_date': date.today().isoformat(),
            'due_date': data['due_date'],
            'priority': data.get('priority', 'Sin prioridad'),
            'color': color,
            'phases': {},
            'assigned': {}
        }
        for phase in PHASE_ORDER:
            hours = data.get(phase)
            if hours:
                try:
                    project['phases'][phase] = int(hours)
                    project['assigned'][phase] = find_worker_for_phase(
                        phase, schedule, project['priority']
                    )
                except ValueError:
                    pass
        projects.append(project)
        save_projects(projects)
        return redirect(url_for('complete'))

    schedule, conflicts = schedule_projects(projects)
    dismissed = load_dismissed()
    conflicts = [c for c in conflicts if c['key'] not in dismissed]

    default_start = date.today() - timedelta(days=date.today().weekday())
    default_offset = (default_start - MIN_DATE).days
    max_offset = (MAX_DATE - MIN_DATE).days - 13

    try:
        offset = int(request.args.get('offset', default_offset))
    except ValueError:
        offset = default_offset
    offset = max(0, min(offset, max_offset))

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

    start = MIN_DATE + timedelta(days=offset)
    days = [start + timedelta(days=i) for i in range(14)]
    today_offset = (date.today() - MIN_DATE).days

    return render_template(
        'complete.html',
        schedule=schedule,
        days=days,
        conflicts=conflicts,
        workers=WORKERS,
        offset=offset,
        max_offset=max_offset,
        today_offset=today_offset,
        project_filter=project_filter,
        client_filter=client_filter,
        projects=projects,
        priorities=list(PRIORITY_ORDER.keys()),
        phases=PHASE_ORDER,
        all_workers=list(WORKERS.keys()),
    )


@app.route('/update_priority/<pid>', methods=['POST'])
def update_priority(pid):
    projects = load_projects()
    for p in projects:
        if p['id'] == pid:
            p['priority'] = request.form['priority']
            break
    save_projects(projects)
    return redirect(url_for('project_list'))


@app.route('/update_worker/<pid>/<phase>', methods=['POST'])
def update_worker(pid, phase):
    projects = load_projects()
    for p in projects:
        if p['id'] == pid:
            p.setdefault('assigned', {})[phase] = request.form['worker']
            break
    save_projects(projects)
    return redirect(url_for('project_list'))


@app.route('/delete_conflict/<path:key>', methods=['POST'])
def delete_conflict(key):
    dismissed = load_dismissed()
    if key not in dismissed:
        dismissed.append(key)
        save_dismissed(dismissed)
    return redirect(url_for('index'))


if __name__ == '__main__':
    app.run(debug=True, port=5000)
