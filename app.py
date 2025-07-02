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
            position INTEGER NOT NULL
        )''')
        cur.execute('''CREATE TABLE cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            column_id INTEGER,
            position INTEGER,
            parent_id INTEGER,
            FOREIGN KEY(column_id) REFERENCES columns(id),
            FOREIGN KEY(parent_id) REFERENCES cards(id)
        )''')
        # default columns
        cur.executemany('INSERT INTO columns (name, position) VALUES (?, ?)', [
            ('Todo', 1),
            ('Doing', 2),
            ('Done', 3)
        ])
        conn.commit()
    conn.close()

init_db()

# Helpers

def query_db(query, args=(), one=False):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(query, args)
    rv = cur.fetchall()
    conn.commit()
    conn.close()
    return (rv[0] if rv else None) if one else rv

# Routes

@app.route('/')
def index():
    cols = query_db('SELECT id, name FROM columns ORDER BY position')
    columns = []
    for col in cols:
        cards = query_db('SELECT id, title, description, parent_id FROM cards WHERE column_id=? ORDER BY position', (col[0],))
        columns.append({'id': col[0], 'name': col[1], 'cards': cards})
    all_cards = query_db('SELECT id, title FROM cards')
    return render_template('index.html', columns=columns, cards=all_cards)

@app.route('/add_card', methods=['POST'])
def add_card():
    title = request.form['title']
    description = request.form.get('description', '')
    column_id = request.form['column_id']
    parent_id = request.form.get('parent_id') or None
    max_pos = query_db('SELECT COALESCE(MAX(position), 0) FROM cards WHERE column_id=?', (column_id,), one=True)[0]
    query_db('INSERT INTO cards (title, description, column_id, position, parent_id) VALUES (?, ?, ?, ?, ?)',
             (title, description, column_id, max_pos + 1, parent_id))
    return redirect(url_for('index'))

@app.route('/move_card', methods=['POST'])
def move_card():
    card_id = request.json['card_id']
    column_id = request.json['column_id']
    position = request.json['position']
    query_db('UPDATE cards SET column_id=?, position=? WHERE id=?', (column_id, position, card_id))
    return jsonify(success=True)

if __name__ == '__main__':
    app.run(debug=True)
