"""
DietaryHealth — Flask Backend
Connects to dietaryhealth.db (SQLite) and serves the API the frontend needs.

Run:
    pip install flask bcrypt --break-system-packages
    python app.py

Then open your frontend at http://127.0.0.1:5500 (VS Code Live Server)
and the API will be at http://127.0.0.1:5000/api/...

"""

from flask import Flask, request, jsonify, session
from flask.helpers import send_from_directory
import sqlite3
import bcrypt
import os
from datetime import date, datetime
from functools import wraps

app = Flask(__name__)

# Change this to any long random string for production
app.secret_key = 'dh-dev-secret-key-change-in-production'

# Path to the database — sits next to app.py
DB_PATH = os.path.join(os.path.dirname(__file__), 'dietaryhealth.db')


# ─────────────────────────────────────────────
#  Database helper
# ─────────────────────────────────────────────

def get_db():
    """Open a database connection with foreign keys enabled."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row   # lets us access columns by name
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ─────────────────────────────────────────────
#  CORS — allow VS Code Live Server origin
# ─────────────────────────────────────────────

@app.after_request
def add_cors_headers(response):
    allowed_origins = [
        'http://127.0.0.1:5500',
        'http://localhost:5500',
        'http://127.0.0.1:5501',
        'http://localhost:5501',
    ]
    origin = request.headers.get('Origin', '')
    if origin in allowed_origins:
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, PATCH, DELETE, OPTIONS'
    return response

@app.route('/', defaults={'path': ''}, methods=['OPTIONS'])
@app.route('/<path:path>', methods=['OPTIONS'])
def handle_options(path):
    return '', 204


# ─────────────────────────────────────────────
#  Auth helper — require login for protected routes
# ─────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Not logged in'}), 401
        return f(*args, **kwargs)
    return decorated


# ─────────────────────────────────────────────
#  1. AUTH ROUTES
# ─────────────────────────────────────────────

@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    required = ['username', 'email', 'firstName', 'lastName', 'password']
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({'error': f'Missing fields: {", ".join(missing)}'}), 400

    # Hash the password with bcrypt
    password_hash = bcrypt.hashpw(
        data['password'].encode('utf-8'),
        bcrypt.gensalt()
    ).decode('utf-8')

    try:
        conn = get_db()
        cursor = conn.execute(
            """INSERT INTO users (username, email, first_name, last_name, password_hash)
               VALUES (?, ?, ?, ?, ?)""",
            (data['username'], data['email'].lower(),
             data['firstName'], data['lastName'], password_hash)
        )
        conn.commit()
        user_id = cursor.lastrowid

        # Set session
        session['user_id'] = user_id
        session['username'] = data['username']

        conn.close()
        return jsonify({
            'user': {
                'userId': user_id,
                'username': data['username'],
                'firstName': data['firstName'],
                'lastName': data['lastName'],
            }
        }), 201

    except sqlite3.IntegrityError as e:
        if 'username' in str(e):
            return jsonify({'error': 'Username already taken'}), 409
        if 'email' in str(e):
            return jsonify({'error': 'Email already registered'}), 409
        return jsonify({'error': 'Registration failed'}), 409


@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data or not data.get('username') or not data.get('password'):
        return jsonify({'error': 'Username and password required'}), 400

    conn = get_db()
    user = conn.execute(
        "SELECT * FROM users WHERE username = ?", (data['username'],)
    ).fetchone()
    conn.close()

    if not user:
        return jsonify({'error': 'Invalid username or password'}), 401

    # Check password against hash
    if not bcrypt.checkpw(data['password'].encode('utf-8'),
                          user['password_hash'].encode('utf-8')):
        return jsonify({'error': 'Invalid username or password'}), 401

    session['user_id'] = user['user_id']
    session['username'] = user['username']

    return jsonify({
        'user': {
            'userId': user['user_id'],
            'username': user['username'],
            'firstName': user['first_name'],
            'lastName': user['last_name'],
        }
    }), 200


@app.route('/api/auth/logout', methods=['POST'])
@login_required
def logout():
    session.clear()
    return jsonify({'message': 'Logged out'}), 200


# ─────────────────────────────────────────────
#  2. PROFILE ROUTES
# ─────────────────────────────────────────────

@app.route('/api/profile', methods=['POST'])
@login_required
def save_profile():
    data = request.get_json() or {}
    user_id = session['user_id']
    conn = get_db()

    # Upsert the profile row
    conn.execute(
        """INSERT INTO user_profiles
               (user_id, age, gender, activity_level, height_cm, weight_kg, calorie_goal)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(user_id) DO UPDATE SET
               age            = excluded.age,
               gender         = excluded.gender,
               activity_level = excluded.activity_level,
               height_cm      = excluded.height_cm,
               weight_kg      = excluded.weight_kg,
               calorie_goal   = excluded.calorie_goal,
               updated_at     = datetime('now')""",
        (user_id,
         data.get('age'), data.get('gender'), data.get('activityLevel'),
         data.get('heightCm'), data.get('weightKg'), data.get('calorieGoal', 2000))
    )

    # Dietary restrictions — replace all
    conn.execute("DELETE FROM user_dietary_restrictions WHERE user_id = ?", (user_id,))
    for r in data.get('dietaryRestrictions', []):
        conn.execute(
            "INSERT OR IGNORE INTO user_dietary_restrictions (user_id, restriction) VALUES (?, ?)",
            (user_id, r)
        )

    # Allergies — replace all
    conn.execute("DELETE FROM user_allergies WHERE user_id = ?", (user_id,))
    for a in data.get('allergies', []):
        conn.execute(
            "INSERT OR IGNORE INTO user_allergies (user_id, allergen) VALUES (?, ?)",
            (user_id, a)
        )

    # Goals — replace all
    conn.execute("DELETE FROM user_goals WHERE user_id = ?", (user_id,))
    for g in data.get('goals', []):
        conn.execute(
            "INSERT OR IGNORE INTO user_goals (user_id, goal) VALUES (?, ?)",
            (user_id, g)
        )

    conn.commit()
    conn.close()
    return jsonify({'message': 'Profile saved'}), 201


@app.route('/api/profile', methods=['GET'])
@login_required
def get_profile():
    user_id = session['user_id']
    conn = get_db()

    profile = conn.execute(
        "SELECT * FROM user_profiles WHERE user_id = ?", (user_id,)
    ).fetchone()

    restrictions = [r['restriction'] for r in conn.execute(
        "SELECT restriction FROM user_dietary_restrictions WHERE user_id = ?", (user_id,)
    ).fetchall()]

    allergies = [a['allergen'] for a in conn.execute(
        "SELECT allergen FROM user_allergies WHERE user_id = ?", (user_id,)
    ).fetchall()]

    goals = [g['goal'] for g in conn.execute(
        "SELECT goal FROM user_goals WHERE user_id = ?", (user_id,)
    ).fetchall()]

    conn.close()

    if not profile:
        return jsonify({}), 200

    return jsonify({
        'age': profile['age'],
        'gender': profile['gender'],
        'activityLevel': profile['activity_level'],
        'heightCm': profile['height_cm'],
        'weightKg': profile['weight_kg'],
        'calorieGoal': profile['calorie_goal'],
        'dietaryRestrictions': restrictions,
        'allergies': allergies,
        'goals': goals,
    }), 200


@app.route('/api/profile', methods=['PATCH'])
@login_required
def update_profile():
    # Reuse save_profile logic (upsert handles partial updates too)
    return save_profile()


# ─────────────────────────────────────────────
#  3. MEAL LOG ROUTES
# ─────────────────────────────────────────────

@app.route('/api/meals', methods=['GET'])
@login_required
def get_meals():
    user_id = session['user_id']
    log_date = request.args.get('date', date.today().isoformat())

    conn = get_db()
    rows = conn.execute(
        """SELECT log_id, log_date, meal_slot, food_name, kcal,
                  protein_g, carbs_g, fat_g, logged_at
           FROM meal_logs
           WHERE user_id = ? AND log_date = ?
           ORDER BY logged_at""",
        (user_id, log_date)
    ).fetchall()
    conn.close()

    return jsonify([{
        'logId': r['log_id'],
        'logDate': r['log_date'],
        'mealSlot': r['meal_slot'],
        'foodName': r['food_name'],
        'kcal': r['kcal'],
        'proteinG': r['protein_g'],
        'carbsG': r['carbs_g'],
        'fatG': r['fat_g'],
        'loggedAt': r['logged_at'],
    } for r in rows]), 200


@app.route('/api/meals', methods=['POST'])
@login_required
def add_meal():
    data = request.get_json() or {}
    user_id = session['user_id']

    required = ['logDate', 'mealSlot', 'foodName']
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({'error': f'Missing fields: {", ".join(missing)}'}), 400

    conn = get_db()
    cursor = conn.execute(
        """INSERT INTO meal_logs
               (user_id, log_date, meal_slot, food_name, kcal, protein_g, carbs_g, fat_g)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (user_id, data['logDate'], data['mealSlot'], data['foodName'],
         data.get('kcal', 0), data.get('proteinG'), data.get('carbsG'), data.get('fatG'))
    )
    conn.commit()
    log_id = cursor.lastrowid
    conn.close()

    return jsonify({'logId': log_id, 'message': 'Meal logged'}), 201


