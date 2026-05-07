"""CRUD operations for plans, plan workouts, and user plan enrollments."""
from typing import Optional, List
import uuid
from datetime import date, timedelta

from fastapi import HTTPException, status
from sqlalchemy import and_
from sqlalchemy.orm import Session, joinedload

from ..models import Plan, PlanWorkout, UserPlan, Run
from ..schemas.plan import PlanCreate, PlanWorkoutCreate, UserPlanCreate


def get_plan(db: Session, plan_id: uuid.UUID) -> Optional[Plan]:
    """Get a plan by ID with all its workouts."""
    return db.query(Plan).filter(Plan.id == plan_id).first()


def get_all_plans(
    db: Session,
    experience_level: Optional[str] = None,
    goal_type: Optional[str] = None,
) -> List[Plan]:
    """Get all plans with optional filtering by experience level and goal type.
    
    goal_type: 'marathon' or 'race'
    """
    query = db.query(Plan).filter(~Plan.is_custom_ai)
    
    if experience_level:
        query = query.filter(Plan.experience_level == experience_level)
    
    if goal_type:
        query = query.filter(Plan.goal_type == goal_type)
    
    return query.all()


def get_plan_with_workouts(db: Session, plan_id: uuid.UUID) -> Optional[Plan]:
    """Get a plan with all its workouts organized by week and day."""
    plan = db.query(Plan).filter(Plan.id == plan_id).first()
    if not plan:
        return None
    
    # Workouts are already loaded via relationship
    return plan


def create_plan(db: Session, payload: PlanCreate) -> Plan:
    """Create a new plan (admin operation)."""
    plan = Plan(
        name=payload.name,
        description=payload.description,
        target_distance=payload.target_distance,
        total_runs=payload.total_runs,
        duration_weeks=payload.duration_weeks,
        experience_level=payload.experience_level,
        goal_type=payload.goal_type,
        is_custom_ai=False,
    )
    
    db.add(plan)
    db.commit()
    db.refresh(plan)
    
    return plan


def create_plan_workout(
    db: Session,
    plan_id: uuid.UUID,
    payload: PlanWorkoutCreate,
) -> PlanWorkout:
    """Create a workout within a plan."""
    plan = db.query(Plan).filter(Plan.id == plan_id).first()
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan not found",
        )
    
    workout = PlanWorkout(
        plan_id=plan_id,
        week_number=payload.week_number,
        day_name=payload.day_name,
        workout_type=payload.workout_type,
        title=payload.title,
        description=payload.description,
        target_distance_km=payload.target_distance_km,
        target_duration_seconds=payload.target_duration_seconds,
        target_pace_kmh=payload.target_pace_kmh,
        variable_pace_data=payload.variable_pace_data,
    )
    
    db.add(workout)
    db.commit()
    db.refresh(workout)
    
    return workout


def get_user_active_plan(db: Session, user_id: uuid.UUID) -> Optional[UserPlan]:
    """Get the user's currently active plan with plan and workouts eager-loaded."""
    return (
        db.query(UserPlan)
        .options(joinedload(UserPlan.plan).joinedload(Plan.workouts))
        .filter(
            and_(
                UserPlan.user_id == user_id,
                UserPlan.is_active,
            )
        )
        .first()
    )


def get_user_plan(db: Session, user_plan_id: uuid.UUID) -> Optional[UserPlan]:
    """Get a specific user plan enrollment."""
    return db.query(UserPlan).filter(UserPlan.id == user_plan_id).first()


def create_user_plan(
    db: Session,
    user_id: uuid.UUID,
    payload: UserPlanCreate,
) -> UserPlan:
    """Enroll a user in a plan."""
    # Check if plan exists
    plan = db.query(Plan).filter(Plan.id == payload.plan_id).first()
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan not found",
        )
    
    # Check if user already has active plan (optional: prevent multiple active plans)
    existing_active = get_user_active_plan(db, user_id)
    if existing_active:
        # Deactivate existing plan if auto-switching is desired
        existing_active.is_active = False
        db.add(existing_active)
    
    # Calculate end date based on plan duration
    start_date = payload.start_date or date.today()
    end_date = start_date + timedelta(weeks=plan.duration_weeks)
    
    user_plan = UserPlan(
        user_id=user_id,
        plan_id=payload.plan_id,
        start_date=start_date,
        end_date=end_date,
        is_active=True,
    )
    
    db.add(user_plan)
    db.commit()
    db.refresh(user_plan)
    
    return user_plan


def end_user_plan(db: Session, user_plan_id: uuid.UUID) -> Optional[UserPlan]:
    """End/deactivate a user's plan."""
    user_plan = db.query(UserPlan).filter(UserPlan.id == user_plan_id).first()
    if not user_plan:
        return None
    
    user_plan.is_active = False
    db.add(user_plan)
    db.commit()
    db.refresh(user_plan)
    
    return user_plan


def get_plan_progress(
    db: Session,
    user_plan_id: uuid.UUID,
) -> dict:
    """Calculate progress stats for a user's plan."""
    user_plan = db.query(UserPlan).filter(UserPlan.id == user_plan_id).first()
    if not user_plan:
        return {}
    
    plan = user_plan.plan
    user_id = user_plan.user_id
    
    # Get all runs for this user since plan start
    completed_runs = (
        db.query(Run)
        .filter(
            and_(
                Run.user_id == user_id,
                Run.start_time >= user_plan.start_date,
                Run.start_time <= user_plan.end_date,
            )
        )
        .all()
    )
    
    # Calculate metrics
    total_planned_runs = plan.total_runs
    completed_run_count = len(completed_runs)
    completion_percentage = (completed_run_count / total_planned_runs * 100) if total_planned_runs > 0 else 0
    
    total_distance_km = sum(run.distance_km for run in completed_runs)
    
    # Target hit percentage (runs that met pace targets)
    target_hits = 0
    for run in completed_runs:
        if run.plan_workout and run.plan_workout.target_pace_kmh:
            # If actual pace >= target pace, count as hit
            if run.average_pace and run.average_pace >= run.plan_workout.target_pace_kmh:
                target_hits += 1
    
    target_hit_percentage = (target_hits / completed_run_count * 100) if completed_run_count > 0 else 0
    
    return {
        "plan_id": plan.id,
        "plan_name": plan.name,
        "completion_percentage": round(completion_percentage, 2),
        "target_hit_percentage": round(target_hit_percentage, 2),
        "completed_runs": completed_run_count,
        "total_planned_runs": total_planned_runs,
        "total_distance_km": round(total_distance_km, 2),
        "start_date": str(user_plan.start_date),
        "end_date": str(user_plan.end_date),
    }
