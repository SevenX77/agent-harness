"""WebSocket channels for the Studio backend."""

from __future__ import annotations

from fastapi import APIRouter, Depends, WebSocket
from starlette.websockets import WebSocketDisconnect

from app.core.backends import get_eventbus
from app.core.ports.eventbus import EventBus
from app.services.event_bus import STUDIO_EVENTS_TOPIC
from app.services.run_manager import run_manager
from app.services.terminal_manager import terminal_manager

router = APIRouter(tags=["websockets"])


@router.websocket("/ws/runs/{run_id}")
async def run_events(websocket: WebSocket, run_id: str) -> None:
    await websocket.accept()
    queue = await run_manager.stream_run(run_id)
    while True:
        event = await queue.get()
        if event is None:
            await websocket.close()
            return
        await websocket.send_json(event)


@router.websocket("/ws/terminal/{term_id}")
async def terminal_stream(websocket: WebSocket, term_id: str) -> None:
    await terminal_manager.bridge(websocket, term_id)


@router.websocket("/ws/events")
async def studio_events(
    websocket: WebSocket,
    eventbus: EventBus = Depends(get_eventbus),
) -> None:
    await websocket.accept()
    try:
        async for event in eventbus.subscribe(STUDIO_EVENTS_TOPIC):
            await websocket.send_json(event)
    except WebSocketDisconnect:
        return
