from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
import uuid
from ...crud.profile import build_profile_response, update_profile
from ...crud.profile import follow_user, unfollow_user, build_profile_with_social
from ...crud import post as post_crud
from ...lib.db import get_db
from ...lib.security import get_current_user
from ...models.user import User
from ...models.user import followers
from ...models.subscription import UserSubscription
from ...schemas.profile import PersonalInfoOut, PersonalInfoUpdate
from ...schemas.profile import ProfileWithSocialOut
from ...schemas.profile import InviteUserOut
from ...schemas.post import PostCreate, PostResponse
from ...schemas.comment import CommentCreate, CommentResponse
from fastapi import HTTPException
from ...lib.glm_client import generate_short_suggestion


class PushTokenIn(BaseModel):
    expo_push_token: str


class NotificationPrefsIn(BaseModel):
    generalNotifications: bool = True
    trainingReminders: bool = True
    communityUpdates: bool = True
    raceAlerts: bool = True
    activityFeedback: bool = True


class WeatherSuggestionIn(BaseModel):
    temperature_c: float = Field(ge=-50, le=65)
    weather_label: str = Field(min_length=2, max_length=40)
    wind_speed_kmh: float = Field(ge=0, le=300)


class WeatherSuggestionOut(BaseModel):
    suggestion: str

router = APIRouter(prefix="/api/v1/profile", tags=["profile"])


@router.get("/me", response_model=PersonalInfoOut)
def get_my_profile(current_user: User = Depends(get_current_user)):
    return build_profile_response(current_user)


@router.patch("/me", response_model=PersonalInfoOut)
def update_my_profile(
    update_in: PersonalInfoUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    updated = update_profile(db, current_user, update_in)
    return build_profile_response(updated)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_my_account(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Remove rows that do not currently use DB-level ON DELETE CASCADE.
    db.query(UserSubscription).filter(UserSubscription.user_id == current_user.uid).delete()
    db.execute(
        followers.delete().where(
            (followers.c.follower_id == current_user.uid)
            | (followers.c.followed_id == current_user.uid)
        )
    )

    db.delete(current_user)
    db.commit()


@router.post("/me/push-token", status_code=204)
def register_push_token(
    payload: PushTokenIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_user.expo_push_token = payload.expo_push_token
    db.commit()


@router.get("/me/notification-prefs", response_model=NotificationPrefsIn)
def get_notification_prefs(current_user: User = Depends(get_current_user)):
    prefs = current_user.notification_prefs or {}
    return NotificationPrefsIn(
        generalNotifications=prefs.get("generalNotifications", True),
        trainingReminders=prefs.get("trainingReminders", True),
        communityUpdates=prefs.get("communityUpdates", True),
        raceAlerts=prefs.get("raceAlerts", True),
        activityFeedback=prefs.get("activityFeedback", True),
    )


@router.patch("/me/notification-prefs", status_code=204)
def update_notification_prefs(
    payload: NotificationPrefsIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_user.notification_prefs = payload.model_dump()
    db.commit()


@router.post("/me/weather-suggestion", response_model=WeatherSuggestionOut)
def generate_weather_suggestion(
    payload: WeatherSuggestionIn,
    _current_user: User = Depends(get_current_user),
):
    prompt = (
        "Create one practical running suggestion based on weather. "
        "Keep it motivational but safe. "
        f"Conditions: weather={payload.weather_label}, "
        f"temperature_c={payload.temperature_c:.1f}, "
        f"wind_speed_kmh={payload.wind_speed_kmh:.1f}. "
        "Must be <= 200 characters."
    )
    text = generate_short_suggestion(prompt=prompt, max_chars=200)
    return WeatherSuggestionOut(suggestion=text)


@router.get("/users", response_model=list[InviteUserOut])
def list_users(
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    users = db.query(User).order_by(User.full_name.asc()).all()
    return users



@router.get("/{uid:uuid}", response_model=ProfileWithSocialOut)
def get_user_profile(uid: uuid.UUID, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.uid == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    return build_profile_with_social(user)


@router.post("/{uid:uuid}/follow", response_model=ProfileWithSocialOut)
def follow(uid: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        target = follow_user(db, current_user, str(uid))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return build_profile_with_social(target)


@router.post("/{uid:uuid}/unfollow", response_model=ProfileWithSocialOut)
def unfollow(uid: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        target = unfollow_user(db, current_user, str(uid))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return build_profile_with_social(target)


@router.get("/{uid:uuid}/posts", response_model=list[PostResponse])
def list_profile_posts(uid: uuid.UUID, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.uid == uid).first()
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    return post_crud.list_user_posts(db, user.uid)


@router.post("/me/posts", response_model=PostResponse, status_code=201)
def create_post(payload: PostCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    post = post_crud.create_post(db, current_user, payload)
    return post_crud.build_post_response(post, current_user.uid)


@router.get("/{uid:uuid}/posts/{post_id:uuid}/comments", response_model=list[CommentResponse])
def list_post_comments(uid: uuid.UUID, post_id: uuid.UUID, db: Session = Depends(get_db)):
    post = post_crud.get_post_for_profile(db, str(post_id), uid)
    if not post:
        raise HTTPException(status_code=404, detail="post not found")
    return post_crud.list_post_comments(db, post)


@router.post("/{uid:uuid}/posts/{post_id:uuid}/comments", response_model=CommentResponse, status_code=201)
def add_comment(
    uid: uuid.UUID,
    post_id: uuid.UUID,
    payload: CommentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = post_crud.get_post_for_profile(db, str(post_id), uid)
    if not post:
        raise HTTPException(status_code=404, detail="post not found")
    comment = post_crud.create_comment(db, current_user, post, payload)
    return post_crud.build_comment_response(comment, current_user.uid)


@router.post("/{uid:uuid}/posts/{post_id:uuid}/comments/{comment_id:uuid}/like", status_code=204)
def like_comment(
    uid: uuid.UUID,
    post_id: uuid.UUID,
    comment_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = post_crud.get_post_for_profile(db, str(post_id), uid)
    if not post:
        raise HTTPException(status_code=404, detail="post not found")
    comment = post_crud.get_comment_for_post(db, post, str(comment_id))
    if not comment:
        raise HTTPException(status_code=404, detail="comment not found")
    post_crud.like_comment(db, current_user, comment)


@router.delete("/{uid:uuid}/posts/{post_id:uuid}/comments/{comment_id:uuid}/like", status_code=204)
def unlike_comment(
    uid: uuid.UUID,
    post_id: uuid.UUID,
    comment_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = post_crud.get_post_for_profile(db, str(post_id), uid)
    if not post:
        raise HTTPException(status_code=404, detail="post not found")
    comment = post_crud.get_comment_for_post(db, post, str(comment_id))
    if not comment:
        raise HTTPException(status_code=404, detail="comment not found")
    post_crud.unlike_comment(db, current_user, comment)
