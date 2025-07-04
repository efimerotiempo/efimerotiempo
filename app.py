from flask import Flask, render_template, request, jsonify, redirect, url_for
import sqlite3
import os

app = Flask(__name__)
DB_PATH = 'kanban.db'

# Database setup

def init_db():
    first_run = not os.path.exists(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    if first_run:
        cur.execute('''CREATE TABLE columns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            position INTEGER NOT NULL,
            color TEXT
        )''')
        cur.execute('''CREATE TABLE cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            assignee TEXT,
            due_date TEXT,
            column_id INTEGER,
            position INTEGER,
            parent_id INTEGER,
            FOREIGN KEY(column_id) REFERENCES columns(id),
            FOREIGN KEY(parent_id) REFERENCES cards(id)
        )''')
        # default columns with colors
        cur.executemany('INSERT INTO columns (name, position, color) VALUES (?, ?, ?)', [
            ('Todo', 1, "#e3f2fd"),
            ('Doing', 2, "#fff3cd"),
            ('Blocked', 3, "#f8d7da"),
            ('Done', 4, "#d4edda")
        ])
    else:
        # Ensure newer columns exist
        cur.execute('PRAGMA table_info(cards)')
        ccols = [r[1] for r in cur.fetchall()]
        if 'assignee' not in ccols:
            cur.execute('ALTER TABLE cards ADD COLUMN assignee TEXT')
        if 'due_date' not in ccols:
            cur.execute('ALTER TABLE cards ADD COLUMN due_date TEXT')
        cur.execute('PRAGMA table_info(columns)')
        tcols = [r[1] for r in cur.fetchall()]
        if 'color' not in tcols:
            cur.execute('ALTER TABLE columns ADD COLUMN color TEXT')
            cur.execute("UPDATE columns SET color='#e3f2fd' WHERE name='Todo'")
            cur.execute("UPDATE columns SET color='#fff3cd' WHERE name='Doing'")
            cur.execute("UPDATE columns SET color='#f8d7da' WHERE name='Blocked'")
            cur.execute("UPDATE columns SET color='#d4edda' WHERE name='Done'")
    conn.commit()
    conn.close()

init_db()

# Helpers

def query_db(query, args=(), one=False):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(query, args)
    rv = cur.fetchall()
    conn.commit()
    conn.close()
    if one:
        return dict(rv[0]) if rv else None
    return [dict(r) for r in rv]

def get_column_by_name(name):
    return query_db('SELECT id FROM columns WHERE name=?', (name,), one=True)

def get_card(card_id):
    return query_db('SELECT * FROM cards WHERE id=?', (card_id,), one=True)

def mark_children_done(card_id):
    done_col = get_column_by_name('Done')['id']
    children = query_db('SELECT id FROM cards WHERE parent_id=?', (card_id,))
    for ch in children:
        query_db('UPDATE cards SET column_id=? WHERE id=?', (done_col, ch['id']))
        mark_children_done(ch['id'])

def check_parent_done(parent_id):
    done_col = get_column_by_name('Done')['id']
    children = query_db('SELECT column_id FROM cards WHERE parent_id=?', (parent_id,))
    if children and all(c['column_id'] == done_col for c in children):
        pos = query_db('SELECT COALESCE(MAX(position),0)+1 AS m FROM cards WHERE column_id=?', (done_col,), one=True)['m']
        query_db('UPDATE cards SET column_id=?, position=? WHERE id=?', (done_col, pos, parent_id))
        parent = query_db('SELECT parent_id FROM cards WHERE id=?', (parent_id,), one=True)
        if parent and parent['parent_id']:
            check_parent_done(parent['parent_id'])

# Routes

@app.route('/')
def index():
    cols = query_db('SELECT id, name, color FROM columns ORDER BY position')
    columns = []
    for col in cols:
        cards = query_db('''SELECT id, title, description, assignee, due_date
                            FROM cards WHERE column_id=? AND parent_id IS NULL
                            ORDER BY position''', (col['id'],))
        for card in cards:
            children = query_db('SELECT id, title FROM cards WHERE parent_id=? ORDER BY position',
                               (card['id'],))
            card['children'] = children
        columns.append({'id': col['id'], 'name': col['name'],
                        'color': col['color'], 'cards': cards})
    all_cards = query_db('SELECT id, title FROM cards')
    return render_template('index.html', columns=columns, cards=all_cards)

@app.route('/add_card', methods=['POST'])
def add_card():
    title = request.form['title']
    description = request.form.get('description', '')
    assignee = request.form.get('assignee')
    due_date = request.form.get('due_date')
    column_id = request.form['column_id']
    parent_id = request.form.get('parent_id') or None
    max_pos = query_db('SELECT COALESCE(MAX(position), 0) AS maxp FROM cards WHERE column_id=?',
                       (column_id,), one=True)['maxp']
    query_db('''INSERT INTO cards (title, description, assignee, due_date, column_id, position, parent_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)''',
             (title, description, assignee, due_date, column_id, max_pos + 1, parent_id))
    return redirect(url_for('index'))

@app.route('/card/<int:card_id>', methods=['GET', 'POST'])
def edit_card(card_id):
    if request.method == 'POST':
        title = request.form['title']
        description = request.form.get('description', '')
        assignee = request.form.get('assignee')
        due_date = request.form.get('due_date')
        column_id = request.form['column_id']
        parent_id = request.form.get('parent_id') or None
        query_db('''UPDATE cards SET title=?, description=?, assignee=?, due_date=?,
                    column_id=?, parent_id=? WHERE id=?''',
                 (title, description, assignee, due_date, column_id, parent_id, card_id))
        return redirect(url_for('index'))
    card = get_card(card_id)
    return jsonify(card)

@app.route('/move_card', methods=['POST'])
def move_card():
    card_id = request.json['card_id']
    column_id = request.json['column_id']
    position = request.json['position']
    query_db('UPDATE cards SET column_id=?, position=? WHERE id=?', (column_id, position, card_id))
    # automation rules
    col = query_db('SELECT name FROM columns WHERE id=?', (column_id,), one=True)
    if col and col['name'] == 'Done':
        mark_children_done(card_id)
    parent = query_db('SELECT parent_id FROM cards WHERE id=?', (card_id,), one=True)
    if parent and parent['parent_id']:
        check_parent_done(parent['parent_id'])
    return jsonify(success=True)

if __name__ == '__main__':
    app.run(debug=True)
