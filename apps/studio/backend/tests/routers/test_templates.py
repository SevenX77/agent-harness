from __future__ import annotations

import asyncio
from typing import Any

from app.routers import templates as templates_router
from app.services.event_bus import STUDIO_EVENTS_TOPIC, event_bus


class _DirectSubscriber:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    def __enter__(self) -> _DirectSubscriber:
        event_bus._subscribers.setdefault(STUDIO_EVENTS_TOPIC, set()).add(self.queue)
        return self

    def __exit__(self, *_exc: object) -> None:
        subscribers = event_bus._subscribers.get(STUDIO_EVENTS_TOPIC)
        if subscribers is not None:
            subscribers.discard(self.queue)
            if not subscribers:
                event_bus._subscribers.pop(STUDIO_EVENTS_TOPIC, None)


def test_get_templates_returns_builtin_projection_without_event() -> None:
    async def _get() -> list[str]:
        with _DirectSubscriber() as sub:
            templates = await templates_router.get_templates()
            assert sub.queue.empty()
            return [template.id for template in templates]

    template_ids = asyncio.run(_get())

    assert {"blank-agent", "blank-graph", "data-extractor", "chained-reasoning"} <= set(template_ids)
