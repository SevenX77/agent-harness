"""Unit tests for FileWatcherService dynamic-workspace watching and stop().

Covers the deterministic mapping/root-set logic (which skill a changed path
belongs to, and which roots get watched) plus the stop() lifecycle contract.
The real watchfiles watch loop is timing/OS dependent and is not exercised here.
"""

from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path
from typing import Any

import pytest
from app.services.event_bus import event_bus
from app.services.file_watcher import FileWatcherService, _is_within
from watchfiles import Change


def _service() -> FileWatcherService:
    # The pure mapping methods under test never touch the bus.
    return FileWatcherService(event_bus)


def test_registered_workspace_root_maps_changes_to_its_skill_id(tmp_path: Path) -> None:
    root = tmp_path / "story-deconstruction-v3"
    seg = root / "phases" / "segmentation"
    seg.mkdir(parents=True)
    changed = seg / "SKILL.md"
    changed.write_text("body", encoding="utf-8")

    svc = _service()
    svc.register_workspace(root, "story-deconstruction-v3")

    event = svc._skill_event_for_path(Change.modified, changed)
    assert event is not None
    assert event["type"] == "skill_changed"
    assert event["skill_id"] == "story-deconstruction-v3"
    assert event["path"] == "phases/segmentation/SKILL.md"
    assert event["change"] == "modified"


def test_run_products_under_workspace_are_not_skill_events(tmp_path: Path) -> None:
    """`.workspace/runs/**` are run PRODUCTS, not skill content: on Windows the
    spawned run worker holds checkpoints.db locked, and every trace.jsonl append
    used to storm the watcher. Any hidden path component ends the mapping."""
    root = tmp_path / "skillA"
    run_dir = root / ".workspace" / "runs" / "r1"
    run_dir.mkdir(parents=True)
    locked = run_dir / "checkpoints.db"
    locked.write_bytes(b"sqlite")

    svc = _service()
    svc.register_workspace(root, "skillA")

    assert svc._skill_event_for_path(Change.modified, locked) is None


def test_hidden_component_under_static_root_is_not_skill_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core import config
    from app.services.file_watcher import _locate_skill_path

    static_root = tmp_path / "skills"
    hidden = static_root / "skillB" / ".workspace" / "runs" / "r2" / "trace.jsonl"
    hidden.parent.mkdir(parents=True)
    hidden.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(config, "DEFAULT_SKILLS_ROOT", static_root)

    assert _locate_skill_path(hidden) is None


def test_locked_file_mtime_and_hash_degrade_to_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A file held with an exclusive lock (Windows sharing violation) raises
    PermissionError from stat()/read_bytes(); both helpers must degrade to None
    instead of blowing up the watch generation."""
    from app.services.file_watcher import _safe_mtime, file_hash

    target = tmp_path / "GRAPH.md"
    target.write_text("x", encoding="utf-8")

    def _denied_stat(self: Path, *args: Any, **kwargs: Any) -> Any:
        raise PermissionError(13, "locked", str(self))

    def _denied_read(self: Path) -> bytes:
        raise PermissionError(13, "locked", str(self))

    monkeypatch.setattr(Path, "stat", _denied_stat)
    monkeypatch.setattr(Path, "read_bytes", _denied_read)

    assert _safe_mtime(target) is None
    assert file_hash(target) is None


def test_handle_path_survives_a_locked_visible_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One unreadable file must not kill the whole change batch: _handle_path
    still emits the event (hash/mtime unknown) instead of raising."""
    root = tmp_path / "skillA"
    (root / "phases" / "p").mkdir(parents=True)
    target = root / "phases" / "p" / "SKILL.md"
    target.write_text("body", encoding="utf-8")

    svc = _service()
    svc.register_workspace(root, "skillA")

    def _denied_stat(self: Path, *args: Any, **kwargs: Any) -> Any:
        raise PermissionError(13, "locked", str(self))

    def _denied_read(self: Path) -> bytes:
        raise PermissionError(13, "locked", str(self))

    monkeypatch.setattr(Path, "stat", _denied_stat)
    monkeypatch.setattr(Path, "read_bytes", _denied_read)

    broadcasts: list[dict[str, Any]] = []
    monkeypatch.setattr(
        svc._bus, "broadcast_from_thread", lambda event: broadcasts.append(event)
    )

    svc._handle_path(Change.modified, target)

    assert len(broadcasts) == 1
    assert broadcasts[0]["type"] == "skill_changed"
    assert broadcasts[0]["hash"] is None
    assert broadcasts[0]["mtime"] is None


