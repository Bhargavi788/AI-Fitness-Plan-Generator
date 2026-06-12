import sqlite3
from datetime import datetime
import os
from werkzeug.security import generate_password_hash, check_password_hash
import json


def get_db(db_path):
	conn = sqlite3.connect(db_path)
	conn.row_factory = sqlite3.Row
	return conn


def init_db(db_path=None):
	if db_path is None:
		db_path = os.path.join(os.path.dirname(__file__), 'ai_fitness.db')
	conn = sqlite3.connect(db_path)
	cur = conn.cursor()
	cur.execute('''
	CREATE TABLE IF NOT EXISTS users (
		id INTEGER PRIMARY KEY AUTOINCREMENT,
		name TEXT NOT NULL,
		email TEXT UNIQUE NOT NULL,
		password TEXT NOT NULL
	)
	''')
	cur.execute('''
	CREATE TABLE IF NOT EXISTS fitness_history (
		id INTEGER PRIMARY KEY AUTOINCREMENT,
		user_id INTEGER NOT NULL,
		goal TEXT,
		level TEXT,
		equipment TEXT,
		workout_days INTEGER,
		bmi REAL,
		workout_plan TEXT,
		diet_plan TEXT,
		created_at TEXT DEFAULT CURRENT_TIMESTAMP,
		FOREIGN KEY(user_id) REFERENCES users(id)
	)
	''')
	cur.execute('''
	CREATE TABLE IF NOT EXISTS progress_tracking (
		id INTEGER PRIMARY KEY AUTOINCREMENT,
		user_id INTEGER NOT NULL,
		plan_id INTEGER NOT NULL,
		day_name TEXT NOT NULL,
		workout_status TEXT NOT NULL,
		diet_status TEXT NOT NULL,
		current_weight REAL,
		energy_level TEXT,
		goal_result TEXT,
		notes TEXT,
		created_at TEXT DEFAULT CURRENT_TIMESTAMP,
		FOREIGN KEY(user_id) REFERENCES users(id),
		FOREIGN KEY(plan_id) REFERENCES fitness_history(id)
	)
	''')
	conn.commit()
	conn.close()


def register_user(db_path, name, email, password):
	conn = sqlite3.connect(db_path)
	cur = conn.cursor()
	cur.execute('SELECT id FROM users WHERE email = ?', (email,))
	if cur.fetchone():
		conn.close()
		raise ValueError('User already exists')
	hashed = generate_password_hash(password)
	cur.execute('INSERT INTO users (name, email, password) VALUES (?, ?, ?)', (name, email, hashed))
	conn.commit()
	user_id = cur.lastrowid
	conn.close()
	return user_id


def login_user(db_path, email, password):
	conn = sqlite3.connect(db_path)
	cur = conn.cursor()
	cur.execute('SELECT id, name, email, password FROM users WHERE email = ?', (email,))
	row = cur.fetchone()
	conn.close()
	if not row:
		return None
	user_id, name, email_db, hashed = row[0], row[1], row[2], row[3]
	if check_password_hash(hashed, password):
		return {'id': user_id, 'name': name, 'email': email_db}
	return None


def save_fitness_plan(db_path, user_id, goal, level, equipment, workout_days, bmi, workout_plan, diet_plan):
	conn = sqlite3.connect(db_path)
	cur = conn.cursor()
	cur.execute('INSERT INTO fitness_history (user_id, goal, level, equipment, workout_days, bmi, workout_plan, diet_plan) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
			(user_id, goal, level, equipment, workout_days, bmi, json.dumps(workout_plan), json.dumps(diet_plan)))
	conn.commit()
	fid = cur.lastrowid
	conn.close()
	return fid


def get_user_history(db_path, user_id):
	conn = sqlite3.connect(db_path)
	conn.row_factory = sqlite3.Row
	cur = conn.cursor()
	cur.execute('SELECT id, goal, level, equipment, workout_days, bmi, workout_plan, diet_plan, created_at FROM fitness_history WHERE user_id = ? ORDER BY created_at DESC', (user_id,))
	rows = cur.fetchall()
	conn.close()
	results = []
	for r in rows:
		results.append({
			'id': r['id'],
			'goal': r['goal'],
			'level': r['level'],
			'equipment': r['equipment'],
			'workout_days': r['workout_days'],
			'bmi': r['bmi'],
			'workout_plan': json.loads(r['workout_plan']),
			'diet_plan': json.loads(r['diet_plan']),
			'created_at': r['created_at']
		})
	return results


def save_daily_progress(db_path, user_id, plan_id, day_name, workout_status, diet_status, current_weight, energy_level, goal_result, notes):
	conn = sqlite3.connect(db_path)
	cur = conn.cursor()
	cur.execute('INSERT INTO progress_tracking (user_id, plan_id, day_name, workout_status, diet_status, current_weight, energy_level, goal_result, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
			(user_id, plan_id, day_name, workout_status, diet_status, current_weight, energy_level, goal_result, notes))
	conn.commit()
	row_id = cur.lastrowid
	conn.close()
	return row_id


def get_weekly_progress(db_path, user_id, plan_id):
	conn = sqlite3.connect(db_path)
	conn.row_factory = sqlite3.Row
	cur = conn.cursor()
	cur.execute('''
	SELECT pt.* FROM progress_tracking pt
	INNER JOIN (
		SELECT day_name, MAX(created_at) AS latest_created
		FROM progress_tracking
		WHERE user_id = ? AND plan_id = ?
		GROUP BY day_name
	) latest ON pt.day_name = latest.day_name AND pt.created_at = latest.latest_created
	WHERE pt.user_id = ? AND pt.plan_id = ?
	ORDER BY CASE pt.day_name
		WHEN 'Monday' THEN 1
		WHEN 'Tuesday' THEN 2
		WHEN 'Wednesday' THEN 3
		WHEN 'Thursday' THEN 4
		WHEN 'Friday' THEN 5
		WHEN 'Saturday' THEN 6
		WHEN 'Sunday' THEN 7
		ELSE 8 END
	''', (user_id, plan_id, user_id, plan_id))
	rows = cur.fetchall()
	conn.close()
	return [dict(r) for r in rows]


def calculate_weekly_score(progress_rows, total_days):
	score = 0
	for row in progress_rows:
		if row.get('workout_status') == 'Done':
			score += 10
		if row.get('diet_status') == 'Done':
			score += 10
	return score
