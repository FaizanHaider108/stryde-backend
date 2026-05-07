"""API routes for training plans."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
import uuid
import logging
from typing import Optional

from ...crud import plan as plan_crud
from ...lib.db import get_db
from ...lib.glm_client import GlmClientError, generate_plan_json
from ...lib.security import get_current_user
from ...models import User, Plan, PlanWorkout
from ...models.subscription import UserSubscription
from ...schemas.plan import (
    CustomPlanGenerateRequest,
    GeneratedPlanPayload,
    PlanCreate,
    PlanResponse,
    PlanWorkoutCreate,
    PlanWorkoutResponse,
    UserPlanCreate,
    UserPlanResponse,
)

router = APIRouter(prefix="/api/v1/plans", tags=["plans"])
logger = logging.getLogger(__name__)


def _ensure_active_subscription(db: Session, current_user: User) -> None:
    subscription = (
        db.query(UserSubscription)
        .filter(UserSubscription.user_id == current_user.uid)
        .first()
    )
    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Active subscription required",
        )
    now_utc = datetime.now(timezone.utc)
    is_expired = bool(subscription.current_period_end and subscription.current_period_end <= now_utc)
    is_effectively_active = bool(
        subscription.is_active
        and subscription.status in {"active", "trialing"}
        and not is_expired
    )

    if subscription.is_active != is_effectively_active:
        subscription.is_active = is_effectively_active
        if is_expired:
            subscription.status = "expired"
        db.commit()

    if not is_effectively_active:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Active subscription required",
        )


def _build_generation_prompt(payload: CustomPlanGenerateRequest) -> str:
    # Calculate exact training weeks from the date window
    weeks = max(4, min((payload.race_day - payload.start_date).days // 7, 24))

    # Map goal type → target race distance label
    gl = payload.goal_type.lower()
    if "ultra" in gl:
        target_distance = "50+ km (Ultra Marathon)"
    elif "full marathon" in gl or ("marathon" in gl and "half" not in gl):
        target_distance = "42.2 km (Full Marathon)"
    elif "half" in gl:
        target_distance = "21.1 km (Half Marathon)"
    elif "10" in gl:
        target_distance = "10 km"
    elif "5" in gl:
        target_distance = "5 km"
    else:
        target_distance = "Race Distance"

    off_days_text = ", ".join(payload.off_days) if payload.off_days else "None"

    return f"""
You are an expert running coach. Generate a {weeks}-week personalized training plan as JSON.

CRITICAL RULES:
- You MUST generate exactly {weeks} weeks (week_number 1 to {weeks}).
- Plan name must be: "{weeks}-Week [Goal Name] Training Plan" (e.g. "{weeks}-Week Half Marathon Training Plan").
- target_distance MUST be: "{target_distance}".
- duration_weeks MUST be exactly: {weeks}.
- experience_level MUST be: "{payload.experience_level or 'Intermediate'}".
- Every week MUST have ALL 7 days (MONDAY through SUNDAY).
- Do NOT schedule runs on off days: {off_days_text}. Use workout_type "off" for those days.
- The preferred long run day is: {payload.long_run_day or 'SATURDAY'}. Put the longest run there.
- Schedule 3-4 runs per week on available days. All other days use workout_type "rest".
- Apply progressive overload: distance and intensity increase each week, then taper in final 2 weeks.
- workout_type must be one of: "easy", "tempo", "intervals", "long_run", "recovery", "rest", "off".
- key_workout_types must contain exactly 3 or 4 concise bullet-ready strings (no numbering, no markdown).
- key_workout_types must match the generated plan style and race goal.

Return ONLY this JSON structure, no markdown:
{{
    "name": string,
    "description": string,
    "target_distance": "{target_distance}",
    "total_runs": number,
    "duration_weeks": {weeks},
    "experience_level": "{payload.experience_level or 'Intermediate'}",
    "goal_type": string,
    "key_workout_types": [string, string, string, string?],
    "workouts": [
        {{
            "week_number": number,
            "day_name": "MONDAY"|"TUESDAY"|"WEDNESDAY"|"THURSDAY"|"FRIDAY"|"SATURDAY"|"SUNDAY",
            "workout_type": string,
            "title": string,
            "description": string,
            "target_distance_km": number | null,
            "target_duration_seconds": number | null,
            "target_pace_kmh": number | null,
            "variable_pace_data": object | null
        }}
    ]
}}

