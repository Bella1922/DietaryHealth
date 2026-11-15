"""
DietaryHealth — Flask Backend
Connects to dietaryhealth.db (SQLite) and serves the API the frontend needs.

Run:
    pip install flask bcrypt pandas --break-system-packages
    python app.py

Then open your frontend at http://127.0.0.1:5500 (VS Code Live Server)
and the API will be at http://127.0.0.1:5000/api/...

SECURITY NOTE: Passwords are NEVER stored in plaintext.
bcrypt hashes them before they touch the database.
"""

from flask import Flask, request, jsonify, session
from flask.helpers import send_from_directory
import sqlite3
import bcrypt
import os
import random
from datetime import date, datetime
from functools import wraps

try:
    import pandas as pd
    _PANDAS_OK = True
except ImportError:
    _PANDAS_OK = False

# Path to the Walmart CSV — search a few likely locations
def _find_csv():
    base = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(base, 'backend', 'Food_from_Walmart_with_healthy_474.csv'),
        os.path.join(base, 'DietaryHealth', 'src', 'backend', 'Food_from_Walmart_with_healthy_474.csv'),
        os.path.join(base, 'src', 'backend', 'Food_from_Walmart_with_healthy_474.csv'),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return candidates[0]  # fallback (will show warning if missing)

CSV_PATH = _find_csv()

# Cache the dataframe so we don't reload it on every request
_food_df = None

def get_food_df():
    global _food_df
    if _food_df is None and _PANDAS_OK and os.path.exists(CSV_PATH):
        _food_df = pd.read_csv(CSV_PATH)
    return _food_df

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


