"""Studio-wide event broadcast and filesystem watching."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, cast

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from app.core import config
from app.core.adapters.eventbus_memory import InMemoryEventBus
from app.core.backends import get_eventbus
from app.services.skills import ensure_workspace_layout, skill_id_from_changed_path

StudioEvent = dict[str, str]
STUDIO_EVENTS_TOPIC = InMemoryEventBus.DEFAULT_TOPIC


def _changed_file(path: Path, skill_id: str) -> str:
    parts = path.parts
    try:
        index = parts.index(skill_id)
    except ValueError:
        return path.name
    relative_parts = parts[index + 1 :]
    return "/".join(relative_parts) if relative_parts else path.name


class _SkillChangeHandler(FileSystemEventHandler):
    """watchdog handler that converts file changes into skill_changed events."""

    def __init__(self, bus: InMemoryEventBus) -> None:
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
        self._bus.broadcast_from_thread({
            "type": "skill_changed",
            "skill_id": skill_id,
            "file": _changed_file(path, skill_id),
        })


class FileWatcherManager:
    """Owns the watchdog observer lifecycle."""

    def __init__(self, bus: InMemoryEventBus) -> None:
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
            self._bus.broadcast_from_thread({
                "type": "skill_changed",
                "skill_id": skill_id,
                "file": _changed_file(path, skill_id),
            })


event_bus = cast(InMemoryEventBus, get_eventbus())
file_watcher = FileWatcherManager(event_bus)
