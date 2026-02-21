from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from ..models.user import User, RunnerType, AuthProvider
from ..schemas.user import UserCreate
from ..lib.security import get_password_hash, verify_password


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