def test_deleted_file_under_workspace_still_emits_with_null_hash(tmp_path: Path) -> None:
    root = tmp_path / "skillA"
    (root / "phases" / "p").mkdir(parents=True)
    gone = root / "phases" / "p" / "LOGIC.md"  # never created -> "deleted"

    svc = _service()
    svc.register_workspace(root, "skillA")

    event = svc._skill_event_for_path(Change.deleted, gone)
    assert event is not None
    assert event["skill_id"] == "skillA"
    assert event["path"] == "phases/p/LOGIC.md"
    assert event["change"] == "deleted"
    assert event["hash"] is None


def test_paths_outside_any_watched_root_are_ignored(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    svc = _service()
    svc.register_workspace(ws, "ws")
    # A path under no registered/static root → no event.
    assert svc._skill_event_for_path(Change.modified, tmp_path / "unrelated" / "x.md") is None


def test_static_parent_of_skills_root_behaviour_unchanged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    static = tmp_path / "static-skills"
    skill_phase = static / "myskill" / "phases" / "x"
    skill_phase.mkdir(parents=True)
    changed = skill_phase / "SKILL.md"
    changed.write_text("y", encoding="utf-8")
    monkeypatch.setattr("app.services.file_watcher._watch_roots", lambda: [static])

    svc = _service()
    event = svc._skill_event_for_path(Change.modified, changed)
    assert event is not None
    # Static roots CONTAIN skill folders: skill id is the first path segment.
    assert event["skill_id"] == "myskill"
    assert event["path"] == "phases/x/SKILL.md"


def test_snapshot_roots_includes_external_workspace_and_skips_static_covered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    static = tmp_path / "static"
    inside = static / "myskill"
    inside.mkdir(parents=True)
    outside = tmp_path / "elsewhere" / "opened-ws"
    outside.mkdir(parents=True)
    monkeypatch.setattr("app.services.file_watcher._watch_roots", lambda: [static])

    svc = _service()
    svc.register_workspace(inside, "myskill")
    svc.register_workspace(outside, "opened-ws")

    roots = svc._snapshot_roots()
    assert static.resolve() in roots
    assert outside.resolve() in roots
    # Already covered by the static watch → not watched again.
    assert inside.resolve() not in roots


def test_register_workspace_is_idempotent(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    svc = _service()
    svc.register_workspace(root, "ws")
    svc.register_workspace(root, "ws")
    assert svc._workspace_roots == {root.resolve(): "ws"}


def test_register_workspace_ignores_missing_dir(tmp_path: Path) -> None:
    svc = _service()
    svc.register_workspace(tmp_path / "does-not-exist", "ghost")
    assert svc._workspace_roots == {}


def test_api_write_echo_defaults_to_current_mtime(tmp_path: Path) -> None:
    changed = tmp_path / "skill" / ".workspace" / "runtime_config.json"
    changed.parent.mkdir(parents=True)
    changed.write_text("before", encoding="utf-8")

    svc = _service()
    svc.record_api_write(changed)

    assert svc._is_echo(changed.resolve()) is True
    assert svc._is_echo(changed.resolve()) is False


def test_api_write_intent_can_suppress_next_mtime_change(tmp_path: Path) -> None:
    changed = tmp_path / "skill" / ".workspace" / "runtime_config.json"
    changed.parent.mkdir(parents=True)
    changed.write_text("before", encoding="utf-8")

    svc = _service()
    svc.record_api_write(changed, match_current_mtime=False)
    changed.write_text("after", encoding="utf-8")

    assert svc._is_echo(changed.resolve()) is True
    assert svc._is_echo(changed.resolve()) is False


def test_stop_clears_registered_workspace_roots(tmp_path: Path) -> None:
    """stop() must reset the workspace-root registry.

    `file_watcher` is a module singleton that outlives each app instance. Every
    `get_skill_detail` registers that app's (in tests: that test's tmp) skill root,
    so without cleanup the root set grows for the rest of the process lifetime and
    every new watch generation re-scans stale directories.
    """
    root = tmp_path / "ws"
    root.mkdir()
    svc = _service()
    svc.register_workspace(root, "ws")

    svc.stop()

    assert svc._workspace_roots == {}


def test_stop_does_not_return_while_watcher_thread_is_alive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """stop() must outlast a transiently unresponsive watch backend.

    The rust notify backend has bounded sections (recursive watcher setup/teardown)
    that cannot observe the stop event. A join that silently gives up after 2s leaks
    the daemon thread into interpreter/coverage shutdown, where it intermittently
    SIGSEGVs the Linux CI runners (exit 139 after "N passed"). Simulate a 3s
    unresponsive window and require stop() to wait it out.
    """
    static = tmp_path / "static"
    static.mkdir()
    monkeypatch.setattr("app.services.file_watcher._watch_roots", lambda: [static])

    entered = threading.Event()

    def fake_watch(*paths: str, stop_event: Any = None, **kwargs: Any) -> Any:
        entered.set()
        time.sleep(3.0)  # bounded native window that cannot see stop_event
        while stop_event is not None and not stop_event.is_set():
            time.sleep(0.01)
        return
        yield  # pragma: no cover - makes this function a generator

    monkeypatch.setattr("app.services.file_watcher.watch", fake_watch)

    svc = _service()
    loop = asyncio.new_event_loop()
    try:
        svc.start(loop)
        thread = svc._thread
        assert thread is not None
        assert entered.wait(timeout=5)

        svc.stop()

        assert not thread.is_alive()
    finally:
        svc.stop()
        loop.close()


def test_stop_returns_promptly_while_a_change_batch_is_draining(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """stop() must not wait out per-event broadcast timeouts (CI run 28568767879).

    stop() runs synchronously inside the async lifespan shutdown, so the event
    loop cannot execute the coroutines the watcher thread schedules while it
    drains its current change batch. A broadcast path that BLOCKS on each
    event's result therefore stalls its full timeout per pending change — a
    file-storm batch (e.g. a run + git auto-commit in a watched tmp root) held
    stop() past its 30s join budget, orphaning the thread. Simulate the
    can't-run-callbacks loop with a never-started loop and require stop() to
    return promptly with the thread dead.
    """
    static = tmp_path / "static"
    static.mkdir()
    ws = tmp_path / "opened-ws"
    ws.mkdir()
    monkeypatch.setattr("app.services.file_watcher._watch_roots", lambda: [static])

    # 10 pending changes in one batch: 10s under the old 1s-per-event drain.
    batch = [(Change.deleted, str(ws / f"file-{i}.md")) for i in range(10)]
    proceed = threading.Event()

    def fake_watch(*paths: str, stop_event: Any = None, **kwargs: Any) -> Any:
        proceed.wait(5)
        yield batch
        while stop_event is not None and not stop_event.is_set():
            time.sleep(0.01)

    monkeypatch.setattr("app.services.file_watcher.watch", fake_watch)

    svc = _service()
    svc.register_workspace(ws, "opened-ws")
    loop = asyncio.new_event_loop()  # never run: run_coroutine_threadsafe futures never complete
    try:
        svc.start(loop)
        thread = svc._thread
        assert thread is not None
        proceed.set()
        time.sleep(0.2)  # let the thread pick up the batch and start draining

        started = time.monotonic()
        svc.stop()
        elapsed = time.monotonic() - started

        assert not thread.is_alive()
        assert elapsed < 3.0, f"stop() blocked {elapsed:.1f}s draining pending change events"
    finally:
        svc.stop()
        loop.close()


def test_thread_surviving_a_timed_out_stop_cannot_be_revived_by_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A watcher thread orphaned by a timed-out stop() must stay condemned.

    In CI run 28568767879 the first timed-out stop() orphaned the thread, and
    the NEXT app start() cleared the shared stop event — reviving the orphan,
    whose per-generation watch break event reference was then lost, leaving a
    thread nothing could ever stop (213 teardown errors, then SIGSEGV at
    interpreter shutdown). Once stop() has been called, that thread must exit
    as soon as it becomes responsive again, restarts notwithstanding.
    """
    static = tmp_path / "static"
    static.mkdir()
    monkeypatch.setattr("app.services.file_watcher._watch_roots", lambda: [static])
    monkeypatch.setattr("app.services.file_watcher._STOP_JOIN_TIMEOUT_SECONDS", 0.2)

    entered = threading.Event()
    release = threading.Event()

    def fake_watch(*paths: str, stop_event: Any = None, **kwargs: Any) -> Any:
        entered.set()
        release.wait(10)  # bounded native window that cannot see stop_event
        while stop_event is not None and not stop_event.is_set():
            time.sleep(0.01)
        return
        yield  # pragma: no cover - makes this function a generator

    monkeypatch.setattr("app.services.file_watcher.watch", fake_watch)

    svc = _service()
    loop = asyncio.new_event_loop()
    try:
        svc.start(loop)
        first = svc._thread
        assert first is not None
        assert entered.wait(timeout=5)
        svc.stop()  # times out (0.2s < native window) and orphans the thread
        assert first.is_alive()

        svc.start(loop)
        second = svc._thread
        assert second is not None and second is not first

        release.set()  # native window ends; the orphan can observe events again
        first.join(3)
        assert not first.is_alive(), "orphaned watcher thread was revived by restart"
    finally:
        release.set()
        svc.stop()
        loop.close()


def test_is_within(tmp_path: Path) -> None:
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    assert _is_within(nested, tmp_path / "a")
    assert _is_within(tmp_path / "a", tmp_path / "a")
    assert not _is_within(tmp_path / "a", nested)
