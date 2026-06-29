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
        # Opened workspaces to watch on top of the static config roots. Each maps a
        # skill ROOT directory (the opened folder itself) -> its skill id, so the
        # watcher follows whatever the user opens, from any path — not only the
        # app's built-in skills dirs. Set by `register_workspace` (called when the
        # backend resolves a skill's directory in get_skill_detail).
        self._workspace_roots: dict[Path, str] = {}
        # The stop_event of the CURRENT watch() generation. Setting it breaks the
        # active watch so _run re-reads the (now larger) root set and re-watches.
        self._watch_stop: threading.Event | None = None

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        if self._thread is not None:
            return
        self._bus.set_loop(loop)
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="studio-file-watcher",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        with self._lock:
            watch_stop = self._watch_stop
        if watch_stop is not None:
            # Break the blocking watch() so the thread can observe _stop_event.
            watch_stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2)
        self._thread = None

    def register_workspace(self, root: Path, skill_id: str) -> None:
        """Watch an opened workspace's skill ROOT directory (idempotent).

        The opened folder IS the skill root, so changes under it map to `skill_id`
        with paths relative to it. A root already covered by a static config root
        is not added again (the static watch already sees it). Adding a genuinely
        new root breaks the current watch so it is picked up immediately.
        """
        try:
            resolved = root.resolve()
        except OSError:
            return
        if not resolved.is_dir():
            return
        static_covered = any(_is_within(resolved, static) for static in _watch_roots())
        with self._lock:
            if self._workspace_roots.get(resolved) == skill_id:
                return
            self._workspace_roots[resolved] = skill_id
            watch_stop = self._watch_stop
        if not static_covered and watch_stop is not None:
            watch_stop.set()

    def _snapshot_roots(self) -> list[Path]:
        """Existing directories to watch: static config roots + opened workspace
        roots that are not already inside a static root, de-duplicated."""
        with self._lock:
            registered = list(self._workspace_roots.keys())
        seen: set[Path] = set()
        roots: list[Path] = []
        for candidate in [*_watch_roots(), *registered]:
            try:
                resolved = candidate.resolve()
            except OSError:
                continue
            if resolved in seen or not resolved.is_dir():
                continue
            # Skip a workspace root already covered by a static root we will watch.
            if any(other != resolved and _is_within(resolved, other) for other in seen):
                continue
            seen.add(resolved)
            roots.append(resolved)
        return roots

    def record_api_write(self, path: Path) -> None:
        resolved = path.resolve()
        with self._lock:
            self._echo[resolved] = (time.monotonic(), _safe_mtime(resolved))

    def notify_path_changed(self, path: Path) -> None:
        self._handle_path(Change.modified, path)

    def _run(self) -> None:
        # Re-watch whenever the root set changes (a workspace was opened). Each
        # generation gets a fresh stop_event; register_workspace()/stop() set it to
        # break the blocking watch() so we recompute roots and re-watch.
        while not self._stop_event.is_set():
            for static in _watch_roots():
                try:
                    static.mkdir(parents=True, exist_ok=True)
                except OSError:
                    pass
            roots = self._snapshot_roots()
            if not roots:
                if self._stop_event.wait(1.0):
                    break
                continue
            watch_stop = threading.Event()
            with self._lock:
                self._watch_stop = watch_stop
            if self._stop_event.is_set():
                break
            try:
                for changes in watch(
                    *[str(root) for root in roots],
                    stop_event=watch_stop,
                    recursive=True,
                ):
                    for change, raw_path in changes:
                        self._handle_path(change, Path(raw_path))
            except Exception:
                logger.exception("skill file watcher crashed")
                if self._stop_event.wait(1.0):
                    break

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

        event = self._skill_event_for_path(change, resolved)
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

    def _skill_event_for_path(self, change: Change, path: Path) -> dict[str, Any] | None:
        # An opened workspace root IS the skill root, so it takes precedence over
        # the static parent-of-skills roots.
        located = self._locate_workspace_skill(path) or _locate_skill_path(path)
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

    def _locate_workspace_skill(self, path: Path) -> tuple[str, str] | None:
        try:
            resolved = path.resolve()
        except OSError:
            return None
        with self._lock:
            registered = list(self._workspace_roots.items())
        for root, skill_id in registered:
            try:
                relative = resolved.relative_to(root)
            except ValueError:
                continue
            if not relative.parts:
                continue
            return skill_id, relative.as_posix()
        return None


def record_api_write(path: Path) -> None:
    file_watcher.record_api_write(path)


def register_workspace(root: Path, skill_id: str) -> None:
    """Module entry point: watch an opened workspace's skill root (idempotent)."""
    file_watcher.register_workspace(root, skill_id)


def file_hash(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except FileNotFoundError:
        return None


def _is_within(child: Path, ancestor: Path) -> bool:
    """True when `child` is `ancestor` or sits inside it (both resolved)."""
    try:
        child.resolve().relative_to(ancestor.resolve())
        return True
    except (OSError, ValueError):
        return False


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
