"""
WebSocket endpoint -- real-time document processing progress broadcasts.

Clients connect to ``/ws/progress`` and receive JSON messages for
document status changes.  Authentication is handled via the first
WebSocket message or (development only) a query parameter.
"""

from __future__ import annotations

import asyncio
import json
from typing import Set

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.api.deps.auth import verify_token
from app.config.settings import settings
from app.shared.logging import logger

router = APIRouter()

_connections: Set[WebSocket] = set()
_conn_lock = asyncio.Lock()
_MAX_WS_CONNECTIONS = 200
_HEARTBEAT_INTERVAL = 30


@router.websocket("/ws/progress")
async def doc_progress(
    ws: WebSocket,
    token: str = Query(default=None),
):
    """WebSocket endpoint for real-time document processing updates.

    Authentication flow:
    1. Server accepts the WebSocket upgrade.
    2. Client sends ``{"type": "auth", "token": "<jwt>"}`` as the first
       message within 5 seconds.
    3. On success, the connection is registered and kept alive with
       periodic heartbeats.
    """
    await ws.accept()

    authenticated = False
    auth_user_id = "anonymous"

    if settings.APP_ENV == "development" and token:
        payload = verify_token(token)
        if payload:
            authenticated = True
            auth_user_id = payload.get("sub", "anonymous")
    else:
        try:
            first_msg = await asyncio.wait_for(ws.receive_text(), timeout=5.0)
            msg = json.loads(first_msg)
            if isinstance(msg, dict) and msg.get("type") == "auth":
                jwt_token = msg.get("token")
                if jwt_token:
                    payload = verify_token(jwt_token)
                    if payload:
                        authenticated = True
                        auth_user_id = payload.get("sub", "anonymous")
        except (asyncio.TimeoutError, json.JSONDecodeError):
            pass

    if not authenticated and settings.APP_ENV != "development":
        await ws.close(code=1008, reason="Authentication failed")
        return

    async with _conn_lock:
        if len(_connections) >= _MAX_WS_CONNECTIONS:
            await ws.close(code=1013, reason="Server at capacity")
            return
        _connections.add(ws)

    logger.info(
        "WebSocket connected: user={} conns={}",
        auth_user_id,
        len(_connections),
    )

    try:
        while True:
            try:
                data = await asyncio.wait_for(
                    ws.receive_text(), timeout=_HEARTBEAT_INTERVAL
                )
                try:
                    msg = json.loads(data)
                    if isinstance(msg, dict) and msg.get("type") == "ping":
                        await ws.send_json({"type": "pong"})
                except (json.JSONDecodeError, ValueError):
                    pass
            except asyncio.TimeoutError:
                await ws.send_json({"type": "ping"})
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning("WebSocket error: {}", e)
    finally:
        async with _conn_lock:
            _connections.discard(ws)
        logger.info(
            "WebSocket disconnected: user={} conns={}",
            auth_user_id,
            len(_connections),
        )


async def broadcast_progress(data: dict) -> None:
    """Broadcast a progress event to all connected WebSocket clients.

    Args:
        data: A JSON-serialisable dict (e.g. ``{"type": "doc_status",
            "doc_id": "...", "status": "done"}``).
    """
    dead: list[WebSocket] = []
    async with _conn_lock:
        conns = list(_connections)

    for ws in conns:
        try:
            await ws.send_json(data)
        except Exception:
            dead.append(ws)

    if dead:
        async with _conn_lock:
            for ws in dead:
                _connections.discard(ws)
