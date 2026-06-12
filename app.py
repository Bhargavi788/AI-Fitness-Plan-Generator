from flask import Flask, render_template, request, redirect, url_for, session, g, flash
import json
import os
from dotenv import load_dotenv
from database import (
    init_db,
    register_user,
    login_user,
    save_fitness_plan,
    get_user_history,
    save_daily_progress,
    get_weekly_progress,
    calculate_weekly_score,
)

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret')
app.config['DATABASE'] = os.getenv('DATABASE', os.path.join(os.path.dirname(__file__), 'ai_fitness.db'))
app.config['GEMINI_API_KEY'] = os.getenv('GEMINI_API_KEY')

try:
    init_db(app.config['DATABASE'])
    print(f"Database ready at {app.config['DATABASE']}")
except Exception as e:
    print(f"Warning: Database initialization failed: {e}")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EXERCISES_PATH = os.path.join(BASE_DIR, "exercises.json")

try:
    with open(EXERCISES_PATH, "r", encoding="utf-8") as f:
        EXERCISES = json.load(f)
except Exception:
    EXERCISES = []


@app.before_request
def before_request():
    g.db_path = app.config['DATABASE']


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/test')
def test():
    return "Flask is working"


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        if not name or not email or not password:
            flash('All fields are required', 'danger')
            return redirect(url_for('register'))
        if '@' not in email or '.' not in email:
            flash('Please enter a valid email address', 'danger')
            return redirect(url_for('register'))
        if len(password) < 6:
            flash('Password must be at least 6 characters', 'danger')
            return redirect(url_for('register'))
        try:
            user_id = register_user(g.db_path, name, email, password)
            flash('Registration successful. Please log in.', 'success')
            return redirect(url_for('login'))
        except ValueError:
            flash('User already exists with that email.', 'danger')
            return redirect(url_for('register'))
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        if not email or not password:
            flash('Email and password required', 'danger')
            return redirect(url_for('login'))
        user = login_user(g.db_path, email, password)
        if not user:
            flash('Invalid email or password', 'danger')
            return redirect(url_for('login')) 
        session['user_id'] = user['id']
        session['user_name'] = user['name']
        flash('Logged in successfully', 'success')
        return redirect(url_for('dashboard'))
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out', 'info')
    return redirect(url_for('home'))


def calculate_bmi(weight_kg, height_cm):
    try:
        h = float(height_cm) / 100.0
        w = float(weight_kg)
        if h <= 0 or w <= 0:
            return None
        return round(w / (h * h), 2)
    except Exception:
        return None


def filter_exercises(equipment_list, level):
    # level: beginner/intermediate/advanced
    level = level.lower()
    allowed = []
    for ex in EXERCISES:
        ex_level = ex.get('difficulty', '').lower()
        eq = ex.get('equipment_needed', 'none')
        if eq not in equipment_list and eq != 'none':
            continue
        if level == 'beginner' and ex_level != 'beginner':
            continue
        if level == 'intermediate' and ex_level not in ('beginner', 'intermediate'):
            continue
        # advanced can use all
        allowed.append(ex)
    return allowed


def build_weekly_plan(profile):
    # profile contains age, gender, height, weight, goal, level, equipment (list), workout_days, diet_pref
    equipment = profile.get('equipment', [])
    level = profile.get('level', 'beginner')
    workout_days = int(profile.get('workout_days', 3))
    allowed = filter_exercises(equipment, level)
    if not allowed:
        raise ValueError('No matching exercises found for selected equipment/level')

    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    week = []
    idx = 0
    # choose variety of muscle groups
    for i in range(workout_days):
        day_name = days[i]
        # pick 4 exercises per workout from allowed
        picks = []
        start = (i * 4) % len(allowed)
        for j in range(4):
            ex = allowed[(start + j) % len(allowed)]
            picks.append({
                'exercise_name': ex['exercise_name'],
                'muscle_group': ex['muscle_group'],
                'sets': ex['recommended_sets'],
                'reps': ex['recommended_reps'],
                'rest_seconds': ex['rest_time_seconds'],
                'common_mistakes': ex.get('common_mistakes', '')
            })
        week.append({'day': day_name, 'workouts': picks})

    # insert rest days to fill 7-day week
    rest_days = [d for d in days if d not in [w['day'] for w in week]]
    for rd in rest_days:
        week.append({'day': rd, 'workouts': [], 'rest': True})

    # weekly summary
    summary = f"{workout_days} workouts per week, goal: {profile.get('goal')}, level: {level}"

    return {'week': week, 'summary': summary}


