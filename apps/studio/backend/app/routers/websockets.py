"""WebSocket channels for the Studio backend."""

from __future__ import annotations

from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketDisconnect

from app.services.event_bus import event_bus
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
async def studio_events(websocket: WebSocket) -> None:
    await websocket.accept()
    queue = event_bus.subscribe()
    try:
        while True:
            await websocket.send_json(await queue.get())
    except WebSocketDisconnect:
        return
    finally:
        event_bus.unsubscribe(queue)