User profile:
- Goal type: {payload.goal_type}
- Ultimate goal: {payload.ultimate_goal or 'Not specified'}
- Experience level: {payload.experience_level or 'Intermediate'}
- Target pace (min/mile): {payload.target_pace_min_per_mile or 'Not specified'}
- Start date: {payload.start_date.isoformat()}
- Race day: {payload.race_day.isoformat()}
- Training duration: {weeks} weeks
- Off days: {off_days_text}
- Preferred long run day: {payload.long_run_day or 'Saturday'}
""".strip()


def _persist_generated_plan(
        db: Session,
        current_user: User,
        payload: GeneratedPlanPayload,
) -> Plan:
        plan = Plan(
                name=payload.name,
                description=payload.description,
                target_distance=payload.target_distance,
                total_runs=payload.total_runs,
                duration_weeks=payload.duration_weeks,
                experience_level=payload.experience_level,
                goal_type=payload.goal_type,
                is_custom_ai=True,
                creator_id=current_user.uid,
        )
        db.add(plan)
        db.commit()
        db.refresh(plan)

        workouts = [
                PlanWorkout(
                        plan_id=plan.id,
                        week_number=w.week_number,
                        day_name=w.day_name,
                        workout_type=w.workout_type,
                        title=w.title,
                        description=w.description,
                        target_distance_km=w.target_distance_km,
                        target_duration_seconds=w.target_duration_seconds,
                        target_pace_kmh=w.target_pace_kmh,
                        variable_pace_data=w.variable_pace_data,
                )
                for w in payload.workouts
        ]
        db.add_all(workouts)
        db.commit()
        db.refresh(plan)
        return plan


def _derive_key_workout_types_from_workouts(workouts: list) -> list[str]:
    workout_type_map = {
        "long_run": "Long runs to build race-day endurance",
        "tempo": "Tempo sessions to improve sustained threshold pace",
        "intervals": "Intervals for speed development and turnover",
        "easy": "Easy aerobic runs to build your base",
        "recovery": "Recovery runs to absorb training load",
    }

    seen: list[str] = []
    for workout in workouts:
        workout_type = getattr(workout, "workout_type", None) if hasattr(workout, "workout_type") else workout.get("workout_type")
        if workout_type in workout_type_map and workout_type_map[workout_type] not in seen:
            seen.append(workout_type_map[workout_type])

    defaults = [
        "Long runs to build race-day endurance",
        "Tempo sessions to improve sustained threshold pace",
        "Intervals for speed development and turnover",
        "Easy and recovery runs to support consistency",
    ]

    merged = seen + [d for d in defaults if d not in seen]
    return merged[:4] if len(merged) >= 4 else merged[:3]


# ===== LIST/CREATE PLANS =====


@router.get("/", response_model=list[PlanResponse])
def list_plans(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    experience_level: str = Query(None),
    goal_type: str = Query(None),
):
    """Get all plans with optional filtering."""
    _ensure_active_subscription(db, current_user)
    return plan_crud.get_all_plans(
        db,
        experience_level=experience_level,
        goal_type=goal_type,
    )


@router.post("/", response_model=PlanResponse, status_code=status.HTTP_201_CREATED)
def create_plan_endpoint(
    payload: PlanCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new plan (admin only)."""
    return plan_crud.create_plan(db, payload)


