import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from ...crud import chat as chat_crud
from ...lib.db import SessionLocal, get_db
from ...lib.realtime import realtime_manager
from ...lib.security import decode_access_token, get_current_user
from ...models import User
from ...schemas.chat import ClubMessageOut, MessageReadRequest, MessageReadResponse

router = APIRouter(prefix="/api/v1/clubs", tags=["chat"])

MAX_MESSAGE_LENGTH = 2000


def _extract_ws_token(websocket: WebSocket) -> Optional[str]:
    token = websocket.query_params.get("token")
    if token:
        return token
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


@router.get("/{club_id:uuid}/messages", response_model=list[ClubMessageOut])
def list_club_messages(
    club_id: uuid.UUID,
    limit: int = 50,
    before: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if limit <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="limit must be positive")
    limit = min(limit, 200)
    return chat_crud.list_messages(db, club_id, current_user, limit=limit, before=before)


@router.post("/{club_id:uuid}/messages/read", response_model=MessageReadResponse)
def mark_messages_read(
    club_id: uuid.UUID,
    payload: MessageReadRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    message_ids = payload.message_ids
    if message_ids:
        message_ids = [uuid.UUID(str(mid)) for mid in message_ids]
    new_ids, read_at = chat_crud.mark_messages_read(
        db,
        club_id,
        current_user,
        message_ids=message_ids,
        up_to=payload.up_to,
    )
    if new_ids:
        realtime_manager.broadcast_to_club_sync(
            club_id,
            {
                "type": "message.read",
                "message_ids": [str(mid) for mid in new_ids],
                "user_id": str(current_user.uid),
                "read_at": read_at.isoformat(),
            },
        )
    return MessageReadResponse(message_ids=new_ids, read_at=read_at)


@router.websocket("/{club_id:uuid}/ws")
async def club_chat_ws(websocket: WebSocket, club_id: uuid.UUID):
    await websocket.accept() 
    
    db = SessionLocal()
    connected = False
    try:
        token = _extract_ws_token(websocket)
        if not token:
            await websocket.close(code=1008, reason="Missing token")
            return

        try:
            user = _get_user_from_token(db, token)
        except Exception as e: 
            print(f"WebSocket Auth Error: {repr(e)}")
            await websocket.close(code=1008, reason="Invalid or missing data in token")
            return

        try:
            history = chat_crud.list_messages(db, club_id, user, limit=50)
        except Exception as e:
            print(f"History Fetch Error: {repr(e)}")
            await websocket.close(code=1008, reason="Failed to fetch history")
            return

        await realtime_manager.connect_club(club_id, websocket)
        connected = True
        
        await websocket.send_json({
            "type": "message.history",
            "messages": jsonable_encoder(history),
        })

        while True:
            data = await websocket.receive_json()
            event_type = data.get("type")

            if event_type == "message.send":
                body = (data.get("body") or "").strip()
                if not body:
                    await websocket.send_json({"type": "error", "detail": "Message body is required"})
                    continue
                if len(body) > MAX_MESSAGE_LENGTH:
                    await websocket.send_json({"type": "error", "detail": "Message too long"})
                    continue

                try:
                    message = chat_crud.create_message(db, user, club_id, body)
                except HTTPException as exc:
                    await websocket.send_json({"type": "error", "detail": exc.detail})
                    continue

                message_out = chat_crud.build_message_out(message, user.uid)
                await realtime_manager.broadcast_to_club(
                    club_id,
                    {"type": "message.new", "message": jsonable_encoder(message_out)},
                )
                continue

            if event_type == "message.read":
                raw_ids = data.get("message_ids")
                up_to_raw = data.get("up_to")
                message_ids = None
                up_to = None

                if raw_ids:
                    try:
                        message_ids = [uuid.UUID(str(mid)) for mid in raw_ids]
                    except (ValueError, TypeError):
                        await websocket.send_json({"type": "error", "detail": "Invalid message_ids"})
                        continue
                if up_to_raw:
                    try:
                        up_to = datetime.fromisoformat(str(up_to_raw))
                    except ValueError:
                        await websocket.send_json({"type": "error", "detail": "Invalid up_to timestamp"})
                        continue

                try:
                    new_ids, read_at = chat_crud.mark_messages_read(
                        db,
                        club_id,
                        user,
                        message_ids=message_ids,
                        up_to=up_to,
                    )
                except HTTPException as exc:
                    await websocket.send_json({"type": "error", "detail": exc.detail})
                    continue
                if new_ids:
                    await realtime_manager.broadcast_to_club(
                        club_id,
                        {
                            "type": "message.read",
                            "message_ids": [str(mid) for mid in new_ids],
                            "user_id": str(user.uid),
                            "read_at": read_at.isoformat(),
                        },
                    )
                continue

            await websocket.send_json({"type": "error", "detail": "Unsupported event type"})
    except WebSocketDisconnect:
        pass
    finally:
        if connected:
            await realtime_manager.disconnect_club(club_id, websocket)
        db.close()
