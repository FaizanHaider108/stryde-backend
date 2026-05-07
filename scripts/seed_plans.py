"""Seed script to populate plans and workouts into the database."""
import sys
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.lib.db import SessionLocal
from app.models import Plan, PlanWorkout

# Comprehensive 6-week marathon training plans
PLANS_DATA = [
    {
        "name": "Sub-4 Hour Marathon",
        "experience_level": "Intermediate",
        "goal_type": "marathon",
        "description": "Designed for runners aiming to break the 4-hour marathon barrier, with a strong emphasis on consistent mileage, targeted speed work, and long runs.",
        "target_distance": "42.2K",
        "duration_weeks": 6,
        "total_runs": 30,
        "workouts": [
            # WEEK 1
            {"week": 1, "day": "Monday", "type": "Easy Run", "title": "Easy Run", "distance": 5.0, "duration": 50, "pace": 10.0},
            {"week": 1, "day": "Tuesday", "type": "Intervals", "title": "Speed Work: 6x800m", "distance": 6.0, "duration": 45, "pace": 7.5},
            {"week": 1, "day": "Wednesday", "type": "Recovery Run", "title": "Recovery Jog", "distance": 3.5, "duration": 40, "pace": 11.4},
            {"week": 1, "day": "Thursday", "type": "Tempo Run", "title": "Tempo Run: 3x3km", "distance": 10.0, "duration": 90, "pace": 9.0},
            {"week": 1, "day": "Friday", "type": "Rest Day", "title": "Rest Day", "distance": 0, "duration": 0, "pace": 0},
            {"week": 1, "day": "Saturday", "type": "Easy Run", "title": "Easy Run", "distance": 5.0, "duration": 50, "pace": 10.0},
            {"week": 1, "day": "Sunday", "type": "Long Run", "title": "Long Run", "distance": 18.0, "duration": 180, "pace": 10.0},
            # WEEK 2
            {"week": 2, "day": "Monday", "type": "Easy Run", "title": "Easy Run", "distance": 5.5, "duration": 55, "pace": 10.0},
            {"week": 2, "day": "Tuesday", "type": "Intervals", "title": "Speed Work: 8x600m", "distance": 6.5, "duration": 48, "pace": 7.38},
            {"week": 2, "day": "Wednesday", "type": "Recovery Run", "title": "Recovery Jog", "distance": 4.0, "duration": 45, "pace": 11.25},
            {"week": 2, "day": "Thursday", "type": "Tempo Run", "title": "Tempo Run: 4x3km", "distance": 12.0, "duration": 105, "pace": 8.75},
            {"week": 2, "day": "Friday", "type": "Rest Day", "title": "Rest Day", "distance": 0, "duration": 0, "pace": 0},
            {"week": 2, "day": "Saturday", "type": "Easy Run", "title": "Easy Run", "distance": 5.5, "duration": 55, "pace": 10.0},
            {"week": 2, "day": "Sunday", "type": "Long Run", "title": "Long Run", "distance": 19.0, "duration": 190, "pace": 10.0},
            # WEEK 3 (Peak Week)
            {"week": 3, "day": "Monday", "type": "Easy Run", "title": "Easy Run", "distance": 6.0, "duration": 60, "pace": 10.0},
            {"week": 3, "day": "Tuesday", "type": "Intervals", "title": "Speed Work: 10x500m", "distance": 7.0, "duration": 50, "pace": 7.14},
            {"week": 3, "day": "Wednesday", "type": "Recovery Run", "title": "Recovery Jog", "distance": 4.5, "duration": 50, "pace": 11.1},
            {"week": 3, "day": "Thursday", "type": "Tempo Run", "title": "Tempo Run: 5x3km", "distance": 15.0, "duration": 130, "pace": 8.67},
            {"week": 3, "day": "Friday", "type": "Rest Day", "title": "Rest Day", "distance": 0, "duration": 0, "pace": 0},
            {"week": 3, "day": "Saturday", "type": "Easy Run", "title": "Easy Run", "distance": 6.0, "duration": 60, "pace": 10.0},
            {"week": 3, "day": "Sunday", "type": "Long Run", "title": "Long Run (Peak)", "distance": 20.0, "duration": 200, "pace": 10.0},
            # WEEK 4 (Taper Week)
            {"week": 4, "day": "Monday", "type": "Easy Run", "title": "Easy Run", "distance": 5.0, "duration": 50, "pace": 10.0},
            {"week": 4, "day": "Tuesday", "type": "Intervals", "title": "Speed Work: 6x800m", "distance": 6.0, "duration": 45, "pace": 7.5},
            {"week": 4, "day": "Wednesday", "type": "Recovery Run", "title": "Recovery Jog", "distance": 3.5, "duration": 40, "pace": 11.4},
            {"week": 4, "day": "Thursday", "type": "Tempo Run", "title": "Tempo Run: 3x3km", "distance": 10.0, "duration": 90, "pace": 9.0},
            {"week": 4, "day": "Friday", "type": "Rest Day", "title": "Rest Day", "distance": 0, "duration": 0, "pace": 0},
            {"week": 4, "day": "Saturday", "type": "Easy Run", "title": "Easy Run", "distance": 4.0, "duration": 40, "pace": 10.0},
            {"week": 4, "day": "Sunday", "type": "Long Run", "title": "Long Run (Taper)", "distance": 16.0, "duration": 160, "pace": 10.0},
            # WEEK 5 (Final Preparation)
            {"week": 5, "day": "Monday", "type": "Easy Run", "title": "Easy Run", "distance": 4.5, "duration": 45, "pace": 10.0},
            {"week": 5, "day": "Tuesday", "type": "Recovery Run", "title": "Recovery Jog", "distance": 3.0, "duration": 35, "pace": 11.67},
            {"week": 5, "day": "Wednesday", "type": "Easy Run", "title": "Easy Run", "distance": 4.0, "duration": 40, "pace": 10.0},
            {"week": 5, "day": "Thursday", "type": "Easy Run", "title": "Easy Run", "distance": 3.5, "duration": 35, "pace": 10.0},
            {"week": 5, "day": "Friday", "type": "Rest Day", "title": "Rest Day", "distance": 0, "duration": 0, "pace": 0},
            {"week": 5, "day": "Saturday", "type": "Easy Run", "title": "Easy Run", "distance": 3.0, "duration": 30, "pace": 10.0},
            {"week": 5, "day": "Sunday", "type": "Long Run", "title": "Long Run (Easy)", "distance": 12.0, "duration": 120, "pace": 10.0},
            # WEEK 6 (Race Week)
            {"week": 6, "day": "Monday", "type": "Easy Run", "title": "Easy Run", "distance": 3.0, "duration": 30, "pace": 10.0},
            {"week": 6, "day": "Tuesday", "type": "Easy Run", "title": "Easy Run", "distance": 2.5, "duration": 25, "pace": 10.0},
            {"week": 6, "day": "Wednesday", "type": "Rest Day", "title": "Rest Day", "distance": 0, "duration": 0, "pace": 0},
            {"week": 6, "day": "Thursday", "type": "Easy Run", "title": "Easy Run", "distance": 2.0, "duration": 20, "pace": 10.0},
            {"week": 6, "day": "Friday", "type": "Rest Day", "title": "Rest Day", "distance": 0, "duration": 0, "pace": 0},
            {"week": 6, "day": "Saturday", "type": "Easy Run", "title": "Easy Run", "distance": 1.5, "duration": 15, "pace": 10.0},
            {"week": 6, "day": "Sunday", "type": "Marathon", "title": "Marathon Race Day!", "distance": 42.2, "duration": 240, "pace": 5.7},
        ]
    },
    {
        "name": "10K Race Destroyer",
        "experience_level": "Intermediate",
        "goal_type": "race",
        "description": "A 6-week plan to peak for a 10K race. Combines speed work, tempo runs, and strategic long runs to maximize 10K performance.",
        "target_distance": "10K",
        "duration_weeks": 6,
        "total_runs": 24,
        "workouts": [
            # WEEK 1
            {"week": 1, "day": "Monday", "type": "Easy Run", "title": "Easy Run", "distance": 4.0, "duration": 40, "pace": 10.0},
            {"week": 1, "day": "Tuesday", "type": "Intervals", "title": "Speed Work: 8x400m", "distance": 4.5, "duration": 36, "pace": 8.0},
            {"week": 1, "day": "Wednesday", "type": "Recovery Run", "title": "Recovery Jog", "distance": 3.0, "duration": 35, "pace": 11.67},
            {"week": 1, "day": "Thursday", "type": "Tempo Run", "title": "Tempo Run: 2x2km", "distance": 5.5, "duration": 50, "pace": 9.09},
            {"week": 1, "day": "Friday", "type": "Rest Day", "title": "Rest Day", "distance": 0, "duration": 0, "pace": 0},
            {"week": 1, "day": "Saturday", "type": "Easy Run", "title": "Easy Run", "distance": 3.5, "duration": 35, "pace": 10.0},
            {"week": 1, "day": "Sunday", "type": "Long Run", "title": "Long Run", "distance": 10.0, "duration": 100, "pace": 10.0},
            # WEEK 2
            {"week": 2, "day": "Monday", "type": "Easy Run", "title": "Easy Run", "distance": 4.5, "duration": 45, "pace": 10.0},
            {"week": 2, "day": "Tuesday", "type": "Intervals", "title": "Speed Work: 6x600m", "distance": 5.0, "duration": 38, "pace": 7.6},
            {"week": 2, "day": "Wednesday", "type": "Recovery Run", "title": "Recovery Jog", "distance": 3.5, "duration": 40, "pace": 11.43},
            {"week": 2, "day": "Thursday", "type": "Tempo Run", "title": "Tempo Run: 3x2km", "distance": 7.0, "duration": 60, "pace": 8.57},
            {"week": 2, "day": "Friday", "type": "Rest Day", "title": "Rest Day", "distance": 0, "duration": 0, "pace": 0},
            {"week": 2, "day": "Saturday", "type": "Easy Run", "title": "Easy Run", "distance": 4.0, "duration": 40, "pace": 10.0},
            {"week": 2, "day": "Sunday", "type": "Long Run", "title": "Long Run", "distance": 11.0, "duration": 110, "pace": 10.0},
            # WEEK 3 (Peak)
            {"week": 3, "day": "Monday", "type": "Easy Run", "title": "Easy Run", "distance": 5.0, "duration": 50, "pace": 10.0},
            {"week": 3, "day": "Tuesday", "type": "Intervals", "title": "Speed Work: 10x300m", "distance": 5.5, "duration": 40, "pace": 7.27},
            {"week": 3, "day": "Wednesday", "type": "Recovery Run", "title": "Recovery Jog", "distance": 4.0, "duration": 45, "pace": 11.25},
            {"week": 3, "day": "Thursday", "type": "Tempo Run", "title": "Tempo Run: 4x2km", "distance": 9.0, "duration": 75, "pace": 8.33},
            {"week": 3, "day": "Friday", "type": "Rest Day", "title": "Rest Day", "distance": 0, "duration": 0, "pace": 0},
            {"week": 3, "day": "Saturday", "type": "Easy Run", "title": "Easy Run", "distance": 4.5, "duration": 45, "pace": 10.0},
            {"week": 3, "day": "Sunday", "type": "Long Run", "title": "Long Run (Peak)", "distance": 12.0, "duration": 120, "pace": 10.0},
            # WEEK 4 (Taper)
            {"week": 4, "day": "Monday", "type": "Easy Run", "title": "Easy Run", "distance": 4.0, "duration": 40, "pace": 10.0},
            {"week": 4, "day": "Tuesday", "type": "Intervals", "title": "Speed Work: 6x400m", "distance": 4.5, "duration": 36, "pace": 8.0},
            {"week": 4, "day": "Wednesday", "type": "Recovery Run", "title": "Recovery Jog", "distance": 3.0, "duration": 35, "pace": 11.67},
            {"week": 4, "day": "Thursday", "type": "Tempo Run", "title": "Tempo Run: 2x2km", "distance": 5.5, "duration": 50, "pace": 9.09},
            {"week": 4, "day": "Friday", "type": "Rest Day", "title": "Rest Day", "distance": 0, "duration": 0, "pace": 0},
            {"week": 4, "day": "Saturday", "type": "Easy Run", "title": "Easy Run", "distance": 3.0, "duration": 30, "pace": 10.0},
            {"week": 4, "day": "Sunday", "type": "Long Run", "title": "Long Run (Taper)", "distance": 8.0, "duration": 80, "pace": 10.0},
            # WEEK 5
            {"week": 5, "day": "Monday", "type": "Easy Run", "title": "Easy Run", "distance": 3.5, "duration": 35, "pace": 10.0},
            {"week": 5, "day": "Tuesday", "type": "Easy Run", "title": "Easy Run", "distance": 3.0, "duration": 30, "pace": 10.0},
            {"week": 5, "day": "Wednesday", "type": "Recovery Run", "title": "Recovery Jog", "distance": 2.5, "duration": 30, "pace": 12.0},
            {"week": 5, "day": "Thursday", "type": "Easy Run", "title": "Easy Run", "distance": 2.5, "duration": 25, "pace": 10.0},
            {"week": 5, "day": "Friday", "type": "Rest Day", "title": "Rest Day", "distance": 0, "duration": 0, "pace": 0},
            {"week": 5, "day": "Saturday", "type": "Easy Run", "title": "Easy Run", "distance": 2.0, "duration": 20, "pace": 10.0},
            {"week": 5, "day": "Sunday", "type": "Long Run", "title": "Long Run (Final)", "distance": 6.0, "duration": 60, "pace": 10.0},
            # WEEK 6 (Race Week)
            {"week": 6, "day": "Monday", "type": "Easy Run", "title": "Easy Run", "distance": 2.5, "duration": 25, "pace": 10.0},
            {"week": 6, "day": "Tuesday", "type": "Easy Run", "title": "Easy Run", "distance": 2.0, "duration": 20, "pace": 10.0},
            {"week": 6, "day": "Wednesday", "type": "Rest Day", "title": "Rest Day", "distance": 0, "duration": 0, "pace": 0},
            {"week": 6, "day": "Thursday", "type": "Easy Run", "title": "Easy Run", "distance": 1.5, "duration": 15, "pace": 10.0},
            {"week": 6, "day": "Friday", "type": "Rest Day", "title": "Rest Day", "distance": 0, "duration": 0, "pace": 0},
            {"week": 6, "day": "Saturday", "type": "Easy Run", "title": "Easy Run", "distance": 1.0, "duration": 10, "pace": 10.0},
            {"week": 6, "day": "Sunday", "type": "10K Race", "title": "10K Race Day!", "distance": 10.0, "duration": 60, "pace": 6.0},
        ]
    },
    {
        "name": "Half Marathon Ready",
        "experience_level": "Beginner",
        "goal_type": "marathon",
        "description": "Build up to a half marathon in 6 weeks. Progressive mileage increase with emphasis on the long run.",
        "target_distance": "21.1K",
        "duration_weeks": 6,
        "total_runs": 24,
        "workouts": [
            # WEEK 1
            {"week": 1, "day": "Monday", "type": "Easy Run", "title": "Easy Run", "distance": 3.0, "duration": 32, "pace": 10.67},
            {"week": 1, "day": "Tuesday", "type": "Recovery Run", "title": "Recovery Jog", "distance": 2.5, "duration": 30, "pace": 12.0},
            {"week": 1, "day": "Wednesday", "type": "Easy Run", "title": "Easy Run", "distance": 3.5, "duration": 37, "pace": 10.57},
            {"week": 1, "day": "Thursday", "type": "Rest Day", "title": "Rest Day", "distance": 0, "duration": 0, "pace": 0},
            {"week": 1, "day": "Friday", "type": "Easy Run", "title": "Easy Run", "distance": 3.0, "duration": 32, "pace": 10.67},
            {"week": 1, "day": "Saturday", "type": "Rest Day", "title": "Rest Day", "distance": 0, "duration": 0, "pace": 0},
            {"week": 1, "day": "Sunday", "type": "Long Run", "title": "Long Run", "distance": 8.0, "duration": 85, "pace": 10.625},
            # WEEK 2
            {"week": 2, "day": "Monday", "type": "Easy Run", "title": "Easy Run", "distance": 3.5, "duration": 37, "pace": 10.57},
            {"week": 2, "day": "Tuesday", "type": "Easy Run", "title": "Easy Run", "distance": 3.0, "duration": 32, "pace": 10.67},
            {"week": 2, "day": "Wednesday", "type": "Easy Run", "title": "Easy Run", "distance": 4.0, "duration": 42, "pace": 10.5},
            {"week": 2, "day": "Thursday", "type": "Rest Day", "title": "Rest Day", "distance": 0, "duration": 0, "pace": 0},
            {"week": 2, "day": "Friday", "type": "Easy Run", "title": "Easy Run", "distance": 3.5, "duration": 37, "pace": 10.57},
            {"week": 2, "day": "Saturday", "type": "Rest Day", "title": "Rest Day", "distance": 0, "duration": 0, "pace": 0},
            {"week": 2, "day": "Sunday", "type": "Long Run", "title": "Long Run", "distance": 9.5, "duration": 100, "pace": 10.53},
            # WEEK 3 (Peak)
            {"week": 3, "day": "Monday", "type": "Easy Run", "title": "Easy Run", "distance": 4.0, "duration": 42, "pace": 10.5},
            {"week": 3, "day": "Tuesday", "type": "Easy Run", "title": "Easy Run", "distance": 3.5, "duration": 37, "pace": 10.57},
            {"week": 3, "day": "Wednesday", "type": "Tempo Run", "title": "Tempo Run: 2x2km", "distance": 5.5, "duration": 50, "pace": 9.09},
            {"week": 3, "day": "Thursday", "type": "Rest Day", "title": "Rest Day", "distance": 0, "duration": 0, "pace": 0},
            {"week": 3, "day": "Friday", "type": "Easy Run", "title": "Easy Run", "distance": 4.0, "duration": 42, "pace": 10.5},
            {"week": 3, "day": "Saturday", "type": "Rest Day", "title": "Rest Day", "distance": 0, "duration": 0, "pace": 0},
            {"week": 3, "day": "Sunday", "type": "Long Run", "title": "Long Run (Peak)", "distance": 11.0, "duration": 116, "pace": 10.55},
            # WEEK 4 (Taper)
            {"week": 4, "day": "Monday", "type": "Easy Run", "title": "Easy Run", "distance": 3.5, "duration": 37, "pace": 10.57},
            {"week": 4, "day": "Tuesday", "type": "Easy Run", "title": "Easy Run", "distance": 3.0, "duration": 32, "pace": 10.67},
            {"week": 4, "day": "Wednesday", "type": "Easy Run", "title": "Easy Run", "distance": 3.5, "duration": 37, "pace": 10.57},
            {"week": 4, "day": "Thursday", "type": "Rest Day", "title": "Rest Day", "distance": 0, "duration": 0, "pace": 0},
            {"week": 4, "day": "Friday", "type": "Easy Run", "title": "Easy Run", "distance": 3.0, "duration": 32, "pace": 10.67},
            {"week": 4, "day": "Saturday", "type": "Rest Day", "title": "Rest Day", "distance": 0, "duration": 0, "pace": 0},
            {"week": 4, "day": "Sunday", "type": "Long Run", "title": "Long Run (Taper)", "distance": 9.0, "duration": 95, "pace": 10.56},
            # WEEK 5
            {"week": 5, "day": "Monday", "type": "Easy Run", "title": "Easy Run", "distance": 3.0, "duration": 32, "pace": 10.67},
            {"week": 5, "day": "Tuesday", "type": "Easy Run", "title": "Easy Run", "distance": 2.5, "duration": 27, "pace": 10.8},
            {"week": 5, "day": "Wednesday", "type": "Easy Run", "title": "Easy Run", "distance": 3.0, "duration": 32, "pace": 10.67},
            {"week": 5, "day": "Thursday", "type": "Rest Day", "title": "Rest Day", "distance": 0, "duration": 0, "pace": 0},
            {"week": 5, "day": "Friday", "type": "Easy Run", "title": "Easy Run", "distance": 2.5, "duration": 27, "pace": 10.8},
            {"week": 5, "day": "Saturday", "type": "Rest Day", "title": "Rest Day", "distance": 0, "duration": 0, "pace": 0},
            {"week": 5, "day": "Sunday", "type": "Long Run", "title": "Long Run (Final)", "distance": 7.0, "duration": 74, "pace": 10.57},
            # WEEK 6 (Race Week)
            {"week": 6, "day": "Monday", "type": "Easy Run", "title": "Easy Run", "distance": 2.0, "duration": 21, "pace": 10.5},
            {"week": 6, "day": "Tuesday", "type": "Easy Run", "title": "Easy Run", "distance": 1.5, "duration": 16, "pace": 10.67},
            {"week": 6, "day": "Wednesday", "type": "Rest Day", "title": "Rest Day", "distance": 0, "duration": 0, "pace": 0},
            {"week": 6, "day": "Thursday", "type": "Easy Run", "title": "Easy Run", "distance": 1.5, "duration": 16, "pace": 10.67},
            {"week": 6, "day": "Friday", "type": "Rest Day", "title": "Rest Day", "distance": 0, "duration": 0, "pace": 0},
            {"week": 6, "day": "Saturday", "type": "Easy Run", "title": "Easy Run", "distance": 1.0, "duration": 11, "pace": 11.0},
            {"week": 6, "day": "Sunday", "type": "Half Marathon", "title": "Half Marathon Race Day!", "distance": 21.1, "duration": 130, "pace": 6.17},
        ]
    },
    {
        "name": "Aerobic Stamina Builder",
        "experience_level": "Intermediate",
        "goal_type": "race",
        "description": "Build aerobic base and stamina with emphasis on Zone 2 training and consistent effort. Perfect for general fitness.",
        "target_distance": "50K",
        "duration_weeks": 6,
        "total_runs": 24,
        "workouts": [
            # WEEK 1
            {"week": 1, "day": "Monday", "type": "Zone 2 Run", "title": "Zone 2 Easy", "distance": 5.0, "duration": 52, "pace": 10.4},
            {"week": 1, "day": "Tuesday", "type": "Easy Run", "title": "Easy Run", "distance": 4.0, "duration": 40, "pace": 10.0},
            {"week": 1, "day": "Wednesday", "type": "Zone 2 Run", "title": "Zone 2 Easy", "distance": 4.5, "duration": 47, "pace": 10.44},
            {"week": 1, "day": "Thursday", "type": "Rest Day", "title": "Rest Day", "distance": 0, "duration": 0, "pace": 0},
            {"week": 1, "day": "Friday", "type": "Easy Run", "title": "Easy Run", "distance": 4.0, "duration": 40, "pace": 10.0},
            {"week": 1, "day": "Saturday", "type": "Rest Day", "title": "Rest Day", "distance": 0, "duration": 0, "pace": 0},
            {"week": 1, "day": "Sunday", "type": "Zone 2 Long Run", "title": "Zone 2 Long", "distance": 10.0, "duration": 104, "pace": 10.4},
            # WEEK 2
            {"week": 2, "day": "Monday", "type": "Zone 2 Run", "title": "Zone 2 Easy", "distance": 5.5, "duration": 57, "pace": 10.36},
            {"week": 2, "day": "Tuesday", "type": "Easy Run", "title": "Easy Run", "distance": 4.5, "duration": 45, "pace": 10.0},
            {"week": 2, "day": "Wednesday", "type": "Zone 2 Run", "title": "Zone 2 Easy", "distance": 5.0, "duration": 52, "pace": 10.4},
            {"week": 2, "day": "Thursday", "type": "Rest Day", "title": "Rest Day", "distance": 0, "duration": 0, "pace": 0},
            {"week": 2, "day": "Friday", "type": "Easy Run", "title": "Easy Run", "distance": 4.5, "duration": 45, "pace": 10.0},
            {"week": 2, "day": "Saturday", "type": "Rest Day", "title": "Rest Day", "distance": 0, "duration": 0, "pace": 0},
            {"week": 2, "day": "Sunday", "type": "Zone 2 Long Run", "title": "Zone 2 Long", "distance": 11.0, "duration": 114, "pace": 10.36},
            # WEEK 3 (Peak)
            {"week": 3, "day": "Monday", "type": "Zone 2 Run", "title": "Zone 2 Easy", "distance": 6.0, "duration": 62, "pace": 10.33},
            {"week": 3, "day": "Tuesday", "type": "Easy Run", "title": "Easy Run", "distance": 5.0, "duration": 50, "pace": 10.0},
            {"week": 3, "day": "Wednesday", "type": "Zone 2 Run", "title": "Zone 2 Easy", "distance": 5.5, "duration": 57, "pace": 10.36},
            {"week": 3, "day": "Thursday", "type": "Rest Day", "title": "Rest Day", "distance": 0, "duration": 0, "pace": 0},
            {"week": 3, "day": "Friday", "type": "Easy Run", "title": "Easy Run", "distance": 5.0, "duration": 50, "pace": 10.0},
            {"week": 3, "day": "Saturday", "type": "Rest Day", "title": "Rest Day", "distance": 0, "duration": 0, "pace": 0},
            {"week": 3, "day": "Sunday", "type": "Zone 2 Long Run", "title": "Zone 2 Long (Peak)", "distance": 13.0, "duration": 135, "pace": 10.38},
            # WEEK 4 (Taper)
            {"week": 4, "day": "Monday", "type": "Zone 2 Run", "title": "Zone 2 Easy", "distance": 5.0, "duration": 52, "pace": 10.4},
            {"week": 4, "day": "Tuesday", "type": "Easy Run", "title": "Easy Run", "distance": 4.0, "duration": 40, "pace": 10.0},
            {"week": 4, "day": "Wednesday", "type": "Zone 2 Run", "title": "Zone 2 Easy", "distance": 4.5, "duration": 47, "pace": 10.44},
            {"week": 4, "day": "Thursday", "type": "Rest Day", "title": "Rest Day", "distance": 0, "duration": 0, "pace": 0},
            {"week": 4, "day": "Friday", "type": "Easy Run", "title": "Easy Run", "distance": 4.0, "duration": 40, "pace": 10.0},
            {"week": 4, "day": "Saturday", "type": "Rest Day", "title": "Rest Day", "distance": 0, "duration": 0, "pace": 0},
            {"week": 4, "day": "Sunday", "type": "Zone 2 Long Run", "title": "Zone 2 Long (Taper)", "distance": 10.0, "duration": 104, "pace": 10.4},
            # WEEK 5
            {"week": 5, "day": "Monday", "type": "Zone 2 Run", "title": "Zone 2 Easy", "distance": 4.5, "duration": 47, "pace": 10.44},
            {"week": 5, "day": "Tuesday", "type": "Easy Run", "title": "Easy Run", "distance": 3.5, "duration": 35, "pace": 10.0},
            {"week": 5, "day": "Wednesday", "type": "Zone 2 Run", "title": "Zone 2 Easy", "distance": 4.0, "duration": 42, "pace": 10.5},
            {"week": 5, "day": "Thursday", "type": "Rest Day", "title": "Rest Day", "distance": 0, "duration": 0, "pace": 0},
            {"week": 5, "day": "Friday", "type": "Easy Run", "title": "Easy Run", "distance": 3.5, "duration": 35, "pace": 10.0},
            {"week": 5, "day": "Saturday", "type": "Rest Day", "title": "Rest Day", "distance": 0, "duration": 0, "pace": 0},
            {"week": 5, "day": "Sunday", "type": "Zone 2 Long Run", "title": "Zone 2 Long (Final)", "distance": 9.0, "duration": 94, "pace": 10.44},
            # WEEK 6
            {"week": 6, "day": "Monday", "type": "Zone 2 Run", "title": "Zone 2 Easy", "distance": 4.0, "duration": 42, "pace": 10.5},
            {"week": 6, "day": "Tuesday", "type": "Easy Run", "title": "Easy Run", "distance": 3.0, "duration": 30, "pace": 10.0},
            {"week": 6, "day": "Wednesday", "type": "Zone 2 Run", "title": "Zone 2 Easy", "distance": 3.5, "duration": 37, "pace": 10.57},
            {"week": 6, "day": "Thursday", "type": "Rest Day", "title": "Rest Day", "distance": 0, "duration": 0, "pace": 0},
            {"week": 6, "day": "Friday", "type": "Easy Run", "title": "Easy Run", "distance": 3.0, "duration": 30, "pace": 10.0},
            {"week": 6, "day": "Saturday", "type": "Rest Day", "title": "Rest Day", "distance": 0, "duration": 0, "pace": 0},
            {"week": 6, "day": "Sunday", "type": "Zone 2 Long Run", "title": "Zone 2 Long (Recovery)", "distance": 7.0, "duration": 73, "pace": 10.43},
        ]
    },
]


