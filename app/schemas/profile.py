from enum import Enum
from typing import Optional
from datetime import date

from pydantic import BaseModel, EmailStr, validator


class Gender(str, Enum):
    male = "male"
    female = "female"
    other = "other"
    prefer_not_to_say = "prefer_not_to_say"


class HeightUnit(str, Enum):
    meters = "m"
    centimeters = "cm"
    feet_inches = "ft_in"


class WeightUnit(str, Enum):
    kilograms = "kg"
    pounds = "lb"


class HeightPayload(BaseModel):
    # Accept either a metric `value` (meters or centimeters) OR separate
    # `feet` + `inches` when `unit` == `ft_in`.
    unit: HeightUnit
    # metric value (meters or centimeters depending on `unit`)
    value: Optional[float] = None
    # imperial components used when unit == ft_in
    feet: Optional[int] = None
    inches: Optional[float] = None

    @validator("value")
    def validate_value(cls, value: Optional[float], values):
        unit = values.get("unit")
        if unit in {HeightUnit.meters, HeightUnit.centimeters}:
            if value is None or value <= 0:
                raise ValueError("metric height `value` must be provided and positive")
        return value

    @validator("feet")
    def validate_feet(cls, feet: Optional[int], values):
        unit = values.get("unit")
        if unit == HeightUnit.feet_inches:
            if feet is None or feet < 0:
                raise ValueError("feet must be provided and non-negative for imperial height")
        return feet

    @validator("inches")
    def validate_inches(cls, inches: Optional[float], values):
        unit = values.get("unit")
        if unit == HeightUnit.feet_inches:
            if inches is None:
                inches = 0
            if inches < 0 or inches >= 12:
                raise ValueError("inches must be between 0 and <12")
        return inches

    def to_meters(self) -> float:
        if self.unit == HeightUnit.meters:
            return float(self.value)
        if self.unit == HeightUnit.centimeters:
            return float(self.value) / 100.0
        # imperial: feet + inches
        total_inches = (int(self.feet) * 12) + (float(self.inches) if self.inches is not None else 0.0)
        return total_inches * 0.0254


class WeightPayload(BaseModel):
    value: float
    unit: WeightUnit

    @validator("value")
    def validate_value(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("weight must be positive")
        return value

    def to_kilograms(self) -> float:
        if self.unit == WeightUnit.kilograms:
            return self.value
        return self.value * 0.45359237


class PersonalInfoCreate(BaseModel):
    profile_image_s3_key: Optional[str] = None
    full_name: str
    date_of_birth: Optional[date] = None
    gender: Optional[Gender] = None
    height: Optional[HeightPayload] = None
    weight: Optional[WeightPayload] = None


class PersonalInfoUpdate(BaseModel):
    profile_image_s3_key: Optional[str] = None
    full_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    gender: Optional[Gender] = None
    height: Optional[HeightPayload] = None
    weight: Optional[WeightPayload] = None

    @validator("full_name")
    def validate_full_name(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() if value else value


class PersonalInfoOut(BaseModel):
    uid: str
    email: EmailStr
    full_name: str
    profile_image_s3_key: Optional[str]
    date_of_birth: Optional[date]
    gender: Optional[Gender]
    height_m: Optional[float]
    height_cm: Optional[float]
    height_ft: Optional[int]
    height_in: Optional[float]
    weight_kg: Optional[float]
    weight_lb: Optional[float]

    class Config:
        orm_mode = True
