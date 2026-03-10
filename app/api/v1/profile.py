from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
import uuid
from ...crud.profile import build_profile_response, update_profile
from ...crud.profile import follow_user, unfollow_user, build_profile_with_social
from ...crud import post as post_crud
from ...lib.db import get_db
from ...lib.security import get_current_user
from ...models.user import User
from ...schemas.profile import PersonalInfoOut, PersonalInfoUpdate
from ...schemas.profile import ProfileWithSocialOut
from ...schemas.post import PostCreate, PostResponse
from ...schemas.comment import CommentCreate, CommentResponse
from fastapi import HTTPException
from sqlalchemy.orm import Session

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