def generate_diet_plan(goal, diet_pref):
    goal = (goal or '').lower()
    diet_pref = (diet_pref or 'omnivore').lower()
    plan = {'notes': '', 'meals': []}
    if 'lose' in goal or 'fat' in goal:
        plan['notes'] = 'Calorie deficit, focus on protein and veggies.'
    elif 'muscle' in goal or 'build' in goal:
        plan['notes'] = 'Calorie surplus, prioritize protein and carbs around workouts.'
    else:
        plan['notes'] = 'Balanced diet with adequate protein.'

    if diet_pref == 'vegetarian':
        plan['meals'] = ['Oats with fruit and nuts', 'Lentil salad', 'Tofu stir-fry']
    elif diet_pref == 'vegan':
        plan['meals'] = ['Smoothie with plant protein', 'Chickpea salad', 'Quinoa bowl']
    else:
        plan['meals'] = ['Eggs and toast', 'Chicken salad', 'Grilled fish with veggies']
    return plan


def call_gemini(prompt_text):
    key = app.config.get('GEMINI_API_KEY')
    if not key:
        raise RuntimeError('Gemini API key missing')
    try:
        import google.generativeai as genai
        genai.configure(api_key=key)
        resp = genai.generate_text(model='gemini', prompt=prompt_text)
        return resp.text if hasattr(resp, 'text') else str(resp)
    except Exception as e:
        raise RuntimeError(f'Gemini API failure: {e}')


def build_gemini_prompt(profile):
    prompt = [
        'You are a professional fitness coach. Generate a single-week workout and diet plan using ONLY exercises from the provided JSON database. Match the user equipment and experience level. Mark rest days clearly. Include sets, reps, rest time, muscle group, and common mistakes. Also include a simple diet plan based on the goal and diet preference. Return clean HTML suitable for display in a Flask template.'
    ]
    prompt.append('User profile:')
    for k, v in profile.items():
        prompt.append(f"{k}: {v}")
    prompt.append('Exercises database:')
    # include short listing of exercises (name, equipment, difficulty, muscle)
    for ex in EXERCISES:
        prompt.append(f"- {ex['exercise_name']} | {ex['equipment_needed']} | {ex['difficulty']} | {ex['muscle_group']}")
    return '\n'.join(prompt)


def build_progress_summary(progress_rows, plan_week):
    total_days = len(plan_week)
    workout_done = sum(1 for row in progress_rows if row.get('workout_status') == 'Done')
    diet_done = sum(1 for row in progress_rows if row.get('diet_status') == 'Done')
    score = calculate_weekly_score(progress_rows, total_days)
    max_score = total_days * 20 if total_days else 0
    workout_pct = int(round((workout_done / total_days) * 100)) if total_days else 0
    diet_pct = int(round((diet_done / total_days) * 100)) if total_days else 0
    overall_pct = int(round((score / max_score) * 100)) if max_score else 0
    if overall_pct >= 80:
        message = 'Excellent consistency'
    elif overall_pct >= 50:
        message = 'Good progress, keep improving'
    else:
        message = 'Need more consistency'
    latest = progress_rows[-1] if progress_rows else {}
    return {
        'total_days': total_days,
        'workout_done': workout_done,
        'diet_done': diet_done,
        'workout_pct': workout_pct,
        'diet_pct': diet_pct,
        'score': score,
        'max_score': max_score,
        'overall_pct': overall_pct,
        'message': message,
        'goal_result': latest.get('goal_result', 'Not started') if latest else 'Not started',
        'current_weight': latest.get('current_weight') if latest else None,
        'energy_level': latest.get('energy_level') if latest else None,
        'notes': latest.get('notes', '') if latest else ''
    }


