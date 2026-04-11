"""Fitness tracking domain.

Supports the post-Japan 13-week fat-loss programme:
- Programme header + 12-week progression plan
- Workout session logging (bodyweight)
- Mobility session logging
- Weight trend (7-day EMA, not single readings)
- Daily calorie/protein/steps adherence
- Weekly check-ins with adjustment rules

Reuses existing tables:
- weight_readings (Withings)
- garmin_daily_summary (steps)
- nutrition_logs (calories/protein)

New tables (see migrations/20260411_fitness_tracking.sql):
- fitness_programmes
- fitness_exercises
- fitness_workout_sessions
- fitness_workout_sets
- fitness_mobility_sessions
- fitness_weekly_checkins
"""
