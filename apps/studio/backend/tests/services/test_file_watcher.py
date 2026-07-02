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


def test_is_within(tmp_path: Path) -> None:
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    assert _is_within(nested, tmp_path / "a")
    assert _is_within(tmp_path / "a", tmp_path / "a")
    assert not _is_within(tmp_path / "a", nested)