@app.route('/api/meals/<int:log_id>', methods=['DELETE'])
@login_required
def delete_meal(log_id):
    user_id = session['user_id']
    conn = get_db()

    row = conn.execute(
        "SELECT user_id FROM meal_logs WHERE log_id = ?", (log_id,)
    ).fetchone()

    if not row:
        conn.close()
        return jsonify({'error': 'Entry not found'}), 404
    if row['user_id'] != user_id:
        conn.close()
        return jsonify({'error': 'Not authorized'}), 403

    conn.execute("DELETE FROM meal_logs WHERE log_id = ?", (log_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Meal deleted'}), 200


@app.route('/api/meals/summary', methods=['GET'])
@login_required
def meals_summary():
    user_id = session['user_id']
    start = request.args.get('startDate', date.today().isoformat())
    end = request.args.get('endDate', date.today().isoformat())

    conn = get_db()
    rows = conn.execute(
        """SELECT log_date, SUM(kcal) AS total_kcal
           FROM meal_logs
           WHERE user_id = ? AND log_date BETWEEN ? AND ?
           GROUP BY log_date ORDER BY log_date""",
        (user_id, start, end)
    ).fetchall()
    conn.close()

    return jsonify([{
        'logDate': r['log_date'],
        'totalKcal': r['total_kcal'],
    } for r in rows]), 200


# ─────────────────────────────────────────────
#  4. WATER LOG ROUTES
# ─────────────────────────────────────────────

@app.route('/api/water', methods=['GET'])
@login_required
def get_water():
    user_id = session['user_id']
    log_date = request.args.get('date', date.today().isoformat())

    conn = get_db()
    row = conn.execute(
        "SELECT cups FROM water_logs WHERE user_id = ? AND log_date = ?",
        (user_id, log_date)
    ).fetchone()
    conn.close()

    return jsonify({
        'logDate': log_date,
        'cups': row['cups'] if row else 0,
    }), 200


@app.route('/api/water', methods=['PUT'])
@login_required
def update_water():
    data = request.get_json() or {}
    user_id = session['user_id']
    log_date = data.get('logDate', date.today().isoformat())
    cups = data.get('cups', 0)

    if not (0 <= cups <= 8):
        return jsonify({'error': 'cups must be between 0 and 8'}), 400

    conn = get_db()
    conn.execute(
        """INSERT INTO water_logs (user_id, log_date, cups)
           VALUES (?, ?, ?)
           ON CONFLICT(user_id, log_date) DO UPDATE SET
               cups = excluded.cups,
               updated_at = datetime('now')""",
        (user_id, log_date, cups)
    )
    conn.commit()
    conn.close()

    return jsonify({'message': 'Water updated', 'cups': cups}), 200


# ─────────────────────────────────────────────
#  5. DASHBOARD SUMMARY (all today's data in one call)
# ─────────────────────────────────────────────

@app.route('/api/dashboard/today', methods=['GET'])
@login_required
def dashboard_today():
    user_id = session['user_id']
    today = date.today().isoformat()

    conn = get_db()

    # Calorie goal from profile
    profile = conn.execute(
        "SELECT calorie_goal FROM user_profiles WHERE user_id = ?", (user_id,)
    ).fetchone()
    calorie_goal = profile['calorie_goal'] if profile else 2000

    # Today's meals
    meal_rows = conn.execute(
        """SELECT log_id, meal_slot, food_name, kcal, logged_at
           FROM meal_logs WHERE user_id = ? AND log_date = ?
           ORDER BY logged_at""",
        (user_id, today)
    ).fetchall()

    # Today's water
    water_row = conn.execute(
        "SELECT cups FROM water_logs WHERE user_id = ? AND log_date = ?",
        (user_id, today)
    ).fetchone()

    conn.close()

    meals = [{
        'logId': r['log_id'],
        'mealSlot': r['meal_slot'],
        'foodName': r['food_name'],
        'kcal': r['kcal'],
        'loggedAt': r['logged_at'],
    } for r in meal_rows]

    total_kcal = sum(m['kcal'] for m in meals)

    return jsonify({
        'date': today,
        'calorieGoal': calorie_goal,
        'totalKcalToday': total_kcal,
        'cupsToday': water_row['cups'] if water_row else 0,
        'meals': meals,
    }), 200


# ─────────────────────────────────────────────
#  Run the app
# ─────────────────────────────────────────────

if __name__ == '__main__':
    print(f"Database: {DB_PATH}")
    print("API running at http://127.0.0.1:5000")
    print("Keep this terminal open while using the app.")
    app.run(debug=True, port=5000)