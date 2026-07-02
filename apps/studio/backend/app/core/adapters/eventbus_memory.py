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
        """Publish one default-topic event from a watchdog thread.

        Fire-and-forget, like publish_from_thread: queue puts cannot meaningfully
        fail, and blocking on the result stalls the calling thread for the full
        timeout whenever the loop cannot run callbacks — e.g. while the lifespan
        shutdown blocks the loop inside file_watcher.stop(), where a pending
        change batch of N events became an N-second stall that outlived stop()'s
        join budget and leaked the watcher thread (CI exit-139 class).
        """
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        try:
            asyncio.run_coroutine_threadsafe(self.broadcast(event), loop)
        except RuntimeError:
            # The loop closed between the check and the call.
            return
