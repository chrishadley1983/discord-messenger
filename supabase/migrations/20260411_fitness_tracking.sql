-- Migration: Fitness Tracking System
-- Supports 13-week post-Japan fat-loss programme:
--   * Programme header (start, target, TDEE, calorie/protein/steps targets)
--   * Exercise library (bodyweight movements with progression notes)
--   * Workout sessions + per-exercise sets (reps, holds, RPE)
--   * Mobility sessions (morning/evening slots)
--   * Weekly check-ins (trend weight, adherence snapshot)
--
-- Reuses existing tables (weight_readings, garmin_daily_summary, nutrition_logs)
-- for calorie/protein/step/weight auto-sourcing via the accountability tracker.

-- ============================================================
-- PROGRAMMES
-- ============================================================
CREATE TABLE IF NOT EXISTS fitness_programmes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL DEFAULT 'chris',

    name TEXT NOT NULL,
    split TEXT NOT NULL DEFAULT '5x_short',   -- e.g. '3x_ppl', '5x_short'
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,                   -- start_date + duration_weeks * 7

    duration_weeks INT NOT NULL DEFAULT 13,

    -- Weight targets
    start_weight_kg NUMERIC(5,2) NOT NULL,
    target_weight_kg NUMERIC(5,2) NOT NULL,

    -- Diet targets
    tdee_kcal INT NOT NULL,                    -- Mifflin-St Jeor * activity factor
    daily_calorie_target INT NOT NULL,         -- tdee - deficit
    daily_protein_g INT NOT NULL,              -- ~1.8g / kg bw
    daily_steps_target INT NOT NULL DEFAULT 12000,
    weekly_strength_sessions INT NOT NULL DEFAULT 5,

    -- State
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'paused', 'completed', 'abandoned')),
    notes TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_fitness_programmes_active
ON fitness_programmes(user_id, status) WHERE status = 'active';

