from flask import Flask, render_template, request, redirect, url_for
from datetime import date, timedelta
import uuid
import os
import copy
from werkzeug.utils import secure_filename
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
    load_vacations,
    save_vacations,
    PRIORITY_ORDER,
    PHASE_ORDER,
    WORKERS,
    find_worker_for_phase,
    compute_schedule_map,
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
UPLOAD_FOLDER = os.path.join('static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


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
def home():
    """Redirect to the combined view by default."""
    return redirect(url_for('complete'))


@app.route('/calendar')
def calendar_view():
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

    project_map = {p['id']: p for p in projects}

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
        today=date.today(),
        project_filter=project_filter,
        client_filter=client_filter,
        milestones=milestone_map,
        project_data=project_map,
        phases=PHASE_ORDER,
    )


@app.route('/projects')
def project_list():
    projects = get_projects()
    project_filter = request.args.get('project', '').strip()
    client_filter = request.args.get('client', '').strip()
    if project_filter or client_filter:
        projects = [
            p for p in projects
            if (not project_filter or project_filter.lower() in p['name'].lower())
            and (not client_filter or client_filter.lower() in p['client'].lower())
        ]
    return render_template(
        'projects.html',
        projects=projects,
        priorities=list(PRIORITY_ORDER.keys()),
        phases=PHASE_ORDER,
        all_workers=list(WORKERS.keys()),
        project_filter=project_filter,
        client_filter=client_filter,
    )


@app.route('/add', methods=['GET', 'POST'])
def add_project():
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
            'assigned': {},
            'image': image_path,
        }
        for phase in PHASE_ORDER:
            value = data.get(phase)
            if phase == 'pedidos':
                if not value:
                    value = (date.today() + timedelta(days=14)).isoformat()
                project['phases'][phase] = value
                project['assigned'][phase] = find_worker_for_phase(
                    phase, schedule, project['priority']
                )
            elif value:
                try:
                    project['phases'][phase] = int(value)
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


@app.route('/vacations', methods=['GET', 'POST'])
def vacation_list():
    vacations = load_vacations()
    if request.method == 'POST':
        vacations.append({
            'id': str(uuid.uuid4()),
            'worker': request.form['worker'],
            'start': request.form['start'],
            'end': request.form['end'],
        })
        save_vacations(vacations)
        return redirect(url_for('vacation_list'))
    return render_template('vacations.html', vacations=vacations, workers=list(WORKERS.keys()))


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
        project = {
            'id': str(uuid.uuid4()),
            'name': data['name'],
            'client': data['client'],
            'start_date': date.today().isoformat(),
            'due_date': data['due_date'],
            'priority': data.get('priority', 'Sin prioridad'),
            'color': color,
            'phases': {},
            'assigned': {},
            'image': image_path,
        }
        for phase in PHASE_ORDER:
            value = data.get(phase)
            if phase == 'pedidos':
                if not value:
                    value = (date.today() + timedelta(days=14)).isoformat()
                project['phases'][phase] = value
                project['assigned'][phase] = find_worker_for_phase(
                    phase, schedule, project['priority']
                )
            elif value:
                try:
                    project['phases'][phase] = int(value)
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
        filtered_projects = [
            p for p in projects
            if (not project_filter or project_filter.lower() in p['name'].lower())
            and (not client_filter or client_filter.lower() in p['client'].lower())
        ]
    else:
        filtered_projects = projects

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

    project_map = {p['id']: p for p in projects}

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
        projects=filtered_projects,
        today=date.today(),
        priorities=list(PRIORITY_ORDER.keys()),
        phases=PHASE_ORDER,
        all_workers=list(WORKERS.keys()),
        milestones=milestone_map,
        project_data=project_map,
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
            met = date.fromisoformat(end_dates[cid]) <= date.fromisoformat(pr['due_date'])
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
    return redirect(url_for('calendar_view'))


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


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
