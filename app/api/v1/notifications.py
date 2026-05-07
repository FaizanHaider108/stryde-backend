import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from ...crud import notification as notification_crud
from ...lib.db import SessionLocal, get_db
from ...lib.realtime import realtime_manager
from ...lib.security import decode_access_token, get_current_user
from ...models import User
from ...schemas.notification import NotificationOut, NotificationReadResponse

router = APIRouter(tags=["notifications"])


def _extract_ws_token(websocket: WebSocket) -> Optional[str]:
    auth_header = websocket.headers.get("Authorization")
    if not auth_header:
        return None
    parts = auth_header.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return None


def _get_user_from_token(db: Session, token: str) -> User:
    payload = decode_access_token(token)
    email = payload.get("email")
    if not email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


@router.get("/api/v1/notifications", response_model=list[NotificationOut])
def list_notifications(
    limit: int = 50,
    before: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if limit <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="limit must be positive")
    limit = min(limit, 200)
    notifications = notification_crud.list_notifications(db, current_user, limit=limit, before=before)
    return [notification_crud.build_notification_out(n) for n in notifications]


@router.post("/api/v1/notifications/{notification_id:uuid}/read", response_model=NotificationReadResponse)
def mark_notification_read(
    notification_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    notification = notification_crud.get_notification(db, notification_id)
    if not notification:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="notification not found")
    updated = notification_crud.mark_notification_read(db, notification, current_user)
    realtime_manager.send_to_user_sync(
        current_user.uid,
        {
            "type": "notification.read",
            "notification_ids": [str(updated.id)],
            "read_at": updated.read_at.isoformat() if updated.read_at else None,
        },
    )
    return NotificationReadResponse(id=updated.id, read_at=updated.read_at)


@router.websocket("/api/v1/ws/notifications")
async def notifications_ws(websocket: WebSocket):
    db = SessionLocal()
    user: Optional[User] = None
    connected = False
    try:
        token = _extract_ws_token(websocket)
        if not token:
            await websocket.close(code=1008)
            return

        try:
            user = _get_user_from_token(db, token)
        except HTTPException:
            await websocket.close(code=1008)
            return

        history = notification_crud.list_notifications(db, user, limit=50)
        await realtime_manager.connect_user(user.uid, websocket)
        connected = True
        await websocket.send_json({
            "type": "notification.history",
            "notifications": jsonable_encoder([notification_crud.build_notification_out(n) for n in history]),
        })

        while True:
            data = await websocket.receive_json()
            event_type = data.get("type")

            if event_type == "notification.read":
                raw_ids = data.get("notification_ids") or []
                try:
                    notification_ids = [uuid.UUID(str(nid)) for nid in raw_ids]
                except (ValueError, TypeError):
                    await websocket.send_json({"type": "error", "detail": "Invalid notification_ids"})
                    continue

                try:
                    ids, read_at = notification_crud.mark_notifications_read(db, user, notification_ids)
                except HTTPException as exc:
                    await websocket.send_json({"type": "error", "detail": exc.detail})
                    continue
                if ids:
                    await realtime_manager.send_to_user(
                        user.uid,
                        {
                            "type": "notification.read",
                            "notification_ids": [str(nid) for nid in ids],
                            "read_at": read_at.isoformat(),
                        },
                    )
                continue

            await websocket.send_json({"type": "error", "detail": "Unsupported event type"})
    except WebSocketDisconnect:
        pass
    finally:
        if user and connected:
            await realtime_manager.disconnect_user(user.uid, websocket)
        db.close()
