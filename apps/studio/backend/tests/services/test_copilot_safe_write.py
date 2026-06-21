"""F5 safe-write (model B): can_use_tool routes Write/Edit to patch_proposed and
holds Bash for approval. Verifies the diff payload + the apply-then-review/allow
vs hold/deny decisions without spawning a real SDK client."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace

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
from pydantic import SecretStr


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


def _sha256_text(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _checkpoint_id(skill_id: str, tool_use_id: str, path: str) -> str:
    payload = f"{skill_id}\0{tool_use_id}\0{path}"
    return f"patch:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


@pytest.fixture(autouse=True)
def _clear_sinks():
    copilot._safe_write_sinks.clear()
    copilot._pending_bash_approvals.clear()
    yield
    copilot._safe_write_sinks.clear()
    copilot._pending_bash_approvals.clear()


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
    assert patch.before_hash == _sha256_text("alpha\noriginal line\n")
    assert patch.after_hash == _sha256_text("alpha\nEDITED\n")
    assert patch.checkpoint_id == _checkpoint_id("skill-1", "tu-1", "GRAPH.md")
    assert "--- GRAPH.md" in patch.diff
    assert "+++ GRAPH.md" in patch.diff
    assert "-original line" in patch.diff
    assert "+EDITED" in patch.diff


def test_write_to_new_file_marks_before_absent_and_hashes_after(tmp_path: Path) -> None:
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
    assert patch.before_hash is None
    assert patch.after_hash == _sha256_text("new body")
    assert patch.checkpoint_id == _checkpoint_id("skill-2", "tu-2", "phases/p1/LOGIC.md")
    assert "--- /dev/null" in patch.diff
    assert "+++ phases/p1/LOGIC.md" in patch.diff
    assert "+new body" in patch.diff


def test_write_to_absolute_outside_workspace_path_is_denied(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside.md"
    workspace.mkdir()
    outside.write_text("outside original", encoding="utf-8")
    queue = _register_sink("skill-outside-write", workspace)
    cb = copilot._make_safe_write_can_use_tool("skill-outside-write")

    result = asyncio.run(
        cb(
            "Write",
            {"file_path": str(outside), "content": "outside edited"},
            ToolPermissionContext(tool_use_id="tu-outside-write"),
        )
    )

    assert isinstance(result, PermissionResultDeny)
    assert _drain(queue) == []
    assert outside.read_text(encoding="utf-8") == "outside original"


def test_edit_to_absolute_outside_workspace_path_is_denied(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside.md"
    workspace.mkdir()
    outside.write_text("outside original", encoding="utf-8")
    queue = _register_sink("skill-outside-edit", workspace)
    cb = copilot._make_safe_write_can_use_tool("skill-outside-edit")

    result = asyncio.run(
        cb(
            "Edit",
            {
                "file_path": str(outside),
                "old_string": "original",
                "new_string": "edited",
                "replace_all": False,
            },
            ToolPermissionContext(tool_use_id="tu-outside-edit"),
        )
    )

    assert isinstance(result, PermissionResultDeny)
    assert _drain(queue) == []
    assert outside.read_text(encoding="utf-8") == "outside original"


def test_edit_through_workspace_symlink_escape_is_denied(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside.md"
    workspace.mkdir()
    outside.write_text("outside original", encoding="utf-8")
    symlink = workspace / "escape.md"
    try:
        symlink.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")
    queue = _register_sink("skill-symlink-edit", workspace)
    cb = copilot._make_safe_write_can_use_tool("skill-symlink-edit")

    result = asyncio.run(
        cb(
            "Edit",
            {
                "file_path": str(symlink),
                "old_string": "original",
                "new_string": "edited",
                "replace_all": False,
            },
            ToolPermissionContext(tool_use_id="tu-symlink-edit"),
        )
    )

    assert isinstance(result, PermissionResultDeny)
    assert _drain(queue) == []
    assert outside.read_text(encoding="utf-8") == "outside original"


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


def test_approved_bash_command_executes_once_in_workspace(tmp_path: Path) -> None:
    queue = _register_sink("skill-approve", tmp_path)
    cb = copilot._make_safe_write_can_use_tool("skill-approve")
    asyncio.run(
        cb(
            "Bash",
            {"command": "printf approved > approved.txt"},
            ToolPermissionContext(tool_use_id="tu-approve"),
        )
    )
    assert isinstance(_drain(queue)[0], CopilotEventBashApprovalRequired)

    result = asyncio.run(
        copilot.resolve_bash_approval(
            "skill-approve",
            "tu-approve",
            approve=True,
        )
    )

    assert result.executed is True
    assert result.success is True
    assert result.tool_use_id == "tu-approve"
    assert (tmp_path / "approved.txt").read_text(encoding="utf-8") == "approved"

    second = asyncio.run(
        copilot.resolve_bash_approval(
            "skill-approve",
            "tu-approve",
            approve=True,
        )
    )
    assert second.executed is False
    assert second.success is False
    assert (tmp_path / "approved.txt").read_text(encoding="utf-8") == "approved"


def test_reset_session_clears_pending_bash_approval(tmp_path: Path) -> None:
    queue = _register_sink("skill-reset", tmp_path)
    cb = copilot._make_safe_write_can_use_tool("skill-reset")
    asyncio.run(
        cb(
            "Bash",
            {"command": "printf stale > stale.txt"},
            ToolPermissionContext(tool_use_id="tu-stale"),
        )
    )
    assert isinstance(_drain(queue)[0], CopilotEventBashApprovalRequired)

    asyncio.run(copilot.reset_session("skill-reset"))
    result = asyncio.run(
        copilot.resolve_bash_approval(
            "skill-reset",
            "tu-stale",
            approve=True,
        )
    )

    assert result.executed is False
    assert result.success is False
    assert result.message == "approval_not_found"
    assert not (tmp_path / "stale.txt").exists()


def test_stream_end_keeps_pending_bash_approval_resolvable_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class CredentialProvider:
        def get(self, _ref: str) -> SecretStr:
            return SecretStr("key")

    class FakeClient:
        def __init__(self, options: object) -> None:
            self.options = options
            self.connected = False

        async def connect(self) -> None:
            self.connected = True

        async def query(self, _prompt: str, session_id: str = "default") -> None:
            del session_id
            await self.options.can_use_tool(
                "Bash",
                {"command": "printf approved-after-stream > after-stream.txt"},
                ToolPermissionContext(tool_use_id="tu-after-stream"),
            )

        async def receive_response(self) -> AsyncIterator[object]:
            if False:
                yield object()

    route = SimpleNamespace(
        endpoint_id="provider",
        route_id="provider:model",
        provider_model_id="model",
        base_url="https://provider.test",
        credential_ref="endpoint:provider",
        call_method_id=None,
    )
    monkeypatch.setattr(copilot, "_session_factory", FakeClient)
    monkeypatch.setattr(
        copilot,
        "_resolve_copilot_runtime",
        lambda _model_override, role="copilot_chat": ([route], CredentialProvider()),
    )

    events = asyncio.run(
        _collect(copilot.stream_query("skill-after-stream", "run it", workspace_dir=tmp_path))
    )

    assert any(isinstance(event, CopilotEventBashApprovalRequired) for event in events)
    result = asyncio.run(
        copilot.resolve_bash_approval(
            "skill-after-stream",
            "tu-after-stream",
            approve=True,
        )
    )

    assert result.executed is True
    assert result.success is True
    assert (tmp_path / "after-stream.txt").read_text(encoding="utf-8") == "approved-after-stream"


def test_rejected_bash_command_never_executes(tmp_path: Path) -> None:
    queue = _register_sink("skill-reject", tmp_path)
    cb = copilot._make_safe_write_can_use_tool("skill-reject")
    asyncio.run(
        cb(
            "Bash",
            {"command": "printf denied > denied.txt"},
            ToolPermissionContext(tool_use_id="tu-reject"),
        )
    )
    assert isinstance(_drain(queue)[0], CopilotEventBashApprovalRequired)

    result = asyncio.run(
        copilot.resolve_bash_approval(
            "skill-reject",
            "tu-reject",
            approve=False,
        )
    )

    assert result.executed is False
    assert result.success is True
    assert not (tmp_path / "denied.txt").exists()


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


async def _collect(stream: AsyncIterator[object]) -> list[object]:
    return [event async for event in stream]
