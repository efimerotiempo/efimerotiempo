from flask import Flask, render_template, request, redirect, url_for
from datetime import date, timedelta
import uuid
import json
import random
from schedule import (
    load_projects,
    save_projects,
    schedule_projects,
    load_dismissed,
    save_dismissed,
    PRIORITY_ORDER,
    PHASE_ORDER,
)

app = Flask(__name__)

COLORS = [
    '#f8b195',
    '#c06c84',
    '#355c7d',
    '#6c5b7b',
    '#f67280',
    '#99b898',
    '#ff8c94',
]


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
    start = date.today()
    start -= timedelta(days=start.weekday())  # Monday
    days = [start + timedelta(days=i) for i in range(14)]
    return render_template(
        'index.html',
        schedule=schedule,
        days=days,
        conflicts=conflicts,
    )


@app.route('/projects')
def project_list():
    projects = load_projects()
    return render_template(
        'projects.html',
        projects=projects,
        priorities=list(PRIORITY_ORDER.keys()),
        phases=PHASE_ORDER,
    )


@app.route('/add', methods=['GET', 'POST'])
def add_project():
    if request.method == 'POST':
        data = request.form
        project = {
            'id': str(uuid.uuid4()),
            'name': data['name'],
            'client': data['client'],
            'start_date': date.today().isoformat(),
            'due_date': data['due_date'],
            'priority': data.get('priority', 'Sin prioridad'),
            'color': random.choice(COLORS),
            'phases': {}
        }
        for phase in PHASE_ORDER:
            hours = data.get(phase)
            if hours:
                try:
                    project['phases'][phase] = int(hours)
                except ValueError:
                    pass
        projects = load_projects()
        projects.append(project)
        save_projects(projects)
        return redirect(url_for('project_list'))
    return render_template('add_project.html')


@app.route('/update_priority/<pid>', methods=['POST'])
def update_priority(pid):
    projects = load_projects()
    for p in projects:
        if p['id'] == pid:
            p['priority'] = request.form['priority']
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
