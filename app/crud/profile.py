from math import floor
from typing import Optional

from sqlalchemy.orm import Session

from ..models.user import User
from ..schemas.profile import PersonalInfoOut, PersonalInfoUpdate


def convert_height_meters_to_imperial(height_meters: Optional[float]) -> tuple[Optional[int], Optional[float]]:
    if height_meters is None:
        return None, None
    total_inches = height_meters / 0.0254
    feet = floor(total_inches / 12)
    inches = round(total_inches - (feet * 12), 2)
    return feet, inches


def convert_weight_kg_to_pounds(weight_kg: Optional[float]) -> Optional[float]:
    if weight_kg is None:
        return None
    return round(weight_kg * 2.20462262, 2)


def update_profile(db: Session, user: User, update_in: PersonalInfoUpdate) -> User:
    data = update_in.dict(exclude_unset=True)

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

    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def build_profile_response(user: User) -> PersonalInfoOut:
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
