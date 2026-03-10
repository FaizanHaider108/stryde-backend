from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import uuid

from ...crud import post as post_crud
from ...lib.db import get_db
from ...lib.security import get_current_user
from ...models import User
from ...schemas.comment import CommentCreate, CommentResponse
from ...schemas.post import PostCreate, PostResponse

router = APIRouter(prefix="/api/v1/posts", tags=["posts"])


@router.get("/me", response_model=list[PostResponse])
def list_my_posts(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return post_crud.list_user_posts(db, current_user.uid, current_user.uid)


@router.get("/{user_id:uuid}", response_model=list[PostResponse])
def list_user_posts(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user = db.query(User).filter(User.uid == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    return post_crud.list_user_posts(db, user.uid, current_user.uid)


@router.post("/", response_model=PostResponse, status_code=status.HTTP_201_CREATED)
def create_post(
    payload: PostCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = post_crud.create_post(db, current_user, payload)
    return post_crud.build_post_response(post, current_user.uid)


@router.post("/{post_id:uuid}/like", status_code=status.HTTP_204_NO_CONTENT)
def like_post(
    post_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = post_crud.get_post(db, str(post_id))
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="post not found")
    post_crud.like_post(db, current_user, post)


@router.get("/{post_id:uuid}/comments", response_model=list[CommentResponse])
def list_post_comments(
    post_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = post_crud.get_post(db, str(post_id))
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="post not found")
    return post_crud.list_post_comments(db, post, current_user.uid)


@router.post("/{post_id:uuid}/comment", response_model=CommentResponse, status_code=status.HTTP_201_CREATED)
def add_comment(
    post_id: uuid.UUID,
    payload: CommentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = post_crud.get_post(db, str(post_id))
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="post not found")
    comment = post_crud.create_comment(db, current_user, post, payload)
    return post_crud.build_comment_response(comment, current_user.uid)


@router.post("/{post_id:uuid}/{comment_id:uuid}/like", status_code=status.HTTP_204_NO_CONTENT)
def like_comment(
    post_id: uuid.UUID,
    comment_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = post_crud.get_post(db, str(post_id))
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="post not found")
    comment = post_crud.get_comment_for_post(db, post, str(comment_id))
    if not comment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="comment not found")
    post_crud.like_comment(db, current_user, comment)
