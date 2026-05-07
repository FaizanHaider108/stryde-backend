"""Mock GLM client for development and testing without real API credentials."""

import logging
import re
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

WEEKDAY_ORDER = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]


def _extract(pattern: str, text: str, default: str = "") -> str:
    m = re.search(pattern, text, re.IGNORECASE)
    return m.group(1).strip() if m else default


def generate_plan_json_mock(prompt: str) -> dict[str, Any]:
    """
    Generate a realistic mock training plan that intelligently uses every
    user input extracted from the prompt.
    """
    logger.info("Using mock GLM client (development mode)")

    # ── Extract all user inputs from the prompt ──────────────────────────
    goal_type_raw  = _extract(r"- Goal type:\s*(.+)", prompt, "race")
    ultimate_goal  = _extract(r"- Ultimate goal:\s*(.+)", prompt, "")
    experience_raw = _extract(r"- Experience level:\s*(.+)", prompt, "Intermediate")
    pace_str       = _extract(r"- Target pace \(min/mile\):\s*(.+)", prompt, "")
    start_date_str = _extract(r"- Start date:\s*(\S+)", prompt, "")
    race_day_str   = _extract(r"- Race day:\s*(\S+)", prompt, "")
    off_days_str   = _extract(r"- Off days:\s*(.+)", prompt, "None")
    long_run_raw   = _extract(r"- Preferred long run day:\s*(.+)", prompt, "Saturday")
    duration_hint  = _extract(r"- Training duration:\s*(\d+)", prompt, "")

    # ── Calculate exact number of training weeks from date range ─────────
    weeks = int(duration_hint) if duration_hint.isdigit() else 12
    try:
        if start_date_str and race_day_str:
            start = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            race  = datetime.strptime(race_day_str,  "%Y-%m-%d").date()
            weeks = max(4, min((race - start).days // 7, 24))
    except Exception:
        pass

    # ── Parse off_days ───────────────────────────────────────────────────
    off_days: list[str] = []
    if off_days_str.strip().lower() not in ("none", "not specified", ""):
        for part in off_days_str.split(","):
            token = part.strip().upper()
            for d in WEEKDAY_ORDER:
                if d.startswith(token[:3]) or token.startswith(d[:3]):
                    if d not in off_days:
                        off_days.append(d)
                    break

    # ── Resolve preferred long run day ───────────────────────────────────
    long_run_day = "SATURDAY"
    for d in WEEKDAY_ORDER:
        if d.upper().startswith(long_run_raw.strip().upper()[:3]):
            long_run_day = d
            break
    if long_run_day in off_days:          # Shift if it's also an off day
        for d in WEEKDAY_ORDER:
            if d not in off_days:
                long_run_day = d
                break

    # ── Goal metadata ────────────────────────────────────────────────────
    gl = goal_type_raw.lower()
    if "ultra" in gl:
        goal_name, target_distance_label, race_km = "Ultra Marathon", "50+ km (Ultra)", 50.0
    elif "full marathon" in gl or ("marathon" in gl and "half" not in gl):
        goal_name, target_distance_label, race_km = "Marathon", "42.2 km (Full Marathon)", 42.2
    elif "half" in gl:
        goal_name, target_distance_label, race_km = "Half Marathon", "21.1 km (Half Marathon)", 21.1
    elif "10" in gl:
        goal_name, target_distance_label, race_km = "10K", "10 km", 10.0
    elif "5" in gl:
        goal_name, target_distance_label, race_km = "5K", "5 km", 5.0
    else:
        goal_name, target_distance_label, race_km = "Race", "Race Distance", 21.1

    # ── Experience adjustments ───────────────────────────────────────────
    exp = experience_raw.lower()
    if "beginner" in exp or "novice" in exp:
        exp_label, base_easy_km, base_long_km = "Beginner", 3.0, 5.0
    elif "advanced" in exp or "pro" in exp or "elite" in exp:
        exp_label, base_easy_km, base_long_km = "Advanced", 8.0, 14.0
    else:
        exp_label, base_easy_km, base_long_km = "Intermediate", 5.0, 8.0

    # ── Convert target pace (min/mile → km/h) ───────────────────────────
    target_pace_kmh: float | None = None
    if pace_str and pace_str.lower() not in ("not specified", "none", ""):
        try:
            pace_min_per_mile = float(pace_str)
            target_pace_kmh = round(60.0 / (pace_min_per_mile * 1.60934), 1)
        except Exception:
            pass

    easy_pace     = round((target_pace_kmh * 0.75) if target_pace_kmh else 9.5,  1)
    tempo_pace    = round((target_pace_kmh * 0.90) if target_pace_kmh else 11.5, 1)
    long_pace     = round((target_pace_kmh * 0.80) if target_pace_kmh else 10.0, 1)
    interval_pace = round((target_pace_kmh * 1.05) if target_pace_kmh else 13.0, 1)

    # ── Pick regular run days (spread across week, excluding off & long) ─
    candidates   = [d for d in WEEKDAY_ORDER if d not in off_days and d != long_run_day]
    if len(candidates) >= 3:
        run_days = [candidates[0], candidates[len(candidates) // 2], candidates[-1]]
    elif candidates:
        run_days = candidates[:3]
    else:
        run_days = []

    taper_start = max(weeks - 2, 1)
    total_run_count = 0
    workouts: list[dict] = []

    for week in range(1, weeks + 1):
        is_taper    = week >= taper_start
        progression = week / weeks          # 0 → 1 linear progression

        # ── Long run distance (progressive then taper) ───────────────────
        if is_taper:
            long_run_km = round(race_km * 0.55, 1)
        else:
            peak_long   = race_km * 0.90
            long_run_km = round(base_long_km + (peak_long - base_long_km) * progression, 1)

        easy_km = round(
            (base_easy_km + progression * 3.0) if not is_taper else base_easy_km * 0.65, 1
        )

        # ── Regular run days ─────────────────────────────────────────────
        for idx, day in enumerate(run_days):
            total_run_count += 1

            if idx == 0:                          # First day: easy run
                workouts.append({
                    "week_number": week,
                    "day_name": day,
                    "workout_type": "easy",
                    "title": "Easy Run",
                    "description": (
                        f"Conversational pace. Focus on form and relaxed breathing. "
                        f"Target {easy_km:.1f} km."
                    ),
                    "target_distance_km": easy_km,
                    "target_duration_seconds": None,
                    "target_pace_kmh": easy_pace,
                    "variable_pace_data": None,
                })

            elif idx == 1:                        # Mid-week: quality session
                if week % 2 == 0:                 # Even weeks → tempo
                    tempo_km = round(easy_km * 1.4, 1)
                    workouts.append({
                        "week_number": week,
                        "day_name": day,
                        "workout_type": "tempo",
                        "title": "Tempo Run",
                        "description": (
                            f"5 min warm-up, {max(1, int(tempo_km - 2))} km at tempo pace, "
                            f"5 min cool-down. Comfortably hard effort."
                        ),
                        "target_distance_km": tempo_km,
                        "target_duration_seconds": None,
                        "target_pace_kmh": tempo_pace,
                        "variable_pace_data": None,
                    })
                else:                             # Odd weeks → intervals
                    workouts.append({
                        "week_number": week,
                        "day_name": day,
                        "workout_type": "intervals",
                        "title": "Speed Intervals",
                        "description": (
                            "6 × 800 m at race pace with 90 sec recovery jog. "
                            "Warm up 5 min, cool down 5 min."
                        ),
                        "target_distance_km": 7.0,
                        "target_duration_seconds": None,
                        "target_pace_kmh": interval_pace,
                        "variable_pace_data": {
                            "segments": [
                                {"duration_sec": 240, "pace_kmh": interval_pace},
                                {"duration_sec": 90,  "pace_kmh": easy_pace},
                            ]
                        },
                    })

            else:                                 # Third day: recovery
                rec_km = round(easy_km * 0.75, 1)
                workouts.append({
                    "week_number": week,
                    "day_name": day,
                    "workout_type": "recovery",
                    "title": "Recovery Run",
                    "description": "Very easy pace to flush fatigue from mid-week sessions.",
                    "target_distance_km": rec_km,
                    "target_duration_seconds": None,
                    "target_pace_kmh": round(easy_pace * 0.88, 1),
                    "variable_pace_data": None,
                })

        # ── Long run ─────────────────────────────────────────────────────
        total_run_count += 1
        long_desc = (
            f"Taper long run — {long_run_km} km easy to rest legs before race day."
            if is_taper
            else (
                f"Build endurance at easy, conversational pace. "
                f"Target {long_run_km} km. Walk breaks are fine."
            )
        )
        workouts.append({
            "week_number": week,
            "day_name": long_run_day,
            "workout_type": "long_run",
            "title": "Long Run",
            "description": long_desc,
            "target_distance_km": long_run_km,
            "target_duration_seconds": None,
            "target_pace_kmh": long_pace,
            "variable_pace_data": None,
        })

        # ── Rest days (non-running, non-off days) ────────────────────────
        for day in WEEKDAY_ORDER:
            if day not in off_days and day != long_run_day and day not in run_days:
                workouts.append({
                    "week_number": week,
                    "day_name": day,
                    "workout_type": "rest",
                    "title": "Rest Day",
                    "description": (
                        "Active recovery: light stretching, yoga, or easy walking. No running."
                    ),
                    "target_distance_km": None,
                    "target_duration_seconds": None,
                    "target_pace_kmh": None,
                    "variable_pace_data": None,
                })

        # ── Off days ─────────────────────────────────────────────────────
        for day in off_days:
            workouts.append({
                "week_number": week,
                "day_name": day,
                "workout_type": "off",
                "title": "Off Day",
                "description": "Scheduled rest. Prioritize sleep, nutrition, and recovery.",
                "target_distance_km": None,
                "target_duration_seconds": None,
                "target_pace_kmh": None,
                "variable_pace_data": None,
            })

    goal_suffix = f" Goal: {ultimate_goal}." if ultimate_goal else ""
    description = (
        f"A {weeks}-week personalized {goal_name} training plan crafted by Stryde AI. "
        f"Progressive build with structured quality sessions and long runs to prepare you for race day.{goal_suffix}"
    )

    key_workout_types = [
        f"Long runs progressing toward {round(min(race_km * 0.9, race_km), 1)} km for endurance",
        "Tempo runs to improve sustained race pace control",
        "Intervals to build speed and running economy",
        "Easy and recovery runs for aerobic base and adaptation",
    ]

    if "5k" in goal_name.lower() or "10k" in goal_name.lower():
        key_workout_types[0] = "Progressive long runs to strengthen aerobic durability"
        key_workout_types[2] = "Short intervals and repeat efforts for speed sharpening"

    return {
        "name": f"{weeks}-Week {goal_name} Training Plan",
        "description": description,
        "target_distance": target_distance_label,
        "total_runs": total_run_count,
        "duration_weeks": weeks,
        "experience_level": exp_label,
        "goal_type": goal_type_raw,
        "key_workout_types": key_workout_types,
        "workouts": workouts,
    }
