-- ============================================================
--  SECURITY NOTE: passwords are NEVER stored here.
--  The users table stores password_hash only (bcrypt via Python).
--  See app.py for hashing logic.
-- ============================================================

PRAGMA foreign_keys = ON;   -- SQLite disables FK enforcement by default

-- ------------------------------------------------------------
--  1. USERS
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    user_id       INTEGER  PRIMARY KEY AUTOINCREMENT,
    username      TEXT     NOT NULL UNIQUE,
    email         TEXT     NOT NULL UNIQUE,
    first_name    TEXT     NOT NULL,
    last_name     TEXT     NOT NULL,
    password_hash TEXT     NOT NULL,   -- bcrypt hash, NEVER plaintext
    created_at    TEXT     DEFAULT (datetime('now'))
);

-- ------------------------------------------------------------
--  2. USER PROFILES  (questionnaire — physical stats & goals)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_profiles (
    profile_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        INTEGER NOT NULL UNIQUE,

    age            INTEGER,
    gender         TEXT CHECK(gender IN ('male','female','other')),
    activity_level TEXT CHECK(activity_level IN (
                       'mostly_sitting','lightly_active',
                       'moderately_active','very_active','athlete')),

    height_cm      REAL,    -- always stored in cm; frontend converts ft/in ↔ cm
    weight_kg      REAL,    -- always stored in kg; frontend converts lbs ↔ kg

    calorie_goal   INTEGER  DEFAULT 2000,
    notes          TEXT,
    updated_at     TEXT     DEFAULT (datetime('now')),

    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- ------------------------------------------------------------
--  3. DIETARY RESTRICTIONS  (questionnaire step — checkboxes)
--     Remaining options: Vegan, Vegetarian, Pescatarian, None
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_dietary_restrictions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    restriction TEXT    NOT NULL,
    UNIQUE (user_id, restriction),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- ------------------------------------------------------------
--  4. ALLERGIES  (questionnaire step — checkboxes)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_allergies (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id   INTEGER NOT NULL,
    allergen  TEXT    NOT NULL,   -- e.g. 'peanut', 'tree nuts', 'shellfish'
    UNIQUE (user_id, allergen),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- ------------------------------------------------------------
--  5. GOALS  (questionnaire step — radio/checkboxes)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_goals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    goal        TEXT    NOT NULL,
    custom_text TEXT,             -- filled when goal = 'other'
    UNIQUE (user_id, goal),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- ------------------------------------------------------------
--  6. MEAL LOGS  (calendar.html entries)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS meal_logs (
    log_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,

    log_date        TEXT    NOT NULL,   -- stored as 'YYYY-MM-DD'
    meal_slot       TEXT    NOT NULL
                    CHECK(meal_slot IN ('Breakfast','Lunch','Dinner','Snack')),
    food_name       TEXT    NOT NULL,
    kcal            INTEGER NOT NULL DEFAULT 0,

    -- Extended nutrition (can be filled from dataset later)
    protein_g       REAL,
    carbs_g         REAL,
    fat_g           REAL,

    -- Optional link to Rachel's Walmart product dataset
    walmart_item_id TEXT,

    logged_at       TEXT    DEFAULT (datetime('now')),

    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- ------------------------------------------------------------
--  7. WATER LOGS  (dashboard + calendar water tracker)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS water_logs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    log_date   TEXT    NOT NULL,   -- 'YYYY-MM-DD'
    cups       INTEGER NOT NULL DEFAULT 0 CHECK(cups BETWEEN 0 AND 8),
    updated_at TEXT    DEFAULT (datetime('now')),
    UNIQUE (user_id, log_date),   -- one row per user per day; UPDATE on conflict
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- ------------------------------------------------------------
--  Indexes  (speeds up the most common queries)
-- ------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_meal_logs_user_date ON meal_logs(user_id, log_date);
CREATE INDEX IF NOT EXISTS idx_meal_logs_user_slot ON meal_logs(user_id, meal_slot);
CREATE INDEX IF NOT EXISTS idx_water_logs_user_date ON water_logs(user_id, log_date);
CREATE INDEX IF NOT EXISTS idx_restrictions_user   ON user_dietary_restrictions(user_id);
CREATE INDEX IF NOT EXISTS idx_allergies_user       ON user_allergies(user_id);

-- ============================================================
--  Useful queries (run these in Python with sqlite3 or DB Browser)
-- ============================================================

-- All meals for a user on one day:
-- SELECT * FROM meal_logs WHERE user_id=1 AND log_date='2026-10-26' ORDER BY logged_at;

-- Daily calorie totals for the past 7 days:
-- SELECT log_date, SUM(kcal) AS total_kcal
-- FROM meal_logs WHERE user_id=1 AND log_date >= date('now','-7 days')
-- GROUP BY log_date ORDER BY log_date;

-- Today's water count for a user:
-- SELECT cups FROM water_logs WHERE user_id=1 AND log_date=date('now');

-- Full profile with allergies and goals:
-- SELECT u.first_name, u.last_name, u.email,
--        p.age, p.gender, p.activity_level, p.height_cm, p.weight_kg, p.calorie_goal,
--        group_concat(DISTINCT a.allergen) AS allergies,
--        group_concat(DISTINCT g.goal)     AS goals
-- FROM users u
-- LEFT JOIN user_profiles p ON p.user_id = u.user_id
-- LEFT JOIN user_allergies a ON a.user_id = u.user_id
-- LEFT JOIN user_goals g ON g.user_id = u.user_id
-- WHERE u.user_id = 1
-- GROUP BY u.user_id;

-- Top 5 most-logged breakfast items for a user (smart suggestions):
-- SELECT food_name, COUNT(*) AS freq
-- FROM meal_logs WHERE user_id=1 AND meal_slot='Breakfast'
-- GROUP BY lower(food_name) ORDER BY freq DESC LIMIT 5;