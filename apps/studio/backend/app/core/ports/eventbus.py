"""Event bus port for Studio backend notifications."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol


class EventBus(Protocol):
    """Publish and subscribe to Studio events by topic."""

    async def publish(self, topic: str, event: dict[str, Any]) -> None:
        """Publish one event payload to all subscribers of a topic."""
        ...

    def subscribe(self, topic: str) -> AsyncIterator[dict[str, Any]]:
        """Yield events published to a topic until the consumer disconnects."""
        ...
