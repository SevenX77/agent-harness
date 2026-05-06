"""Studio-wide event broadcast and filesystem watching."""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path
from typing import Any

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from app.core import config
from app.services.skills import ensure_workspace_layout, skill_id_from_changed_path

StudioEvent = dict[str, str]


class EventBus:
    """Broadcast JSON events to all connected /ws/events clients."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[StudioEvent]] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self) -> asyncio.Queue[StudioEvent]:
        self._loop = asyncio.get_running_loop()
        queue: asyncio.Queue[StudioEvent] = asyncio.Queue()
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[StudioEvent]) -> None:
        self._subscribers.discard(queue)

    async def broadcast(self, event: StudioEvent) -> None:
        stale: list[asyncio.Queue[StudioEvent]] = []
        for queue in self._subscribers:
            try:
                queue.put_nowait(event)
            except RuntimeError:
                stale.append(queue)
        for queue in stale:
            self.unsubscribe(queue)

    def broadcast_from_thread(self, event: StudioEvent) -> None:
        if self._loop is None:
            return
        future = asyncio.run_coroutine_threadsafe(self.broadcast(event), self._loop)
        with contextlib.suppress(Exception):
            future.result(timeout=1)


class _SkillChangeHandler(FileSystemEventHandler):
    """watchdog handler that converts file changes into skill_changed events."""

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus

    def on_modified(self, event: FileSystemEvent) -> None:
        self._handle(event)

    def on_created(self, event: FileSystemEvent) -> None:
        self._handle(event)

    def on_moved(self, event: FileSystemEvent) -> None:
        self._handle(event)

    def _handle(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        path = Path(str(getattr(event, "dest_path", None) or event.src_path))
        if path.name.startswith("."):
            return
        skill_id = skill_id_from_changed_path(path)
        if skill_id is None:
            return
        self._bus.broadcast_from_thread({"type": "skill_changed", "skill_id": skill_id})


class FileWatcherManager:
    """Owns the watchdog observer lifecycle."""

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._observer: Any | None = None

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        if self._observer is not None:
            return
        ensure_workspace_layout()
        self._bus.set_loop(loop)
        observer = Observer()
        handler = _SkillChangeHandler(self._bus)
        for root in (config.SKILLS_DIR, config.default_workspace_skills_dir()):
            root.mkdir(parents=True, exist_ok=True)
            observer.schedule(handler, str(root), recursive=True)
        observer.daemon = True
        observer.start()
        self._observer = observer

    def stop(self) -> None:
        observer = self._observer
        if observer is None:
            return
        observer.stop()
        observer.join(timeout=2)
        self._observer = None

    def notify_path_changed(self, path: Path) -> None:
        skill_id = skill_id_from_changed_path(path)
        if skill_id is not None:
            self._bus.broadcast_from_thread({"type": "skill_changed", "skill_id": skill_id})


event_bus = EventBus()
file_watcher = FileWatcherManager(event_bus)
