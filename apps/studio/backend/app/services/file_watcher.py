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
# Upper bound for stop() waiting on the watcher thread. The stop events make the
# thread exit within one 50ms rust-notify step; the only non-responsive sections
# are bounded native watcher setup/teardown, which this comfortably outlasts.
_STOP_JOIN_TIMEOUT_SECONDS = 30.0


class _WatchTrigger:
    """`stop_event` handed to watchfiles' watch(): fires on service stop OR re-watch.

    watch() polls a single `is_set()` object from its native loop (~every 50ms
    step). Folding both signals into that one object means a blocked watch()
    always observes the thread's own stop event directly — stopping never
    depends on stop() still holding the current generation's re-watch reference
    (losing that reference once stranded a watcher no stop() could ever reach).
    """

    def __init__(self, stop: threading.Event, rewatch: threading.Event) -> None:
        self._stop = stop
        self._rewatch = rewatch

    def is_set(self) -> bool:
        return self._stop.is_set() or self._rewatch.is_set()


class FileWatcherService:
    """Owns the watchfiles thread lifecycle and skill change event conversion."""

    def __init__(self, bus: InMemoryEventBus) -> None:
        self._bus = bus
        self._thread: threading.Thread | None = None
        # Stop event of the CURRENT thread. One fresh event per start(), passed
        # into _run and never cleared: a thread that outlives a timed-out stop()
        # keeps its own event permanently set, so a later start() cannot revive
        # it (the old shared-and-cleared event did exactly that, leaving an
        # unstoppable watcher for the rest of the process).
        self._thread_stop: threading.Event | None = None
        self._echo: dict[Path, tuple[float, float | None]] = {}
        self._lock = threading.Lock()
        # Opened workspaces to watch on top of the static config roots. Each maps a
        # skill ROOT directory (the opened folder itself) -> its skill id, so the
        # watcher follows whatever the user opens, from any path — not only the
        # app's built-in skills dirs. Set by `register_workspace` (called when the
        # backend resolves a skill's directory in get_skill_detail).
        self._workspace_roots: dict[Path, str] = {}
        # Re-watch signal of the CURRENT watch() generation. Setting it breaks the
        # active watch so _run re-reads the (now larger) root set and re-watches.
        self._rewatch: threading.Event | None = None

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        if self._thread is not None:
            return
        self._bus.set_loop(loop)
        stop = threading.Event()
        thread = threading.Thread(
            target=self._run,
            args=(stop,),
            name="studio-file-watcher",
            daemon=True,
        )
        self._thread = thread
        self._thread_stop = stop
        thread.start()

    def stop(self) -> None:
        thread = self._thread
        stop = self._thread_stop
        self._thread = None
        self._thread_stop = None
        if stop is not None:
            # Breaks the blocking watch() too: the thread's _WatchTrigger polls
            # this event directly.
            stop.set()
        if thread is not None:
            # Wait until the thread actually exits. A daemon watcher that outlives
            # stop() keeps running rust/notify code into interpreter shutdown, which
            # intermittently SIGSEGVs the Linux CI runners under coverage (exit 139
            # after "N passed"). A single join(timeout=2) silently gave up whenever
            # the thread sat in a bounded non-stop-responsive native section, so
            # poll-join past it instead.
            deadline = time.monotonic() + _STOP_JOIN_TIMEOUT_SECONDS
            while thread.is_alive() and time.monotonic() < deadline:
                thread.join(timeout=0.5)
            if thread.is_alive():
                logger.warning(
                    "studio-file-watcher thread still alive after %.0fs stop() wait",
                    _STOP_JOIN_TIMEOUT_SECONDS,
                )
        with self._lock:
            # The service is a module singleton that outlives each app instance:
            # drop per-app state so stale workspace roots do not accumulate across
            # restarts (or across the test suite, where every generation re-watched
            # long-dead tmp directories).
            self._workspace_roots.clear()
            self._rewatch = None

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
            rewatch = self._rewatch
        if not static_covered and rewatch is not None:
            rewatch.set()

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

    def _run(self, stop: threading.Event) -> None:
        # Re-watch whenever the root set changes (a workspace was opened). Each
        # generation gets a fresh rewatch event; register_workspace() sets it to
        # break the blocking watch() so we recompute roots and re-watch. stop()
        # breaks the watch through `stop` itself (see _WatchTrigger).
        while not stop.is_set():
            for static in _watch_roots():
                try:
                    static.mkdir(parents=True, exist_ok=True)
                except OSError:
                    pass
            roots = self._snapshot_roots()
            if not roots:
                if stop.wait(1.0):
                    break
                continue
            rewatch = threading.Event()
            with self._lock:
                self._rewatch = rewatch
            if stop.is_set():
                break
            try:
                for changes in watch(
                    *[str(root) for root in roots],
                    stop_event=_WatchTrigger(stop, rewatch),
                    recursive=True,
                ):
                    # Also re-check between (and within) change batches: a batch
                    # yielded just before stop() must not keep the thread busy
                    # handling events while stop() waits on the join.
                    if stop.is_set():
                        break
                    for change, raw_path in changes:
                        if stop.is_set():
                            break
                        self._handle_path(change, Path(raw_path))
            except Exception:
                logger.exception("skill file watcher crashed")
                if stop.wait(1.0):
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
