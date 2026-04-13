import asyncio
import uuid
from typing import Any

import anyio
from fastapi import WebSocket


class RealtimeManager:
    def __init__(self) -> None:
        self._club_connections: dict[uuid.UUID, set[WebSocket]] = {}
        self._user_connections: dict[uuid.UUID, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect_club(self, club_id: uuid.UUID, websocket: WebSocket) -> None:
        async with self._lock:
            self._club_connections.setdefault(club_id, set()).add(websocket)

    async def disconnect_club(self, club_id: uuid.UUID, websocket: WebSocket) -> None:
        async with self._lock:
            connections = self._club_connections.get(club_id)
            if not connections:
                return
            connections.discard(websocket)
            if not connections:
                self._club_connections.pop(club_id, None)

    async def connect_user(self, user_id: uuid.UUID, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._user_connections.setdefault(user_id, set()).add(websocket)

    async def disconnect_user(self, user_id: uuid.UUID, websocket: WebSocket) -> None:
        async with self._lock:
            connections = self._user_connections.get(user_id)
            if not connections:
                return
            connections.discard(websocket)
            if not connections:
                self._user_connections.pop(user_id, None)

    async def broadcast_to_club(self, club_id: uuid.UUID, payload: Any) -> None:
        async with self._lock:
            sockets = list(self._club_connections.get(club_id, set()))

        for socket in sockets:
            try:
                await socket.send_json(payload)
            except Exception:
                await self.disconnect_club(club_id, socket)

    async def send_to_user(self, user_id: uuid.UUID, payload: Any) -> None:
        async with self._lock:
            sockets = list(self._user_connections.get(user_id, set()))

        for socket in sockets:
            try:
                await socket.send_json(payload)
            except Exception:
                await self.disconnect_user(user_id, socket)

    def broadcast_to_club_sync(self, club_id: uuid.UUID, payload: Any) -> None:
        try:
            anyio.from_thread.run(self.broadcast_to_club, club_id, payload)
        except RuntimeError:
            asyncio.run(self.broadcast_to_club(club_id, payload))

    def send_to_user_sync(self, user_id: uuid.UUID, payload: Any) -> None:
        try:
            anyio.from_thread.run(self.send_to_user, user_id, payload)
        except RuntimeError:
            asyncio.run(self.send_to_user(user_id, payload))


realtime_manager = RealtimeManager()
