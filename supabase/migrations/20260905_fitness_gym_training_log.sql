-- Migration: Fitness gym training log + adaptive training plan
-- Reset Cut moved to a 3-day gym split (upper / lower / full body) on
-- pin-loaded machines + cardio (5 easy + 1 hard stairmaster / week).
--
--   1. fitness_workout_sets gains load + effort columns (weight_kg, rir,
--      failed, target_reps) so machine work can be logged.
--   2. fitness_exercises gains load_step_kg (one "plate" on the stack) and
--      a seed of gym machine / cable movements.
--   3. fitness_cardio_sessions — cardio log (modality, easy/hard, protocol
--      blocks as JSON, peak level, HR, optional Garmin activity link).
--   4. fitness_training_plans — the agreed plan as versioned DATA (split,
--      sessions, exercises + rep ranges, cardio protocol, progression rules,
--      constraints). Next-session targets are derived from logged history
--      against this plan; logging something off-plan adapts the plan.
--
-- See docs/features/reset-cut-training-log/spec.md

-- ── 1. Sets: load + effort ─────────────────────────────────────────────
ALTER TABLE fitness_workout_sets
    ADD COLUMN IF NOT EXISTS weight_kg   NUMERIC(6,2),
    ADD COLUMN IF NOT EXISTS rir         SMALLINT CHECK (rir IS NULL OR rir BETWEEN 0 AND 10),
    ADD COLUMN IF NOT EXISTS failed      BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS target_reps INT;

COMMENT ON COLUMN fitness_workout_sets.weight_kg   IS 'Load on the bar / stack for this set (kg). NULL for bodyweight.';
COMMENT ON COLUMN fitness_workout_sets.rir         IS 'Reps in reserve at the end of the set (0 = to failure). NULL = not reported.';
COMMENT ON COLUMN fitness_workout_sets.failed      IS 'True if the set stopped short of target_reps (e.g. failed rep 7 of 10).';
COMMENT ON COLUMN fitness_workout_sets.target_reps IS 'Reps prescribed for this set when it was performed.';

-- ── 2. Exercises: load step + gym seed ────────────────────────────────
ALTER TABLE fitness_exercises
    ADD COLUMN IF NOT EXISTS load_step_kg NUMERIC(5,2);

COMMENT ON COLUMN fitness_exercises.load_step_kg IS 'Smallest load increment (one plate on the stack / one dumbbell step). NULL = unknown, coach says "one plate up".';

-- Loosen the measurement check so cardio/duration exercises can be catalogued
-- (kept for completeness; cardio sessions live in fitness_cardio_sessions).
ALTER TABLE fitness_exercises DROP CONSTRAINT IF EXISTS fitness_exercises_measurement_check;
ALTER TABLE fitness_exercises
    ADD CONSTRAINT fitness_exercises_measurement_check
    CHECK (measurement IN ('reps', 'hold_seconds', 'distance_m', 'duration_s'));

INSERT INTO fitness_exercises (name, slug, category, muscle_group, measurement, default_sets, default_reps, default_hold_s, progression_note, form_cue, equipment, video_url, instructions) VALUES
-- PULL (machines / cables)
('Lat pulldown', 'lat-pulldown', 'pull', 'back', 'reps', 3, 10, NULL,
 'Double progression: 3x10 with 2 in reserve -> one plate up', 'chest up, pull elbows to hips, no lean-back swing',
 'Lat pulldown machine', 'https://www.youtube.com/results?search_query=lat+pulldown+machine+form',
 E'1. Thigh pads snug, grip just outside shoulders.\n2. Chest tall, slight lean back.\n3. Pull the bar to the upper chest by driving elbows down.\n4. Control it back up to a full stretch (2s).\n5. 3x8-12; one plate up when all sets hit 10+ with 2 in reserve.'),
('Seated row (machine)', 'seated-row', 'pull', 'back', 'reps', 3, 10, NULL,
 'Double progression: 3x10 with 2 in reserve -> one plate up', 'chest on pad, squeeze shoulder blades, no shrug',
 'Seated row machine', 'https://www.youtube.com/results?search_query=life+fitness+seated+row+machine+form',
 E'1. Chest pad set so arms are fully extended at the start.\n2. Pull handles to the ribs, elbows close.\n3. Squeeze shoulder blades for a beat.\n4. Return slowly to a full stretch.\n5. 3x8-12; one plate up when all sets hit 10+ with 2 in reserve.'),
('Assisted pull-up', 'assisted-pull-up', 'pull', 'back', 'reps', 3, 8, NULL,
 'Reduce assistance one plate at a time', 'full hang at the bottom, chin over bar',
 'Assisted pull-up machine', 'https://www.youtube.com/results?search_query=assisted+pull+up+machine+form',
 E'1. Kneel on the pad, grip just outside shoulders.\n2. Pull until chin clears the bar.\n3. Lower under control to a full hang.\n4. Less assistance = harder.\n5. 3x6-10.'),
