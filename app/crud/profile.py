import uuid
from math import floor
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from ..models.user import User
from ..schemas.profile import (
    PersonalInfoOut, 
    PersonalInfoUpdate, 
    SimpleUser, 
    ProfileWithSocialOut
)

# --- Conversion Helpers ---

def convert_height_meters_to_imperial(height_meters: Optional[float]) -> tuple[Optional[int], Optional[float]]:
    """Converts meters to a (feet, inches) tuple."""
    if height_meters is None:
        return None, None
    total_inches = height_meters / 0.0254
    feet = floor(total_inches / 12)
    inches = round(total_inches - (feet * 12), 2)
    return feet, inches


def convert_weight_kg_to_pounds(weight_kg: Optional[float]) -> Optional[float]:
    """Converts kilograms to pounds."""
    if weight_kg is None:
        return None
    return round(weight_kg * 2.20462262, 2)


# --- Profile Logic ---

def update_profile(db: Session, user: User, update_in: PersonalInfoUpdate) -> User:
    """Updates user profile fields and converts height/weight to metric for storage."""
    data = update_in.dict(exclude_unset=True)

    # Basic field updates
    if "full_name" in data:
        user.full_name = data["full_name"]
    if "profile_image_s3_key" in data:
        user.profile_image_s3_key = data["profile_image_s3_key"]
    if "date_of_birth" in data:
        user.date_of_birth = data["date_of_birth"]
    if "gender" in data:
        user.gender = data["gender"]

    # Store metrics only (meters, kilograms)
    if update_in.height:
        user.height = update_in.height.to_meters()
    if update_in.weight:
        user.weight = update_in.weight.to_kilograms()

    try:
        db.add(user)
        db.commit()
        db.refresh(user)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not update profile due to a database integrity error."
        ) from exc
        
    return user


def build_profile_response(user: User) -> PersonalInfoOut:
    """Constructs the standard profile response with both metric and imperial units."""
    height_m = user.height
    height_cm = round(height_m * 100, 2) if height_m is not None else None
    height_ft, height_in = convert_height_meters_to_imperial(height_m)
    
    weight_kg = user.weight
    weight_lb = convert_weight_kg_to_pounds(weight_kg)

    return PersonalInfoOut(
        uid=str(user.uid),
        email=user.email,
        full_name=user.full_name,
        profile_image_s3_key=user.profile_image_s3_key,
        date_of_birth=user.date_of_birth,
        gender=user.gender,
        height_m=height_m,
        height_cm=height_cm,
        height_ft=height_ft,
        height_in=height_in,
        weight_kg=weight_kg,
        weight_lb=weight_lb,
    )


# --- Social & Follower Logic ---

def _simple_user_from_model(u: User) -> SimpleUser:
    """Internal helper to convert a User model to a SimpleUser schema."""
    return SimpleUser(
        uid=str(u.uid), 
        full_name=u.full_name, 
        profile_image_s3_key=u.profile_image_s3_key
    )


def follow_user(db: Session, follower: User, target_uid: str) -> User:
    """Establishes a follow relationship between two users."""
    if str(follower.uid) == target_uid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="You cannot follow yourself."
        )

    try:
        target_id = uuid.UUID(target_uid)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Invalid target user ID format."
        )

    target = db.query(User).filter(User.uid == target_id).first()
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="The user you are trying to follow does not exist."
        )

    # Check if already following to prevent duplicates
    if target not in follower.following:
        follower.following.append(target)
        try:
            db.commit()
            db.refresh(follower)
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Error establishing follow relationship."
            )

    return target


def unfollow_user(db: Session, follower: User, target_uid: str) -> User:
    """Removes a follow relationship between two users."""
    if str(follower.uid) == target_uid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="You cannot unfollow yourself."
        )

    try:
        target_id = uuid.UUID(target_uid)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Invalid target user ID format."
        )

    target = db.query(User).filter(User.uid == target_id).first()
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="The user you are trying to unfollow does not exist."
        )

    if target in follower.following:
        follower.following.remove(target)
        db.commit()
        db.refresh(follower)

    return target


def build_profile_with_social(user: User) -> ProfileWithSocialOut:
    """Constructs a full profile response including follower/following lists and counts."""
    base = build_profile_response(user)

    followers = [_simple_user_from_model(u) for u in user.followers]
    following = [_simple_user_from_model(u) for u in user.following]

    return ProfileWithSocialOut(
        **base.dict(),
        follower_count=len(followers),
        following_count=len(following),
        followers=followers,
        following=following,
    )