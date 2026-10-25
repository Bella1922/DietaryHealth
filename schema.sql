CREATE DATABASE IF NOT EXISTS dietaryhealth
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE dietaryhealth;

-- ------------------------------------------------------------
--  1. USERS
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    user_id       INT          PRIMARY KEY AUTO_INCREMENT,
    username      VARCHAR(50)  NOT NULL UNIQUE,
    email         VARCHAR(255) NOT NULL UNIQUE,
    first_name    VARCHAR(100) NOT NULL,
    last_name     VARCHAR(100) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,   -- store bcrypt hash, NEVER plaintext
    created_at    DATETIME     DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------------------------------------------
--  2. USER PROFILES  (onboarding questionnaire Part 1)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_profiles (
    profile_id      INT  PRIMARY KEY AUTO_INCREMENT,
    user_id         INT  NOT NULL UNIQUE,

    age             INT,
    gender          ENUM('male','female','other'),
    activity_level  ENUM('mostly_sitting','lightly_active','moderately_active',
                         'very_active','athlete'),

    height_cm       FLOAT,    -- always stored in cm; frontend converts ft/in
    weight_kg       FLOAT,    -- always stored in kg; frontend converts lbs

    calorie_goal    INT      DEFAULT 1800,
    notes           TEXT,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- ------------------------------------------------------------
--  3. DIETARY RESTRICTIONS  (questionnaire step 1 chips)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_dietary_restrictions (
    id          INT          PRIMARY KEY AUTO_INCREMENT,
    user_id     INT          NOT NULL,
    restriction VARCHAR(100) NOT NULL,
    UNIQUE KEY uq_user_restriction (user_id, restriction),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- ------------------------------------------------------------
--  4. ALLERGIES  (questionnaire step 2 chips — singular names)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_allergies (
    id        INT          PRIMARY KEY AUTO_INCREMENT,
    user_id   INT          NOT NULL,
    allergen  VARCHAR(100) NOT NULL,   -- e.g. 'peanut', 'dairy', 'wheat'
    UNIQUE KEY uq_user_allergen (user_id, allergen),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- ------------------------------------------------------------
--  5. GOALS  (questionnaire Part 2 chips)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_goals (
    id          INT          PRIMARY KEY AUTO_INCREMENT,
    user_id     INT          NOT NULL,
    goal        VARCHAR(100) NOT NULL,
    custom_text TEXT,                  -- filled when goal = 'other'
    UNIQUE KEY uq_user_goal (user_id, goal),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- ------------------------------------------------------------
--  6. MEAL LOGS  (calendar.html entries)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS meal_logs (
    log_id          INT          PRIMARY KEY AUTO_INCREMENT,
    user_id         INT          NOT NULL,

    log_date        DATE         NOT NULL,
    meal_slot       ENUM('Breakfast','Lunch','Dinner','Snack') NOT NULL,
    food_name       VARCHAR(255) NOT NULL,
    kcal            INT          NOT NULL DEFAULT 0,

    -- Extended nutrition (fill in later from Walmart dataset)
    protein_g       FLOAT,
    carbs_g         FLOAT,
    fat_g           FLOAT,

    -- Optional link to Rachel's Walmart product dataset
    walmart_item_id VARCHAR(100),

    logged_at       DATETIME     DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- ------------------------------------------------------------
--  Indexes
-- ------------------------------------------------------------
CREATE INDEX idx_meal_logs_user_date    ON meal_logs(user_id, log_date);
CREATE INDEX idx_meal_logs_user_slot    ON meal_logs(user_id, meal_slot);
CREATE INDEX idx_allergies_user         ON user_allergies(user_id);
CREATE INDEX idx_restrictions_user      ON user_dietary_restrictions(user_id);

-- ============================================================
--  Example queries
-- ============================================================

-- All meals for a user on one day:
-- SELECT * FROM meal_logs WHERE user_id = 1 AND log_date = '2026-10-23' ORDER BY logged_at;

-- Daily calorie totals for the past 7 days:
-- SELECT log_date, SUM(kcal) AS total_kcal
-- FROM meal_logs WHERE user_id = 1 AND log_date >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
-- GROUP BY log_date ORDER BY log_date;

-- Top 5 most-logged breakfast items (for smart suggestions):
-- SELECT food_name, COUNT(*) AS freq
-- FROM meal_logs WHERE user_id = 1 AND meal_slot = 'Breakfast'
-- GROUP BY LOWER(food_name) ORDER BY freq DESC LIMIT 5;

-- Full user profile with allergies and goals:
-- SELECT u.first_name, u.last_name, u.email,
--        p.age, p.gender, p.activity_level, p.height_cm, p.weight_kg, p.calorie_goal,
--        GROUP_CONCAT(DISTINCT a.allergen ORDER BY a.allergen SEPARATOR ', ') AS allergies,
--        GROUP_CONCAT(DISTINCT g.goal     ORDER BY g.goal     SEPARATOR ', ') AS goals
-- FROM users u
-- LEFT JOIN user_profiles p              ON p.user_id = u.user_id
-- LEFT JOIN user_allergies a             ON a.user_id = u.user_id
-- LEFT JOIN user_goals g                 ON g.user_id = u.user_id
-- WHERE u.user_id = 1
-- GROUP BY u.user_id;