('Rear delt fly (machine)', 'rear-delt-fly', 'pull', 'rear_delts', 'reps', 3, 12, NULL,
 'Double progression 12-15 reps', 'arms slightly bent, lead with elbows',
 'Pec/rear delt fly machine (reversed)', 'https://www.youtube.com/results?search_query=rear+delt+fly+machine+form',
 E'1. Face the pad, handles at shoulder height.\n2. Open arms back in an arc, squeezing rear delts.\n3. Pause, then return slowly.\n4. Light load, strict form.\n5. 3x12-15.'),
('Cable face pull', 'cable-face-pull', 'pull', 'rear_delts', 'reps', 3, 12, NULL,
 'Double progression 12-15 reps', 'pull to the face, elbows high, external rotate',
 'Cable machine + rope', 'https://www.youtube.com/results?search_query=cable+face+pull+form',
 E'1. Rope at face height.\n2. Pull the rope to the forehead, elbows high and wide.\n3. Finish with knuckles pointing back.\n4. Return slowly.\n5. 3x12-15.'),
('Cable curl', 'cable-curl', 'pull', 'biceps', 'reps', 3, 12, NULL,
 'Double progression 10-15 reps', 'elbows pinned, no swing',
 'Cable machine', 'https://www.youtube.com/results?search_query=cable+bicep+curl+form',
 E'1. Bar/rope on the low pulley.\n2. Curl with elbows pinned to the sides.\n3. Squeeze at the top.\n4. Lower slowly (2-3s).\n5. 3x10-15.'),
-- PUSH (machines / cables)
('Chest press (machine)', 'chest-press', 'push', 'chest', 'reps', 3, 10, NULL,
 'Double progression: 3x10 with 2 in reserve -> one plate up', 'shoulder blades back and down, handles at mid-chest',
 'Chest press machine', 'https://www.youtube.com/results?search_query=life+fitness+chest+press+machine+form',
 E'1. Seat so handles line up with mid-chest.\n2. Shoulder blades back, feet planted.\n3. Press to just short of lockout.\n4. Return slowly until hands are level with the chest.\n5. 3x8-12; one plate up when all sets hit 10+ with 2 in reserve.'),
('Shoulder press (machine)', 'shoulder-press', 'push', 'shoulders', 'reps', 3, 10, NULL,
 'Double progression: 3x10 with 2 in reserve -> one plate up', 'ribs down, press slightly forward of the ears',
 'Shoulder press machine', 'https://www.youtube.com/results?search_query=life+fitness+shoulder+press+machine+form',
 E'1. Seat so handles start at ear height.\n2. Brace, ribs down, back on the pad.\n3. Press up without locking hard.\n4. Lower under control to ear height.\n5. 3x8-12; goes last on upper days so expect it to be pre-fatigued.'),
('Pec fly (machine)', 'pec-fly', 'push', 'chest', 'reps', 3, 12, NULL,
 'Double progression 12-15 reps', 'slight elbow bend, squeeze at the middle',
 'Pec fly machine', 'https://www.youtube.com/results?search_query=pec+fly+machine+form',
 E'1. Handles at chest height, slight elbow bend.\n2. Bring the handles together in an arc.\n3. Squeeze for a beat.\n4. Open slowly to a comfortable stretch.\n5. 3x12-15.'),
('Cable triceps pushdown', 'triceps-pushdown', 'push', 'triceps', 'reps', 3, 12, NULL,
 'Double progression 10-15 reps', 'elbows pinned, full extension',
 'Cable machine', 'https://www.youtube.com/results?search_query=cable+triceps+pushdown+form',
 E'1. Bar/rope on the high pulley.\n2. Elbows pinned to the sides.\n3. Push down to full extension.\n4. Return slowly to 90 degrees.\n5. 3x10-15.'),
('Lateral raise (dumbbell)', 'lateral-raise', 'push', 'shoulders', 'reps', 3, 12, NULL,
 'Double progression 12-15 reps, tiny jumps', 'lead with elbows, stop at shoulder height',
 'Dumbbells', 'https://www.youtube.com/results?search_query=dumbbell+lateral+raise+form',
 E'1. Light dumbbells, slight lean forward.\n2. Raise to shoulder height leading with elbows.\n3. Pause briefly.\n4. Lower slowly.\n5. 3x12-15.'),
-- LEGS (machines)
('Leg press', 'leg-press', 'legs', 'quads', 'reps', 3, 10, NULL,
 'Double progression: 3x10 with 2 in reserve -> one plate up', 'feet mid-platform, lower back stays on the pad, no knee lock',
 'Leg press machine', 'https://www.youtube.com/results?search_query=leg+press+machine+form',
 E'1. Feet shoulder-width, mid-platform.\n2. Lower until knees are ~90 degrees, back flat on the pad.\n3. Drive through the whole foot.\n4. Stop short of locking the knees.\n5. 3x8-12. Hip rule: stop on sharp/pinching pain.'),