@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        # collect form
        age = request.form.get('age')
        gender = request.form.get('gender')
        height = request.form.get('height')
        weight = request.form.get('weight')
        goal = request.form.get('goal')
        level = request.form.get('level')
        equipment = request.form.getlist('equipment')
        workout_days = request.form.get('workout_days')
        diet_pref = request.form.get('diet_pref')

        # validation
        if not height or not weight:
            flash('Height and weight are required', 'danger')
            return redirect(url_for('dashboard'))
        bmi = calculate_bmi(weight, height)
        if bmi is None:
            flash('Invalid height or weight', 'danger')
            return redirect(url_for('dashboard'))

        # validate workout_days
        try:
            wd = int(workout_days or 3)
            if wd < 1 or wd > 7:
                flash('Workout days must be between 1 and 7', 'danger')
                return redirect(url_for('dashboard'))
        except Exception:
            flash('Invalid workout days value', 'danger')
            return redirect(url_for('dashboard'))

        # default equipment
        if not equipment:
            equipment = ['none']

        profile = {
            'age': age, 'gender': gender, 'height': height, 'weight': weight,
            'goal': goal, 'level': level, 'equipment': equipment, 'workout_days': wd, 'diet_pref': diet_pref
        }

        # try Gemini first
        try:
            prompt = build_gemini_prompt(profile)
            gemini_html = call_gemini(prompt)
            # Note: we still save a structured plan via local generator to ensure DB consistency
        except Exception:
            gemini_html = None

        try:
            workout_plan = build_weekly_plan(profile)
        except ValueError as e:
            flash(str(e), 'danger')
            return redirect(url_for('dashboard'))

        diet_plan = generate_diet_plan(goal, diet_pref)

        # Save to DB
        plan_id = save_fitness_plan(g.db_path, session['user_id'], goal, level, ','.join(equipment), wd, bmi, workout_plan, diet_plan)

        if gemini_html:
            return gemini_html
        return render_template('result.html', plan=workout_plan, diet=diet_plan, bmi=bmi, plan_id=plan_id, progress_summary=None, progress_rows=[], progress_by_day={})

    history = get_user_history(g.db_path, session['user_id'])
    progress_summary = None
    if history:
        latest_plan = history[0]
        progress_rows = get_weekly_progress(g.db_path, session['user_id'], latest_plan['id'])
        progress_summary = build_progress_summary(progress_rows, latest_plan['workout_plan']['week'])
    return render_template('dashboard.html', progress_summary=progress_summary)


@app.route('/result')
def result_get():
    # Show last result from DB for user
    if 'user_id' not in session:
        return redirect(url_for('login'))
    entries = get_user_history(g.db_path, session['user_id'])
    if not entries:
        flash('No saved plans yet', 'info')
        return redirect(url_for('dashboard'))
    latest = entries[0]
    progress_rows = get_weekly_progress(g.db_path, session['user_id'], latest['id'])
    progress_summary = build_progress_summary(progress_rows, latest['workout_plan']['week'])
    progress_by_day = {row['day_name']: row for row in progress_rows}
    return render_template(
        'result.html',
        plan=latest['workout_plan'],
        diet=latest['diet_plan'],
        bmi=latest['bmi'],
        plan_id=latest['id'],
        progress_summary=progress_summary,
        progress_rows=progress_rows,
        progress_by_day=progress_by_day,
    )


@app.route('/save-progress', methods=['POST'])
def save_progress():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    plan_id = request.form.get('plan_id')
    if not plan_id:
        flash('Progress save failed: missing plan reference.', 'danger')
        return redirect(url_for('dashboard'))

    try:
        plan_id = int(plan_id)
    except ValueError:
        flash('Invalid plan reference.', 'danger')
        return redirect(url_for('dashboard'))

    entries = get_user_history(g.db_path, session['user_id'])
    plan_entry = next((item for item in entries if item['id'] == plan_id), None)
    if not plan_entry:
        flash('Unable to find the associated fitness plan.', 'danger')
        return redirect(url_for('dashboard'))

    current_weight = request.form.get('current_weight')
    energy_level = request.form.get('energy_level')
    goal_result = request.form.get('goal_result')
    notes = request.form.get('notes') or ''
    try:
        current_weight_value = float(current_weight) if current_weight else None
    except ValueError:
        current_weight_value = None

    for day in plan_entry['workout_plan']['week']:
        day_name = day['day']
        workout_status = request.form.get(f'workout_status_{day_name}', 'Not Done')
        diet_status = request.form.get(f'diet_status_{day_name}', 'Not Done')
        save_daily_progress(
            g.db_path,
            session['user_id'],
            plan_id,
            day_name,
            workout_status,
            diet_status,
            current_weight_value,
            energy_level,
            goal_result,
            notes,
        )

    flash('Progress saved successfully.', 'success')
    return redirect(url_for('result_get'))


@app.route('/history')
def history():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    entries = get_user_history(g.db_path, session['user_id'])
    return render_template('history.html', entries=entries)


@app.route('/init-db')
def initdb_route():
    init_db(app.config['DATABASE'])
    flash('Database initialized', 'success')
    return redirect(url_for('home'))


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    host = '127.0.0.1'
    print(f"Starting AI Fitness Plan Generator on http://{host}:{port}")
    try:
        app.run(debug=True, host=host, port=port)
    except OSError as e:
        if 'Address already in use' in str(e):
            fallback_port = 5001
            print(f"Port {port} is busy, falling back to http://{host}:{fallback_port}")
            app.run(debug=True, host=host, port=fallback_port)
        else:
            raise