-- ============================================================
-- EXERCISE LIBRARY
-- ============================================================
CREATE TABLE IF NOT EXISTS fitness_exercises (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    name TEXT NOT NULL UNIQUE,
    slug TEXT NOT NULL UNIQUE,                 -- e.g. "push-up", "wall-sit"
    category TEXT NOT NULL,                    -- push / pull / legs / core / mobility / conditioning
    muscle_group TEXT,                         -- chest, quads, hamstrings, back, etc.

    measurement TEXT NOT NULL DEFAULT 'reps'
        CHECK (measurement IN ('reps', 'hold_seconds', 'distance_m')),

    default_sets INT DEFAULT 3,
    default_reps INT,                          -- null for holds
    default_hold_s INT,                        -- null for reps

    progression_note TEXT,                     -- e.g. "+2 reps/week or elevate feet"
    form_cue TEXT,                             -- one-line cue

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_fitness_exercises_category ON fitness_exercises(category);

-- ============================================================
-- WORKOUT SESSIONS (the "header" per session)
-- ============================================================
CREATE TABLE IF NOT EXISTS fitness_workout_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    programme_id UUID REFERENCES fitness_programmes(id) ON DELETE SET NULL,
    user_id TEXT NOT NULL DEFAULT 'chris',

    session_date DATE NOT NULL DEFAULT CURRENT_DATE,
    session_type TEXT NOT NULL,                -- 'push', 'legs_a', 'pull_core', 'legs_b', 'full_body'
    week_no INT,                               -- 1-13, null if ad-hoc

    duration_min INT,
    rpe INT CHECK (rpe BETWEEN 1 AND 10),      -- rate of perceived exertion
    notes TEXT,

    -- Pre/post state
    pre_weight_kg NUMERIC(5,2),
    pre_mood INT CHECK (pre_mood BETWEEN 1 AND 10),

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_workout_sessions_date
ON fitness_workout_sessions(user_id, session_date DESC);
CREATE INDEX idx_workout_sessions_programme
ON fitness_workout_sessions(programme_id, session_date DESC);

-- ============================================================
-- WORKOUT SETS (per-exercise detail)
-- ============================================================
CREATE TABLE IF NOT EXISTS fitness_workout_sets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES fitness_workout_sessions(id) ON DELETE CASCADE,
    exercise_id UUID NOT NULL REFERENCES fitness_exercises(id),

    set_no INT NOT NULL,                       -- 1, 2, 3...
    reps INT,
    hold_s INT,
    notes TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_workout_sets_session ON fitness_workout_sets(session_id);
CREATE INDEX idx_workout_sets_exercise ON fitness_workout_sets(exercise_id);

-- ============================================================
-- MOBILITY SESSIONS (morning / evening)
-- ============================================================
CREATE TABLE IF NOT EXISTS fitness_mobility_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    programme_id UUID REFERENCES fitness_programmes(id) ON DELETE SET NULL,
    user_id TEXT NOT NULL DEFAULT 'chris',

    session_date DATE NOT NULL DEFAULT CURRENT_DATE,
    slot TEXT NOT NULL CHECK (slot IN ('morning', 'evening', 'adhoc')),
    duration_min INT DEFAULT 10,
    routine TEXT,                              -- which routine done
    notes TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_mobility_one_per_slot
ON fitness_mobility_sessions(user_id, session_date, slot)
WHERE slot IN ('morning', 'evening');

-- ============================================================
-- WEEKLY CHECK-INS (Sunday snapshot)
-- ============================================================
CREATE TABLE IF NOT EXISTS fitness_weekly_checkins (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    programme_id UUID NOT NULL REFERENCES fitness_programmes(id) ON DELETE CASCADE,

    week_no INT NOT NULL,                      -- 1..13
    week_ending DATE NOT NULL,                 -- the Sunday

    -- Weight trend (7-day average, not single reading)
    trend_weight_kg NUMERIC(5,2),
    weight_change_kg NUMERIC(5,2),             -- vs last checkin
    cumulative_loss_kg NUMERIC(5,2),           -- since programme start

    -- Adherence (0-100%)
    calories_adherence_pct INT,
    protein_adherence_pct INT,
    steps_adherence_pct INT,
    strength_sessions_hit INT,                 -- 0..weekly_strength_sessions
    mobility_days_hit INT,                     -- 0..7

    -- Next week adjustment (auto-calculated if trend stalled)
    next_calorie_target INT,
    next_steps_target INT,
    adjustment_note TEXT,                      -- e.g. "stalled - dropped 100kcal"

    pt_grade TEXT,                             -- "A+", "A", "B+" etc.
    notes TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_checkins_programme_week
ON fitness_weekly_checkins(programme_id, week_no);

-- ============================================================
-- UPDATED-AT TRIGGER (reuses existing helper if present)
-- ============================================================
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'update_fitness_timestamp') THEN
        CREATE FUNCTION update_fitness_timestamp()
        RETURNS TRIGGER AS $BODY$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $BODY$ LANGUAGE plpgsql;
    END IF;
END$$;

DROP TRIGGER IF EXISTS trg_fitness_programmes_updated ON fitness_programmes;
CREATE TRIGGER trg_fitness_programmes_updated
    BEFORE UPDATE ON fitness_programmes
    FOR EACH ROW EXECUTE FUNCTION update_fitness_timestamp();

-- ============================================================
-- SEED EXERCISE LIBRARY
-- Bodyweight-only, progressive, no equipment required
-- ============================================================

INSERT INTO fitness_exercises (name, slug, category, muscle_group, measurement, default_sets, default_reps, default_hold_s, progression_note, form_cue) VALUES
-- PUSH
('Push-up', 'push-up', 'push', 'chest', 'reps', 3, 10, NULL, '+2 reps/wk, then elevate feet', 'ribs down, body plank'),
('Incline push-up', 'incline-push-up', 'push', 'chest', 'reps', 3, 12, NULL, 'lower the incline over time', 'hands on counter, lower slowly'),
('Pike push-up', 'pike-push-up', 'push', 'shoulders', 'reps', 3, 6, NULL, '+1 rep/wk, progress to wall-supported HSPU', 'hips high, elbows tuck'),
('Chair dip', 'chair-dip', 'push', 'triceps', 'reps', 3, 10, NULL, '+2 reps/wk, then feet elevated', 'shoulders down, full ROM'),
('Diamond push-up', 'diamond-push-up', 'push', 'triceps', 'reps', 3, 6, NULL, '+1 rep/wk', 'index fingers touch, elbows back'),

-- PULL (bodyweight - limited, uses inverted rows under table)
('Inverted row (under table)', 'inverted-row', 'pull', 'back', 'reps', 3, 8, NULL, '+1 rep/wk, feet elevated', 'chest to table edge, squeeze shoulder blades'),
('Superman hold', 'superman-hold', 'pull', 'lower_back', 'hold_seconds', 3, NULL, 20, '+5s/wk', 'squeeze glutes, neutral neck'),
('Reverse snow angel', 'reverse-snow-angel', 'pull', 'rear_delts', 'reps', 2, 12, NULL, '+2 reps/wk, slow tempo', 'thumbs up, arms off the floor'),
('Y-T-W raise (prone)', 'y-t-w-raise', 'pull', 'rear_delts', 'reps', 2, 8, NULL, 'hold 2s at top', '3 shapes per rep, chin tucked'),
('Prone I-hold', 'prone-i-hold', 'pull', 'upper_back', 'hold_seconds', 3, NULL, 30, '+5s/wk', 'arms straight overhead, lift chest'),

-- LEGS A (quad-focus)
('Bodyweight squat', 'bw-squat', 'legs', 'quads', 'reps', 3, 15, NULL, '+2 reps/wk, pause at bottom 2s', 'knees track toes, depth below parallel'),
('Reverse lunge', 'reverse-lunge', 'legs', 'quads', 'reps', 3, 10, NULL, '+1 rep/wk/leg, add pulse', 'step back, front knee over ankle'),
('Wall sit', 'wall-sit', 'legs', 'quads', 'hold_seconds', 3, NULL, 45, '+10s/wk', 'thighs parallel, back flat'),
('Bulgarian split squat', 'bulgarian-split-squat', 'legs', 'quads', 'reps', 3, 8, NULL, '+1 rep/wk/leg', 'rear foot on chair, front knee over ankle'),
('Step-up (onto chair)', 'step-up', 'legs', 'quads', 'reps', 3, 10, NULL, '+1 rep/wk/leg', 'drive through heel, full extension'),

-- LEGS B (posterior chain)
('Glute bridge', 'glute-bridge', 'legs', 'glutes', 'reps', 3, 15, NULL, '+2 reps/wk, progress to single-leg', 'squeeze glutes 1s at top'),
('Single-leg glute bridge', 'single-leg-glute-bridge', 'legs', 'glutes', 'reps', 3, 8, NULL, '+1 rep/wk/leg', 'hips level, drive through heel'),
('Good morning (BW)', 'bw-good-morning', 'legs', 'hamstrings', 'reps', 3, 12, NULL, '+2 reps/wk, slow down', 'hinge at hips, flat back'),
('Single-leg Romanian deadlift', 'single-leg-rdl', 'legs', 'hamstrings', 'reps', 3, 8, NULL, '+1 rep/wk/leg', 'hinge, back leg straight, flat back'),
('Calf raise', 'calf-raise', 'legs', 'calves', 'reps', 3, 20, NULL, '+5 reps/wk, progress to single-leg', 'full ROM, pause at top'),

-- CORE
('Plank', 'plank', 'core', 'abs', 'hold_seconds', 3, NULL, 45, '+10s/wk', 'straight line head to heels, hollow hold'),
('Side plank', 'side-plank', 'core', 'obliques', 'hold_seconds', 2, NULL, 30, '+5s/wk per side', 'hips stacked, body straight'),
('Dead bug', 'dead-bug', 'core', 'abs', 'reps', 3, 10, NULL, '+1 rep/wk, slow tempo', 'lower back pressed to floor'),
('Bird dog', 'bird-dog', 'core', 'spine', 'reps', 3, 10, NULL, '+1 rep/wk/side, pause 2s', 'opposite arm and leg, no hip rotation'),
('Hollow body hold', 'hollow-hold', 'core', 'abs', 'hold_seconds', 3, NULL, 20, '+5s/wk', 'lower back glued to floor'),
('Mountain climber', 'mountain-climber', 'core', 'abs', 'reps', 3, 20, NULL, '+4 reps/wk', 'hips low, quick feet'),

-- CONDITIONING
('Burpee', 'burpee', 'conditioning', 'full_body', 'reps', 3, 8, NULL, '+1 rep/wk, add push-up', 'pace yourself, land soft'),
('Jumping jack', 'jumping-jack', 'conditioning', 'full_body', 'reps', 2, 30, NULL, '+5 reps/wk', 'warm-up pace'),
('High knees', 'high-knees', 'conditioning', 'full_body', 'hold_seconds', 3, NULL, 30, '+10s/wk', 'knees to waist height'),
('Skater jump', 'skater-jump', 'conditioning', 'legs', 'reps', 3, 12, NULL, '+2 reps/wk', 'lateral hop, soft landing'),

-- MOBILITY (used in the 10-min routine)
('Cat-cow', 'cat-cow', 'mobility', 'spine', 'reps', 1, 10, NULL, 'slow tempo, full ROM', 'breathe with movement'),
('World''s greatest stretch', 'worlds-greatest-stretch', 'mobility', 'hips', 'reps', 1, 6, NULL, '3 each side', 'lunge + thoracic rotation'),
('Couch stretch', 'couch-stretch', 'mobility', 'hip_flexors', 'hold_seconds', 2, NULL, 45, '+5s/wk per side', 'rear foot up against wall, squeeze glute'),
('Pigeon pose', 'pigeon-pose', 'mobility', 'glutes', 'hold_seconds', 2, NULL, 60, 'relax deeper', 'breathe into the hip'),
('Thoracic twist', 'thoracic-twist', 'mobility', 'thoracic', 'reps', 1, 10, NULL, '5 each side', 'open arm wide, follow with eyes'),
('Child''s pose', 'childs-pose', 'mobility', 'back', 'hold_seconds', 1, NULL, 60, 'relax deeper', 'arms extended, hips to heels'),
('Neck rolls', 'neck-rolls', 'mobility', 'neck', 'reps', 1, 5, NULL, 'slow, both directions', 'no forcing')
ON CONFLICT (slug) DO NOTHING;