def init_db():
    """Create all tables if they don't exist yet."""
    conn = get_db()
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        first_name TEXT NOT NULL,
        last_name TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        created_at DATETIME DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS user_profiles (
        user_id INTEGER PRIMARY KEY REFERENCES users(id),
        age INTEGER,
        gender TEXT,
        activity_level TEXT,
        height_cm REAL,
        weight_kg REAL,
        calorie_goal INTEGER DEFAULT 2000,
        updated_at DATETIME DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS user_dietary_restrictions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER REFERENCES users(id),
        restriction TEXT NOT NULL,
        UNIQUE(user_id, restriction)
    );
    CREATE TABLE IF NOT EXISTS user_allergies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER REFERENCES users(id),
        allergen TEXT NOT NULL,
        UNIQUE(user_id, allergen)
    );
    CREATE TABLE IF NOT EXISTS user_goals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER REFERENCES users(id),
        goal TEXT NOT NULL,
        UNIQUE(user_id, goal)
    );
    CREATE TABLE IF NOT EXISTS meal_logs (
        log_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER REFERENCES users(id),
        log_date TEXT NOT NULL,
        meal_slot TEXT NOT NULL,
        food_name TEXT NOT NULL,
        kcal INTEGER DEFAULT 0,
        protein_g REAL,
        carbs_g REAL,
        fat_g REAL,
        logged_at DATETIME DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS water_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER REFERENCES users(id),
        log_date TEXT NOT NULL,
        cups INTEGER DEFAULT 0,
        updated_at DATETIME DEFAULT (datetime('now')),
        UNIQUE(user_id, log_date)
    );
    ''')
    conn.commit()
    conn.close()


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

    # Foods to avoid (free-text) — stored as dietary restrictions prefixed with "avoid:"
    conn.execute("DELETE FROM user_dietary_restrictions WHERE user_id = ? AND restriction LIKE 'avoid:%'", (user_id,))
    for f in data.get('foodsDislike', []):
        if f:
            conn.execute(
                "INSERT OR IGNORE INTO user_dietary_restrictions (user_id, restriction) VALUES (?, ?)",
                (user_id, f'avoid:{f.lower()}')
            )

    # Foods enjoyed (free-text) — stored as dietary restrictions prefixed with "like:"
    conn.execute("DELETE FROM user_dietary_restrictions WHERE user_id = ? AND restriction LIKE 'like:%'", (user_id,))
    for f in data.get('foodsLike', []):
        if f:
            conn.execute(
                "INSERT OR IGNORE INTO user_dietary_restrictions (user_id, restriction) VALUES (?, ?)",
                (user_id, f'like:{f.lower()}')
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
#  6. FOOD RECOMMENDATIONS
# ─────────────────────────────────────────────

@app.route('/api/recommendations', methods=['GET'])
@login_required
def get_recommendations():
    """
    Returns personalized food recommendations from the Walmart dataset,
    filtered by the user's dietary restrictions/allergies and weighted
    by their goal (lose / maintain / gain weight).

    Response shape:
      {
        "bmi": 22,
        "bmr": 1700,
        "dailyCalories": 1700,
        "goal": "maintain weight",
        "recommendations": {
          "breakfast": [ {name, category, subcategory, calories, protein, healthy}, ... ],
          "lunch":     [ ... ],
          "dinner":    [ ... ],
          "snack":     [ ... ]
        }
      }
    """
    user_id = session['user_id']
    conn = get_db()

    profile = conn.execute(
        """SELECT gender, age, height_cm, weight_kg, activity_level, calorie_goal
           FROM user_profiles WHERE user_id = ?""", (user_id,)
    ).fetchone()

    all_restrictions = [r['restriction'].lower() for r in conn.execute(
        "SELECT restriction FROM user_dietary_restrictions WHERE user_id = ?", (user_id,)
    ).fetchall()]

    # Separate liked foods, avoided foods, and regular restrictions
    restrictions = [r for r in all_restrictions if not r.startswith('avoid:') and not r.startswith('like:')]
    foods_dislike = [r[6:] for r in all_restrictions if r.startswith('avoid:')]
    foods_like    = [r[5:] for r in all_restrictions if r.startswith('like:')]

    allergies = [a['allergen'].lower() for a in conn.execute(
        "SELECT allergen FROM user_allergies WHERE user_id = ?", (user_id,)
    ).fetchall()]

    goals = [g['goal'].lower() for g in conn.execute(
        "SELECT goal FROM user_goals WHERE user_id = ?", (user_id,)
    ).fetchall()]

    conn.close()

    # ── Fallback if profile not filled yet ──────────────────────────────────
    if not profile:
        return jsonify({'error': 'Profile not found. Please complete the questionnaire.'}), 404

    gender        = profile['gender'] or 'M'
    age           = profile['age'] or 20
    height_cm     = profile['height_cm'] or 170
    weight_kg     = profile['weight_kg'] or 70
    activity      = (profile['activity_level'] or 'sedentary').lower()
    calorie_goal  = profile['calorie_goal'] or 2000

    # ── BMI ─────────────────────────────────────────────────────────────────
    height_m = height_cm / 100
    bmi = round(weight_kg / (height_m ** 2))

    # ── BMR (Mifflin-St Jeor) ────────────────────────────────────────────────
    if gender == 'M':
        bmr = (10 * weight_kg) + (6.25 * height_cm) - (5 * age) + 5
    else:
        bmr = (10 * weight_kg) + (6.25 * height_cm) - (5 * age) - 161

    # ── Daily calories based on activity ────────────────────────────────────
    multipliers = {
        'sedentary': 1.0,
        'lightly active': 1.375,
        'moderately active': 1.55,
        'very active': 1.725,
        'extra active': 1.9,
    }
    daily_calories = round(bmr * multipliers.get(activity, 1.0))

    # ── Determine goal ───────────────────────────────────────────────────────
    goal = goals[0] if goals else 'maintain weight'

    # ── Load & filter food dataframe ─────────────────────────────────────────
    df = get_food_df()
    if df is None:
        # pandas not installed or CSV missing — return empty recommendations
        return jsonify({
            'bmi': bmi, 'bmr': round(bmr), 'dailyCalories': daily_calories,
            'goal': goal,
            'recommendations': {'breakfast': [], 'lunch': [], 'dinner': [], 'snack': []},
            'warning': 'Food data not available. Make sure pandas is installed and the CSV is in backend/.'
        }), 200

    # Expand restriction/allergy terms into all related keywords to catch CSV category names
    BLOCK_KEYWORDS = {
        'no seafood':    ['seafood', 'fish', 'salmon', 'tuna', 'shrimp', 'crab', 'lobster', 'sardine', 'tilapia', 'cod', 'halibut', 'canned seafood', 'meat & seafood'],
        'seafood':       ['seafood', 'fish', 'salmon', 'tuna', 'shrimp', 'crab', 'lobster', 'sardine', 'tilapia', 'cod', 'halibut', 'canned seafood', 'meat & seafood'],
        'fish':          ['fish', 'salmon', 'tuna', 'tilapia', 'cod', 'halibut', 'sardine', 'canned seafood', 'seafood'],
        'shellfish':     ['shrimp', 'crab', 'lobster', 'scallop', 'clam', 'oyster', 'shellfish'],
        'vegan':         ['meat', 'poultry', 'seafood', 'fish', 'dairy', 'eggs', 'honey', 'beef', 'pork', 'chicken', 'turkey'],
        'vegetarian':    ['meat', 'poultry', 'seafood', 'fish', 'beef', 'pork', 'chicken', 'turkey'],
        'gluten-free':   ['bread', 'pasta', 'wheat', 'flour', 'cereal', 'cracker', 'biscuit', 'bakery'],
        'dairy-free':    ['milk', 'cheese', 'butter', 'cream', 'yogurt', 'dairy'],
        'milk':          ['milk', 'cheese', 'butter', 'cream', 'yogurt', 'dairy & eggs'],
        'egg':           ['egg'],
        'peanut':        ['peanut'],
        'tree nut':      ['almond', 'cashew', 'walnut', 'pecan', 'pistachio', 'tree nut', 'nut'],
        'soy':           ['soy', 'tofu', 'edamame'],
        'wheat':         ['wheat', 'bread', 'flour', 'pasta', 'cereal'],
        'sesame':        ['sesame', 'tahini'],
        'red meat':      ['beef', 'pork', 'lamb', 'steak', 'ground beef', 'bacon'],
        'meat':          ['meat', 'beef', 'pork', 'chicken', 'turkey', 'poultry', 'lamb'],
        'pork':          ['pork', 'bacon', 'ham', 'sausage'],
        'chicken':       ['chicken', 'poultry'],
    }

    # Build the full set of keywords to block
    blocked_keywords = set()
    for term in restrictions + allergies + foods_dislike:
        t = term.lower()
        # Handle "avoid:seafood" style terms saved from free-text
        if t.startswith('avoid:'):
            t = t[6:].strip()
        if t in BLOCK_KEYWORDS:
            blocked_keywords.update(BLOCK_KEYWORDS[t])
        else:
            # Free-text: split into words and block each one directly
            for word in t.replace(',', ' ').split():
                word = word.strip()
                if len(word) > 2:  # skip very short words like "no", "or"
                    if word in BLOCK_KEYWORDS:
                        blocked_keywords.update(BLOCK_KEYWORDS[word])
                    else:
                        blocked_keywords.add(word)

    if blocked_keywords:
        def row_blocked(row):
            text = ' '.join([
                str(row.get('Category', '')),
                str(row.get('Subcategory', '')),
                str(row.get('Food Name', '')),
            ]).lower()
            return any(kw in text for kw in blocked_keywords)
        mask = df.apply(row_blocked, axis=1)
        filtered = df[~mask].copy()
    else:
        filtered = df.copy()

    # ── Score foods by goal ──────────────────────────────────────────────────
    # lose weight  → favor low-calorie, high-protein, Healthy=True
    # gain weight  → favor high-calorie, high-protein
    # maintain     → favor Healthy=True, balanced calories
    if 'lose' in goal:
        filtered['_score'] = (
            filtered['Healthy'].astype(int) * 3
            + filtered['Protein (g)'] / 10
            - filtered['Calories'] / 200
        )
    elif 'gain' in goal:
        filtered['_score'] = (
            filtered['Protein (g)'] / 5
            + filtered['Calories'] / 100
        )
    else:  # maintain
        filtered['_score'] = (
            filtered['Healthy'].astype(int) * 2
            + filtered['Protein (g)'] / 10
        )

    # ── Boost score for foods the user said they enjoy ──────────────────────
    if foods_like:
        def liked_boost(row):
            name_text = str(row.get('Food Name', '')).lower()
            return 5 if any(liked in name_text for liked in foods_like) else 0
        filtered['_score'] = filtered['_score'] + filtered.apply(liked_boost, axis=1)

    filtered = filtered.sort_values('_score', ascending=False)

    # ── Assign categories to meal slots ─────────────────────────────────────
    SLOT_CATEGORIES = {
        'breakfast': ['Breakfast & Cereal', 'Dairy & Eggs', 'Bakery & Bread', 'Beverages'],
        'lunch':     ['Meat & Seafood', 'Deli', 'Dairy & Eggs', 'Produce', 'Bakery & Bread'],
        'dinner':    ['Meat & Seafood', 'Produce', 'Pantry', 'Frozen'],
        'snack':     ['Snacks', 'Beverages', 'Produce', 'Dairy & Eggs'],
    }

    def pick_for_slot(slot, n=3):
        cats = SLOT_CATEGORIES[slot]
        pool = filtered[filtered['Category'].isin(cats)]
        # Drop duplicates by subcategory so we get variety
        pool = pool.drop_duplicates(subset=['Subcategory'])
        # Take top scored, then shuffle slightly for variety
        top = pool.head(n * 3)
        sample = top.sample(min(n, len(top)), random_state=random.randint(0, 9999))
        return [{
            'name':        row['Food Name'],
            'category':    row['Category'],
            'subcategory': row['Subcategory'],
            'servingSize': row['Serving Size'],
            'calories':    int(row['Calories']),
            'protein':     float(row['Protein (g)']),
            'healthy':     bool(row['Healthy']),
        } for _, row in sample.iterrows()]

    recommendations = {
        'breakfast': pick_for_slot('breakfast'),
        'lunch':     pick_for_slot('lunch'),
        'dinner':    pick_for_slot('dinner'),
        'snack':     pick_for_slot('snack'),
    }

    return jsonify({
        'bmi':           bmi,
        'bmr':           round(bmr),
        'dailyCalories': daily_calories,
        'goal':          goal,
        'recommendations': recommendations,
    }), 200


# ─────────────────────────────────────────────
#  Run the app
# ─────────────────────────────────────────────

if __name__ == '__main__':
    init_db()
    print(f"Database: {DB_PATH}")
    print("API running at http://127.0.0.1:5000")
    print("Keep this terminal open while using the app.")
    app.run(debug=True, port=5000)