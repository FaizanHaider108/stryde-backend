import logging
from typing import Optional
import uuid

from ..crud import notification as notification_crud
from ..lib.realtime import realtime_manager
from ..models import NotificationType

logger = logging.getLogger(__name__)


def _model_dump(model_obj) -> dict:
    if hasattr(model_obj, "model_dump"):
        return model_obj.model_dump()
    return model_obj.dict()


def notify_user(
    db,
    user_id: uuid.UUID,
    notif_type: NotificationType,
    actor_id: Optional[uuid.UUID] = None,
    club_id: Optional[uuid.UUID] = None,
    event_id: Optional[uuid.UUID] = None,
    post_id: Optional[uuid.UUID] = None,
    comment_id: Optional[uuid.UUID] = None,
    payload: Optional[dict] = None,
) -> None:
    try:
        notification = notification_crud.create_notification(
            db,
            user_id=user_id,
            notif_type=notif_type,
            actor_id=actor_id,
            club_id=club_id,
            event_id=event_id,
            post_id=post_id,
            comment_id=comment_id,
            payload=payload,
        )
        notification_out = notification_crud.build_notification_out(notification)
        realtime_manager.send_to_user_sync(
            user_id,
            {"type": "notification.new", "notification": _model_dump(notification_out)},
        )
    except Exception:
        logger.exception("Failed to create or send notification")
