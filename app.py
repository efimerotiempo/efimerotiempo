import json
import uuid
from typing import List, Dict

PROJECTS_FILE = 'data/projects.json'
CONFLICTS_FILE = 'data/conflicts.json'


def load_projects() -> List[Dict]:
    try:
        with open(PROJECTS_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return []


def save_projects(projects: List[Dict]):
    with open(PROJECTS_FILE, 'w') as f:
        json.dump(projects, f, indent=2)


def append_conflict(entry: Dict):
    try:
        with open(CONFLICTS_FILE, 'r') as f:
            conflicts = json.load(f)
    except FileNotFoundError:
        conflicts = []
    conflicts.append(entry)
    with open(CONFLICTS_FILE, 'w') as f:
        json.dump(conflicts, f, indent=2)


def update_priority(project_name: str, new_priority: int):
    """Update project priority and log a conflict."""
    projects = load_projects()
    for p in projects:
        if p.get('name') == project_name:
            old_priority = p.get('priority')
            p['priority'] = new_priority
            save_projects(projects)
            conflict = {
                'key': str(uuid.uuid4()),
                'project': project_name,
                'note': f"Priority changed from {old_priority} to {new_priority}. Other tasks may shift."
            }
            append_conflict(conflict)
            return True
    return False


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Update project priority.')
    parser.add_argument('name', help='Project name')
    parser.add_argument('priority', type=int, help='New priority')
    args = parser.parse_args()
    if update_priority(args.name, args.priority):
        print('Priority updated.')
    else:
        print('Project not found.')


if __name__ == '__main__':
    main()
