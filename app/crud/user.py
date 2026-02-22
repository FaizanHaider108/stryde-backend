from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..lib.security import get_password_hash, verify_password
from ..models.user import AuthProvider, PersonalInfo, RunnerType, User
from ..schemas.profile import PersonalInfoCreate, PersonalInfoUpdate
from ..schemas.user import UserCreate


def get_user_by_email(db: Session, email: str):
    return db.query(User).filter(User.email == email).first()


def create_user(db: Session, user_in: UserCreate):
    hashed = get_password_hash(user_in.password)
    user = User(
        full_name=user_in.full_name,
        email=user_in.email,
        password_hash=hashed,
        runner_type=RunnerType(user_in.runner_type.value if hasattr(user_in.runner_type, 'value') else user_in.runner_type),
        auth_provider=AuthProvider.credentials,
    )
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        return None
    return user


def authenticate_user(db: Session, email: str, password: str):
    user = get_user_by_email(db, email)
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def get_personal_info_by_user_uid(db: Session, user_uid: str):
    return db.query(PersonalInfo).filter(PersonalInfo.user_uid == user_uid).first()


def create_personal_info(db: Session, user_uid: str, info_in: PersonalInfoCreate):
    info = PersonalInfo(
        user_uid=user_uid,
        profile_image=info_in.profile_image,
        full_name=info_in.full_name,
        email=info_in.email,
        date_of_birth=info_in.date_of_birth,
        gender=info_in.gender,
        height=info_in.height,
        weight=info_in.weight,
    )
    db.add(info)
    try:
        db.commit()
        db.refresh(info)
    except IntegrityError:
        db.rollback()
        return None
    return info


def update_personal_info(db: Session, user_uid: str, info_in: PersonalInfoUpdate):
    info = get_personal_info_by_user_uid(db, user_uid)
    if not info:
        return None
    for field, value in info_in.dict(exclude_unset=True).items():
        setattr(info, field, value)
    db.add(info)
    db.commit()
    db.refresh(info)
    return info

# def login_social_user(db: Session, email: str, full_name: str, runner_type: RunnerType, provider: str):
#     user = get_user_by_email(db, email)
#     if user:
#         return user
#     # Create new user with no password for social login
#     user = User(
#         email=email,
#         full_name=full_name,
#         password_hash=None,
#         auth_provider=AuthProvider(provider),
#         runner_type=runner_type,
#     )
#     db.add(user)
#     try:
#         db.commit()
#         db.refresh(user)
#     except IntegrityError:
#         db.rollback()
#         return None
#     return user
