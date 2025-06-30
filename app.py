from flask import Flask, render_template, request, redirect, url_for
from datetime import date, timedelta
import uuid
from schedule import (
    load_projects,
    save_projects,
    schedule_projects,
    load_dismissed,
    save_dismissed,
    load_extra_conflicts,
    save_extra_conflicts,
    load_milestones,
    save_milestones,
    PRIORITY_ORDER,
    PHASE_ORDER,
    WORKERS,
    find_worker_for_phase,
)

app = Flask(__name__)

COLORS = [
    '#ffd9e8', '#ffe4c4', '#e0ffff', '#d0f0c0', '#fef9b7', '#ffe8d6',
    '#dcebf1', '#e6d3f8', '#fdfd96', '#e7f5ff', '#ccffcc', '#e9f7fd',
    '#ffd8be', '#f8f0fb', '#f2ffde', '#fae1dd', '#fffff0', '#e8f0fe',
    '#ffcfd2', '#f0fff4', '#e7f9ea', '#fff2cc', '#e0e0ff', '#f0f8ff',
]
MIN_DATE = date(2024, 1, 1)
MAX_DATE = date(2026, 12, 31)


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


@app.route('/')
def index():
    projects = get_projects()
    schedule, conflicts = schedule_projects(projects)
    milestones = load_milestones()
    extra = load_extra_conflicts()
    conflicts.extend(extra)
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

    week_spans = []
    current_week = days[0].isocalendar().week
    span = 0
    for d in days:
        week = d.isocalendar().week
        if week != current_week:
            week_spans.append({'week': current_week, 'span': span})
            current_week = week
            span = 1
        else:
            span += 1
    week_spans.append({'week': current_week, 'span': span})

    today_offset = (date.today() - MIN_DATE).days

    milestone_map = {}
    for m in milestones:
        milestone_map.setdefault(m['date'], []).append(m['description'])

    return render_template(
        'index.html',
        schedule=schedule,
        days=days,
        week_spans=week_spans,
        conflicts=conflicts,
        workers=WORKERS,
        offset=offset,
        max_offset=max_offset,
        today_offset=today_offset,
        project_filter=project_filter,
        client_filter=client_filter,
        milestones=milestone_map,
    )


@app.route('/projects')
def project_list():
    projects = get_projects()
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
        projects = get_projects()
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
            if not hours and phase == 'pedidos':
                hours = '80'
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
    return render_template('add_project.html', phases=PHASE_ORDER)


@app.route('/add_milestone', methods=['POST'])
def add_milestone():
    """Add a milestone with a unique id."""
    milestones = load_milestones()
    milestones.append({
        'id': str(uuid.uuid4()),
        'description': request.form['description'],
        'date': request.form['date'],
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


@app.route('/complete', methods=['GET', 'POST'])
def complete():
    projects = get_projects()
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
            if not hours and phase == 'pedidos':
                hours = '80'
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
    milestones = load_milestones()
    extra = load_extra_conflicts()
    conflicts.extend(extra)
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
    week_spans = []
    current_week = days[0].isocalendar().week
    span = 0
    for d in days:
        week = d.isocalendar().week
        if week != current_week:
            week_spans.append({'week': current_week, 'span': span})
            current_week = week
            span = 1
        else:
            span += 1
    week_spans.append({'week': current_week, 'span': span})
    today_offset = (date.today() - MIN_DATE).days

    milestone_map = {}
    for m in milestones:
        milestone_map.setdefault(m['date'], []).append(m['description'])

    return render_template(
        'complete.html',
        schedule=schedule,
        days=days,
        week_spans=week_spans,
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
        milestones=milestone_map,
    )


@app.route('/update_priority/<pid>', methods=['POST'])
def update_priority(pid):
    projects = get_projects()
    for p in projects:
        if p['id'] == pid:
            p['priority'] = request.form['priority']
            break
    save_projects(projects)
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
    return redirect(url_for('index'))


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
