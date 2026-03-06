import logging
import os

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ...crud.auth import (
    authenticate_user,
    create_password_reset_token,
    create_user,
    get_user_by_email,
    get_valid_password_reset_token,
    reset_password_with_token,
)
from ...lib.db import get_db
from ...lib.mailer import send_email
from ...lib.security import RESET_TOKEN_EXPIRE_MINUTES, create_access_token, hash_password_reset_token
from ...schemas.auth import (
    MessageResponse,
    PasswordResetConfirm,
    PasswordResetRequest,
    Token,
    UserCreate,
    UserOut,
    UserSignIn,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
logger = logging.getLogger(__name__)


@router.post("/signup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def signup(user_in: UserCreate, db: Session = Depends(get_db)):
    existing = get_user_by_email(db, user_in.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user = create_user(db, user_in)
    if not user:
        raise HTTPException(status_code=400, detail="Could not create user")
    return user


@router.post("/signin", response_model=Token)
def signin(form_data: UserSignIn, db: Session = Depends(get_db)):
    # using UserSignIn for simplicity: expects email and password fields
    user = authenticate_user(db, form_data.email, form_data.password)
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    payload = {"full_name": user.full_name, "email": user.email, "runner_type": user.runner_type.value}
    token = create_access_token(payload)
    return {"access_token": token}


@router.post("/password-reset/request", response_model=MessageResponse)
def request_password_reset(payload: PasswordResetRequest, db: Session = Depends(get_db)):
    reset_url_base = os.getenv("RESET_PASSWORD_URL")
    if not reset_url_base:
        raise HTTPException(status_code=500, detail="RESET_PASSWORD_URL not configured")

    user = get_user_by_email(db, payload.email)
    if user:
        raw_token, _reset_token = create_password_reset_token(db, user)
        reset_link = f"{reset_url_base}?token={raw_token}"
        subject = os.getenv("PASSWORD_RESET_SUBJECT", "Reset your Stryde password")
        body = (
            "We received a request to reset your password.\n\n"
            f"Reset link: {reset_link}\n\n"
            f"This link expires in {RESET_TOKEN_EXPIRE_MINUTES} minutes.\n"
            "If you did not request a password reset, you can ignore this email."
        )
        try:
            send_email(user.email, subject, body)
        except ValueError:
            logger.exception("Failed to send password reset email")

    return {"message": "If an account exists for that email, a reset link has been sent."}


@router.post("/password-reset/confirm", response_model=MessageResponse)
def confirm_password_reset(payload: PasswordResetConfirm, db: Session = Depends(get_db)):
    token_hash = hash_password_reset_token(payload.token)
    reset_token = get_valid_password_reset_token(db, token_hash)
    if not reset_token:
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    reset_password_with_token(db, reset_token, payload.new_password)
    return {"message": "Password reset successful"}

# @router.post("/social-login", response_model=Token)
# def social_login(request: SocialLoginRequest, db: Session = Depends(get_db)):
#     email = None
#     full_name = None
    
#     if request.provider == "google":
#         try:
#             # Verify the Google token
#             idinfo = id_token.verify_oauth2_token(request.token, requests.Request(), GOOGLE_CLIENT_ID)
#             email = idinfo['email']
#             # Google includes 'name' in the verified payload
#             full_name = idinfo.get('name', 'Unknown User') 
#         except ValueError:
#             raise HTTPException(status_code=400, detail="Invalid Google token")

#     # elif request.provider == "apple":
#     #     # 1. Verify the Apple identityToken (using a library like pyjwt)
#     #     # 2. Extract the email from the decoded token
#     #     # 3. Get the name from the request body (Frontend must send it on first login!)
#     #     email = decoded_apple_token['email']
#     #     full_name = request.name_from_frontend or "Apple User" 

#     else:
#         raise HTTPException(status_code=400, detail="Unsupported provider")

#     # Now pass the clean, extracted data to your database function
#     user = login_social_user(
#         db=db, 
#         email=email, 
#         full_name=full_name, 
#         runner_type=request.runner_type, 
#         provider=request.provider
#     )
