"""watchfiles-based skill directory watcher with API-write echo filtering."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import threading
import time
from pathlib import Path
from typing import Any

from watchfiles import Change, watch

from app.core import config
from app.core.adapters.eventbus_memory import InMemoryEventBus
from app.services.event_bus import event_bus

logger = logging.getLogger(__name__)
_ECHO_TTL_SECONDS = 2.0


class FileWatcherService:
    """Owns the watchfiles thread lifecycle and skill change event conversion."""

    def __init__(self, bus: InMemoryEventBus) -> None:
        self._bus = bus
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._echo: dict[Path, tuple[float, float | None]] = {}
        self._lock = threading.Lock()

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        if self._thread is not None:
            return
        self._bus.set_loop(loop)
        self._stop_event.clear()
        roots = tuple(_watch_roots())
        for root in roots:
            root.mkdir(parents=True, exist_ok=True)
        self._thread = threading.Thread(
            target=self._run,
            args=(roots,),
            name="studio-file-watcher",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2)
        self._thread = None

    def record_api_write(self, path: Path) -> None:
        resolved = path.resolve()
        with self._lock:
            self._echo[resolved] = (time.monotonic(), _safe_mtime(resolved))

    def notify_path_changed(self, path: Path) -> None:
        self._handle_path(Change.modified, path)

    def _run(self, roots: tuple[Path, ...]) -> None:
        try:
            for changes in watch(
                *[str(root) for root in roots],
                stop_event=self._stop_event,
                recursive=True,
            ):
                for change, raw_path in changes:
                    self._handle_path(change, Path(raw_path))
        except Exception:
            logger.exception("skill file watcher crashed")

    def _handle_path(self, change: Change, path: Path) -> None:
        if path.name.startswith(".") or path.is_dir():
            return
        resolved = path.resolve()
        if self._is_echo(resolved):
            return

        # Check for LLM config files
        from app.services.llm_paths import credentials_path, roles_path
        try:
            target_credentials = credentials_path().resolve()
            target_roles = roles_path().resolve()
        except Exception:
            target_credentials = None
            target_roles = None

        if target_credentials and resolved == target_credentials:
            self._bus.broadcast_from_thread({
                "type": "registry_changed",
                "change": change.name,
            })
            return
        if target_roles and resolved == target_roles:
            self._bus.broadcast_from_thread({
                "type": "roles_changed",
                "change": change.name,
            })
            return

        event = _skill_event_for_path(change, resolved)
        if event is not None:
            self._bus.broadcast_from_thread(event)

    def _is_echo(self, path: Path) -> bool:
        now = time.monotonic()
        mtime = _safe_mtime(path)
        with self._lock:
            stale = [
                saved
                for saved, (saved_at, _) in self._echo.items()
                if now - saved_at > _ECHO_TTL_SECONDS
            ]
            for saved in stale:
                self._echo.pop(saved, None)
            entry = self._echo.get(path)
            if entry is None:
                return False
            saved_at, saved_mtime = entry
            is_recent = now - saved_at <= _ECHO_TTL_SECONDS
            has_same_mtime = saved_mtime is None or saved_mtime == mtime
            if is_recent and has_same_mtime:
                self._echo.pop(path, None)
                return True
            return False


def record_api_write(path: Path) -> None:
    file_watcher.record_api_write(path)


def file_hash(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except FileNotFoundError:
        return None


def _skill_event_for_path(change: Change, path: Path) -> dict[str, Any] | None:
    located = _locate_skill_path(path)
    if located is None:
        return None
    skill_id, rel_path = located
    return {
        "type": "skill_changed",
        "skill_id": skill_id,
        "path": rel_path,
        "change": change.name,
        "hash": file_hash(path),
        "mtime": _safe_mtime(path),
    }


def _locate_skill_path(path: Path) -> tuple[str, str] | None:
    resolved = path.resolve()
    for root in _watch_roots():
        try:
            relative = resolved.relative_to(root.resolve())
        except ValueError:
            continue
        if len(relative.parts) < 2:
            return None
        return relative.parts[0], Path(*relative.parts[1:]).as_posix()
    return None


def _watch_roots() -> list[Path]:
    from app.services.llm_paths import credentials_path
    roots = [config.SKILLS_DIR, config.default_workspace_skills_dir(), config.DEFAULT_SKILLS_ROOT]
    try:
        llm_dir = credentials_path().parent
        if llm_dir not in roots:
            roots.append(llm_dir)
    except Exception:
        pass
    return roots


def _safe_mtime(path: Path) -> float | None:
    try:
        return path.stat().st_mtime
    except FileNotFoundError:
        return None


file_watcher = FileWatcherService(event_bus)