def seed_plans():
    """Seed all plans and workouts into the database."""
    db = SessionLocal()
    
    try:
        # Check if plans already exist
        existing_count = db.query(Plan).count()
        if existing_count > 0:
            print(f"ℹ️  Database already has {existing_count} plans. Clearing and reseeding...")
            # Delete all existing plans and workouts
            db.query(PlanWorkout).delete()
            db.query(Plan).delete()
            db.commit()
        
        for plan_data in PLANS_DATA:
            print(f"🌱 Seeding plan: {plan_data['name']}")
            
            # Extract workouts
            workouts_data = plan_data.pop("workouts")
            
            # Create plan
            plan = Plan(**plan_data)
            db.add(plan)
            db.flush()  # Get the ID
            
            # Create workouts
            for workout_data in workouts_data:
                week = workout_data.pop("week")
                day = workout_data.pop("day")
                workout_type = workout_data.pop("type")
                title = workout_data.pop("title")
                distance = workout_data.pop("distance")
                duration = workout_data.pop("duration")
                pace = workout_data.pop("pace")
                
                # Calculate pace in km/h from min/km
                pace_kmh = 60.0 / pace if pace > 0 else 0
                
                workout = PlanWorkout(
                    plan_id=plan.id,
                    week_number=week,
                    day_name=day,
                    workout_type=workout_type,
                    title=title,
                    description=f"{title} - {distance}km in {duration} minutes",
                    target_distance_km=distance,
                    target_duration_seconds=duration * 60,
                    target_pace_kmh=pace_kmh,
                )
                db.add(workout)
        
        db.commit()
        print("✅ Plans seeded successfully!")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error seeding plans: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_plans()