@router.post("/me/custom/generate/", response_model=PlanResponse, status_code=status.HTTP_201_CREATED)
def generate_custom_plan(
    payload: CustomPlanGenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate a custom plan via GLM cloud and save it."""
    logger.info(f"Starting custom plan generation for user {current_user.uid}")
    
    if payload.race_day <= payload.start_date:
        raise HTTPException(status_code=400, detail="Race day must be after start date")

    prompt = _build_generation_prompt(payload)
    logger.info(f"Built generation prompt ({len(prompt)} chars)")

    try:
        logger.info("Calling GLM API...")
        ai_json = generate_plan_json(prompt)
        logger.info("GLM API returned successfully")
        
        generated_payload = GeneratedPlanPayload.model_validate(ai_json)
        logger.info(f"Generated payload validated: {generated_payload.name}")
    except GlmClientError as exc:
        logger.error(f"GLM client error: {str(exc)}")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        logger.error(f"Validation error: {str(exc)}")
        raise HTTPException(status_code=422, detail="AI response validation failed") from exc

    if not generated_payload.workouts:
        raise HTTPException(status_code=422, detail="AI did not generate workouts")

    # Guardrails to keep persisted data sensible even if model drifts.
    generated_payload.duration_weeks = max(4, min(generated_payload.duration_weeks, 24))
    generated_payload.total_runs = max(1, generated_payload.total_runs)
    generated_payload.key_workout_types = [
        item.strip()
        for item in (generated_payload.key_workout_types or [])
        if isinstance(item, str) and item.strip()
    ][:4]

    plan = _persist_generated_plan(db, current_user, generated_payload)
    # Attach key workout bullets for immediate frontend rendering on generate response.
    # This is not persisted in DB yet, but is returned to the client in this response.
    key_workout_types = generated_payload.key_workout_types
    if len(key_workout_types) < 3:
        key_workout_types = _derive_key_workout_types_from_workouts(generated_payload.workouts)
    setattr(plan, "key_workout_types", key_workout_types)

    logger.info(f"Plan persisted: {plan.id}")
    return plan


# ===== USER PLAN ENDPOINTS (must come BEFORE /{plan_id:uuid}) =====


@router.get("/me/active/", response_model=Optional[UserPlanResponse])
def get_my_active_plan(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the user's currently active plan."""
    _ensure_active_subscription(db, current_user)
    user_plan = plan_crud.get_user_active_plan(db, current_user.uid)
    return user_plan


@router.get("/me/active/progress/", response_model=dict)
def get_my_plan_progress(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get progress stats for user's active plan."""
    _ensure_active_subscription(db, current_user)
    user_plan = plan_crud.get_user_active_plan(db, current_user.uid)
    if not user_plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active plan",
        )
    
    return plan_crud.get_plan_progress(db, user_plan.id)


@router.post("/me/enroll/", response_model=UserPlanResponse, status_code=status.HTTP_201_CREATED)
def enroll_in_plan(
    payload: UserPlanCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Enroll the current user in a plan."""
    _ensure_active_subscription(db, current_user)
    return plan_crud.create_user_plan(db, current_user.uid, payload)


# ===== PLAN DETAIL ENDPOINTS =====


@router.get("/{plan_id:uuid}/", response_model=PlanResponse)
def get_plan_detail(
    plan_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get plan details with all workouts."""
    _ensure_active_subscription(db, current_user)
    logger.debug("Fetching plan detail for plan_id=%s user_id=%s", plan_id, current_user.uid)
    plan = plan_crud.get_plan_with_workouts(db, plan_id)
    if not plan:
        logger.info("Plan not found for plan_id=%s", plan_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan not found",
        )
    logger.debug("Plan found for plan_id=%s with workouts=%s", plan_id, len(plan.workouts))
    return plan


@router.post("/{plan_id:uuid}/workouts/", response_model=PlanWorkoutResponse, status_code=status.HTTP_201_CREATED)
def create_plan_workout(
    plan_id: uuid.UUID,
    payload: PlanWorkoutCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add a workout to a plan (admin only)."""
    return plan_crud.create_plan_workout(db, plan_id, payload)


@router.patch("/{user_plan_id:uuid}/end/", response_model=UserPlanResponse)
def end_plan(
    user_plan_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """End a user's plan."""
    user_plan = plan_crud.get_user_plan(db, user_plan_id)
    if not user_plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User plan not found",
        )
    
    # Verify user owns this plan
    if user_plan.user_id != current_user.uid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    
    return plan_crud.end_user_plan(db, user_plan_id)
