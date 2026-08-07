"""WebSocket channels for the Studio backend."""

from __future__ import annotations

from fastapi import APIRouter, Depends, WebSocket
from starlette.websockets import WebSocketDisconnect

from app.core.backends import get_eventbus
from app.core.ports.eventbus import EventBus
from app.services.event_bus import STUDIO_EVENTS_TOPIC
from app.services.run_manager import run_manager

router = APIRouter(tags=["websockets"])


def _websocket_token_is_valid(websocket: WebSocket) -> bool:
    from app.main import _is_valid_token

    return _is_valid_token(websocket.query_params.get("token"))


async def _close_unauthorized(websocket: WebSocket) -> None:
    await websocket.accept()
    await websocket.close(code=4401, reason="Unauthorized")


@router.websocket("/ws/runs/{run_id}")
async def run_events(websocket: WebSocket, run_id: str) -> None:
    if not _websocket_token_is_valid(websocket):
        await _close_unauthorized(websocket)
        return
    await websocket.accept()
    queue = await run_manager.stream_run(run_id, cursor=websocket.query_params.get("cursor"))
    while True:
        event = await queue.get()
        if event is None:
            await websocket.close()
            return
        await websocket.send_json(event)



@router.websocket("/ws/events")
async def studio_events(
    websocket: WebSocket,
    eventbus: EventBus = Depends(get_eventbus),
) -> None:
    if not _websocket_token_is_valid(websocket):
        await _close_unauthorized(websocket)
        return
    await websocket.accept()
    try:
        async for event in eventbus.subscribe(STUDIO_EVENTS_TOPIC):
            await websocket.send_json(event)
    except WebSocketDisconnect:
        return
