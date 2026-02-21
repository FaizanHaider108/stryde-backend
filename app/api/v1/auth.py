from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from ...lib.db import get_db, engine, Base
from ...schemas.user import UserCreate, UserSignIn, UserOut, Token
from ...crud.user import create_user, authenticate_user, get_user_by_email
from ...lib.security import create_access_token

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


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
