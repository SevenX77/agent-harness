"""F5 safe-write (model B): can_use_tool routes Write/Edit to patch_proposed and
holds Bash for approval. Verifies the diff payload + the apply-then-review/allow
vs hold/deny decisions without spawning a real SDK client."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from app.models.copilot import (
    CopilotEventBashApprovalRequired,
    CopilotEventPatchProposed,
)
from app.services import copilot
from claude_agent_sdk import (
    PermissionResultAllow,
    PermissionResultDeny,
    ToolPermissionContext,
)


def _drain(queue: asyncio.Queue[object]) -> list[object]:
    items: list[object] = []
    while not queue.empty():
        items.append(queue.get_nowait())
    return items


def _register_sink(skill_id: str, workspace: Path) -> asyncio.Queue[object]:
    queue: asyncio.Queue[object] = asyncio.Queue()
    copilot._safe_write_sinks[skill_id] = copilot._SafeWriteSink(
        queue=queue, workspace_root=workspace
    )
    return queue


@pytest.fixture(autouse=True)
def _clear_sinks():
    copilot._safe_write_sinks.clear()
    yield
    copilot._safe_write_sinks.clear()


def test_build_options_safe_write_routes_writes_through_callback() -> None:
    async def cb(name, tool_input, ctx):  # noqa: ANN001
        return PermissionResultAllow()

    opts = copilot.build_options("https://x", "key", "/ws", can_use_tool=cb)
    # Only Read pre-allowed so Write/Edit/Bash reach can_use_tool; default mode.
    assert opts.allowed_tools == ["Read"]
    assert opts.permission_mode == "default"
    assert opts.can_use_tool is cb


def test_build_options_probe_path_keeps_accept_edits() -> None:
    opts = copilot.build_options("https://x", "key", "/ws")
    assert opts.permission_mode == "acceptEdits"
    assert "Edit" in (opts.allowed_tools or [])
    assert opts.can_use_tool is None


def test_edit_emits_patch_proposed_and_allows(tmp_path: Path) -> None:
    (tmp_path / "GRAPH.md").write_text("alpha\noriginal line\n", encoding="utf-8")
    queue = _register_sink("skill-1", tmp_path)
    cb = copilot._make_safe_write_can_use_tool("skill-1")

    result = asyncio.run(
        cb(
            "Edit",
            {
                "file_path": str(tmp_path / "GRAPH.md"),
                "old_string": "original line",
                "new_string": "EDITED",
                "replace_all": False,
            },
            ToolPermissionContext(tool_use_id="tu-1"),
        )
    )

    assert isinstance(result, PermissionResultAllow)
    events = _drain(queue)
    assert len(events) == 1
    patch = events[0]
    assert isinstance(patch, CopilotEventPatchProposed)
    assert patch.path == "GRAPH.md"
    assert patch.tool_name == "Edit"
    assert patch.before_existed is True
    assert patch.before_content == "alpha\noriginal line\n"
    assert patch.after_content == "alpha\nEDITED\n"
    assert patch.tool_use_id == "tu-1"


def test_write_to_new_file_marks_before_absent(tmp_path: Path) -> None:
    queue = _register_sink("skill-2", tmp_path)
    cb = copilot._make_safe_write_can_use_tool("skill-2")

    result = asyncio.run(
        cb(
            "Write",
            {"file_path": str(tmp_path / "phases/p1/LOGIC.md"), "content": "new body"},
            ToolPermissionContext(tool_use_id="tu-2"),
        )
    )

    assert isinstance(result, PermissionResultAllow)
    patch = _drain(queue)[0]
    assert isinstance(patch, CopilotEventPatchProposed)
    assert patch.path == "phases/p1/LOGIC.md"
    assert patch.before_existed is False
    assert patch.before_content == ""
    assert patch.after_content == "new body"


def test_bash_is_held_for_approval_and_denied(tmp_path: Path) -> None:
    queue = _register_sink("skill-3", tmp_path)
    cb = copilot._make_safe_write_can_use_tool("skill-3")

    result = asyncio.run(
        cb(
            "Bash",
            {"command": "rm -rf build", "description": "clean"},
            ToolPermissionContext(tool_use_id="tu-3"),
        )
    )

    # Held, not executed — destructive Bash must not run without approval.
    assert isinstance(result, PermissionResultDeny)
    event = _drain(queue)[0]
    assert isinstance(event, CopilotEventBashApprovalRequired)
    assert event.command == "rm -rf build"
    assert event.blocked is True
    assert event.tool_use_id == "tu-3"


def test_read_is_allowed_without_emitting(tmp_path: Path) -> None:
    queue = _register_sink("skill-4", tmp_path)
    cb = copilot._make_safe_write_can_use_tool("skill-4")

    result = asyncio.run(
        cb(
            "Read",
            {"file_path": str(tmp_path / "GRAPH.md")},
            ToolPermissionContext(tool_use_id="tu-4"),
        )
    )

    assert isinstance(result, PermissionResultAllow)
    assert _drain(queue) == []
