"""WebSocket channel placeholders for the Studio backend."""

from __future__ import annotations

from fastapi import APIRouter, WebSocket

router = APIRouter(tags=["websockets"])


@router.websocket("/ws/runs/{run_id}")
async def run_events(websocket: WebSocket, run_id: str) -> None:
    await websocket.accept()
    await websocket.send_json({"type": "not_implemented", "run_id": run_id})
    await websocket.close(code=1011)


@router.websocket("/ws/terminal/{term_id}")
async def terminal_stream(websocket: WebSocket, term_id: str) -> None:
    await websocket.accept()
    await websocket.send_json({"type": "not_implemented", "term_id": term_id})
    await websocket.close(code=1011)


@router.websocket("/ws/events")
async def studio_events(websocket: WebSocket) -> None:
    await websocket.accept()
    await websocket.send_json({"type": "not_implemented"})
    await websocket.close(code=1011)
