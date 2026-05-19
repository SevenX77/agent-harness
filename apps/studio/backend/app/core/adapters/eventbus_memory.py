"""In-memory EventBus adapter for local Studio sessions."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any


class InMemoryEventBus:
    """Topic-based pub/sub backed by asyncio queues."""

    DEFAULT_TOPIC = "studio:events"

    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Remember the event loop used by thread callbacks."""
        self._loop = loop

    async def publish(self, topic: str, event: dict[str, Any]) -> None:
        """Publish one event to all current topic subscribers."""
        queues = tuple(self._subscribers.get(topic, set()))
        for queue in queues:
            await queue.put(event)

    def subscribe(self, topic: str) -> AsyncIterator[dict[str, Any]]:
        """Yield topic events until the consumer exits the iterator."""
        return self._subscribe(topic)

    async def _subscribe(self, topic: str) -> AsyncIterator[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subscribers.setdefault(topic, set()).add(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            subscribers = self._subscribers.get(topic)
            if subscribers is not None:
                subscribers.discard(queue)
                if not subscribers:
                    self._subscribers.pop(topic, None)

    def publish_from_thread(
        self,
        topic: str,
        event: dict[str, Any],
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        """Schedule publication from a non-async callback thread."""
        asyncio.run_coroutine_threadsafe(self.publish(topic, event), loop)

    async def broadcast(self, event: dict[str, Any]) -> None:
        """Publish one event to the default Studio event topic."""
        await self.publish(self.DEFAULT_TOPIC, event)

    def broadcast_from_thread(self, event: dict[str, Any]) -> None:
        """Publish one default-topic event from a watchdog thread."""
        if self._loop is None:
            return
        if self._loop.is_closed():
            return
        future = asyncio.run_coroutine_threadsafe(self.broadcast(event), self._loop)
        try:
            future.result(timeout=1)
        except Exception:
            return
