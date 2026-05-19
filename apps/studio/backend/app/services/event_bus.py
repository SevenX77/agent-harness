"""Studio-wide event broadcast primitives."""

from __future__ import annotations

from typing import cast

from app.core.adapters.eventbus_memory import InMemoryEventBus
from app.core.backends import get_eventbus

StudioEvent = dict[str, str]
STUDIO_EVENTS_TOPIC = InMemoryEventBus.DEFAULT_TOPIC


event_bus = cast(InMemoryEventBus, get_eventbus())
