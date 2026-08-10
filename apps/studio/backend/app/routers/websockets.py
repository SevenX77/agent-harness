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


@router.websocket("/ws/skills/{skill_id}/runs/{run_id}")
async def run_events(websocket: WebSocket, skill_id: str, run_id: str) -> None:
    """Stream one run's events.

    The run's owning skill is part of the address because a finished run is
    replayed from its own directory on disk, and that directory is only
    addressable as (skill, run).
    """
    if not _websocket_token_is_valid(websocket):
        await _close_unauthorized(websocket)
        return
    await websocket.accept()
    queue = await run_manager.stream_run(skill_id, run_id, cursor=websocket.query_params.get("cursor"))
    while True:
        event = await queue.get()
        if event is None:
            await websocket.close()
            return
        await websocket.send_json(event)



@router.websocket("/ws/skills/{skill_id}/runs/{run_id}/deltas")
async def run_deltas(websocket: WebSocket, skill_id: str, run_id: str) -> None:
    """Stream one run's output as it arrives.

    A separate socket from the run's events, not a second kind of message on
    that one, because the two have opposite guarantees. The event socket
    promises a contiguous numbered sequence and replays from a cursor after a
    reconnect; this one promises nothing of the sort — it may merge adjacent
    pieces and drop them under backpressure, and it has nothing to replay.
    Putting both on one socket would mean either giving deltas numbers they
    must not have, or breaking the contiguity the events depend on.

    There is no cursor for the same reason: a reader who dropped off has not
    missed anything recoverable. What the pieces spelled out arrives whole on
    the step's closing event, over the other socket.
    """
    del skill_id  # addressed like its sibling; only the run identifies the stream
    if not _websocket_token_is_valid(websocket):
        await _close_unauthorized(websocket)
        return
    await websocket.accept()
    stream = run_manager.stream_run_deltas(run_id)
    try:
        async for frame in stream:
            await websocket.send_json(frame.model_dump(mode="json"))
    except WebSocketDisconnect:
        return
    finally:
        run_manager.stop_streaming_deltas(run_id, stream)
    await websocket.close()


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