('Leg extension', 'leg-extension', 'legs', 'quads', 'reps', 3, 12, NULL,
 'Double progression 10-15 reps', 'pause at the top, lower slowly',
 'Leg extension machine', 'https://www.youtube.com/results?search_query=leg+extension+machine+form',
 E'1. Pad on the shins just above the ankles.\n2. Extend to a straight leg, squeeze quads.\n3. Pause 1s.\n4. Lower slowly (2-3s).\n5. 3x10-15.'),
('Seated leg curl', 'seated-leg-curl', 'legs', 'hamstrings', 'reps', 3, 12, NULL,
 'Double progression 10-15 reps', 'hips pinned, curl to full flexion',
 'Seated leg curl machine', 'https://www.youtube.com/results?search_query=seated+leg+curl+machine+form',
 E'1. Thigh pad locked, pad above the heels.\n2. Curl the heels under the seat.\n3. Squeeze hamstrings at the bottom.\n4. Return slowly.\n5. 3x10-15.'),
('Hip abduction (machine)', 'hip-abduction', 'legs', 'glutes', 'reps', 3, 15, NULL,
 'Double progression 12-20 reps', 'push through the knees, pause at the widest point',
 'Hip abduction machine', 'https://www.youtube.com/results?search_query=hip+abduction+machine+form',
 E'1. Pads outside the knees.\n2. Push out against the pads.\n3. Pause at the widest point.\n4. Return slowly.\n5. 3x12-20. Hip-friendly glute work.'),
('Seated calf raise (machine)', 'seated-calf-raise', 'legs', 'calves', 'reps', 3, 15, NULL,
 'Double progression 12-20 reps', 'full stretch at the bottom, pause at the top',
 'Calf raise machine', 'https://www.youtube.com/results?search_query=seated+calf+raise+machine+form',
 E'1. Balls of the feet on the platform.\n2. Lower heels for a full stretch.\n3. Rise onto the toes and pause.\n4. Lower slowly.\n5. 3x12-20.'),
('Glute kickback (cable)', 'cable-glute-kickback', 'legs', 'glutes', 'reps', 3, 12, NULL,
 'Double progression 12-15 reps', 'square hips, squeeze the glute, no lower-back arch',
 'Cable machine + ankle strap', 'https://www.youtube.com/results?search_query=cable+glute+kickback+form',
 E'1. Ankle strap on the low pulley.\n2. Hinge slightly, hold the frame.\n3. Kick back and squeeze the glute.\n4. Return under control.\n5. 3x12-15 each side.'),
-- CORE (cable)
('Cable pallof press', 'cable-pallof-press', 'core', 'obliques', 'reps', 3, 10, NULL,
 'Double progression 10-15 reps', 'resist the twist, ribs down',
 'Cable machine', 'https://www.youtube.com/results?search_query=cable+pallof+press+form',
 E'1. Handle at chest height, stand side-on.\n2. Press the handle straight out.\n3. Hold 2s resisting rotation.\n4. Return to the chest.\n5. 3x10-12 each side.')
ON CONFLICT (slug) DO NOTHING;

-- ── 3. Cardio sessions ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fitness_cardio_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL DEFAULT 'chris',
    programme_id UUID REFERENCES fitness_programmes(id) ON DELETE SET NULL,

    session_date DATE NOT NULL DEFAULT CURRENT_DATE,
    modality TEXT NOT NULL,                     -- stairmaster / treadmill / bike / rower / elliptical / walk / other
    intensity TEXT NOT NULL DEFAULT 'easy'
        CHECK (intensity IN ('easy', 'hard')),
    duration_min INT,
    protocol JSONB,                             -- ordered blocks: [{phase, seconds, level}]
    peak_level NUMERIC(4,1),                    -- machine level of the hardest block
    work_level NUMERIC(4,1),                    -- level used for the other hard blocks
    avg_hr INT,
    max_hr INT,
    calories INT,
    distance_m INT,
    rpe INT CHECK (rpe IS NULL OR rpe BETWEEN 1 AND 10),
    limiter TEXT,                               -- what stopped you: legs / breathing / hip / time
    pain_flag BOOLEAN NOT NULL DEFAULT false,   -- sharp / pinching hip pain reported
    notes TEXT,
    garmin_activity_id TEXT,                    -- link to garmin_activities (Phase 2)

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cardio_sessions_user_date
    ON fitness_cardio_sessions(user_id, session_date DESC);

-- ── 4. Training plans (versioned data) ────────────────────────────────
CREATE TABLE IF NOT EXISTS fitness_training_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL DEFAULT 'chris',
    programme_id UUID REFERENCES fitness_programmes(id) ON DELETE SET NULL,

    version INT NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'superseded')),
    name TEXT NOT NULL,
    plan JSONB NOT NULL,                        -- see domains/fitness/training_plan.py
    rationale TEXT,                             -- why this version exists
    created_by TEXT NOT NULL DEFAULT 'peter',   -- chris / peter / auto

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_training_plans_one_active
    ON fitness_training_plans(user_id) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_training_plans_user_version
    ON fitness_training_plans(user_id, version DESC);
