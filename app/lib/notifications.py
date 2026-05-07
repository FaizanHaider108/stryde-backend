import logging
import urllib.request
import json
from typing import Optional
import uuid

from ..crud import notification as notification_crud
from ..lib.realtime import realtime_manager
from ..models import NotificationType

logger = logging.getLogger(__name__)

# Maps each notification type to the user's pref key that controls it
_TYPE_TO_PREF: dict[NotificationType, str] = {
    NotificationType.post_like: "activityFeedback",
    NotificationType.post_comment: "activityFeedback",
    NotificationType.comment_like: "activityFeedback",
    NotificationType.club_invitation: "communityUpdates",
    NotificationType.event_invitation: "raceAlerts",
    NotificationType.follow: "communityUpdates",
}

# Human-readable titles/bodies for each notification type
_PUSH_COPY: dict[NotificationType, tuple[str, str]] = {
    NotificationType.post_like: ("Someone liked your post", "Tap to view your post"),
    NotificationType.post_comment: ("New comment on your post", "Someone commented on your post"),
    NotificationType.comment_like: ("Someone liked your comment", "Tap to see the comment"),
    NotificationType.club_invitation: ("Club invitation", "You've been invited to join a club"),
    NotificationType.event_invitation: ("Event invitation", "You've been invited to an event"),
    NotificationType.follow: ("New follower", "Someone started following you"),
}


def _send_expo_push(expo_push_token: str, title: str, body: str) -> None:
    """Fire-and-forget Expo push notification via their HTTP API."""
    try:
        message = {
            "to": expo_push_token,
            "sound": "default",
            "title": title,
            "body": body,
        }
        data = json.dumps(message).encode("utf-8")
        req = urllib.request.Request(
            "https://exp.host/--/api/v2/push/send",
            data=data,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Accept-Encoding": "gzip, deflate",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            resp.read()
    except Exception:
        logger.warning("Failed to send Expo push notification", exc_info=True)


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

        # Send OS-level push notification if user has a token and prefs allow it
        try:
            from ..models.user import User
            user = db.query(User).filter(User.uid == user_id).first()
            if user and user.expo_push_token:
                prefs = user.notification_prefs or {}
                # Check master switch first
                if prefs.get("generalNotifications", True):
                    pref_key = _TYPE_TO_PREF.get(notif_type)
                    if pref_key is None or prefs.get(pref_key, True):
                        title, body = _PUSH_COPY.get(notif_type, ("New notification", "You have a new notification"))
                        _send_expo_push(user.expo_push_token, title, body)
        except Exception:
            logger.warning("Failed to look up user for push notification", exc_info=True)

    except Exception:
        logger.exception("Failed to create or send notification")
