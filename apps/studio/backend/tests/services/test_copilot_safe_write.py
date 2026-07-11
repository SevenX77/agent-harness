"""F5 safe-write + 读护栏 + 挂起式审批: can_use_tool routes Write/Edit to
patch_proposed, fences Read/Glob/Grep to workspace+spec, and holds Bash /
out-of-fence reads awaiting user approval. Approval flows back into the
awaiting callback (Allow -> CLI executes itself); the old backend re-execution
path is gone by design."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.models.copilot import (
    CopilotEventPatchProposed,
    CopilotEventToolApprovalRequired,
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


async def _held_call(
    skill_id: str,
    queue: asyncio.Queue[object],
    tool_name: str,
    tool_input: dict[str, object],
    tool_use_id: str,
    *,
    approve: bool,
) -> tuple[object, CopilotEventToolApprovalRequired, copilot.ToolApprovalResolution]:
    """Run one held tool call: start the callback, catch the approval event,
    resolve it, and return (permission result, event, resolution)."""

    cb = copilot._make_safe_write_can_use_tool(skill_id)
    task = asyncio.create_task(
        cb(tool_name, tool_input, ToolPermissionContext(tool_use_id=tool_use_id))
    )
    event = await asyncio.wait_for(queue.get(), 5)
    assert isinstance(event, CopilotEventToolApprovalRequired)
    resolution = copilot.resolve_tool_approval(skill_id, tool_use_id, approve=approve)
    result = await asyncio.wait_for(task, 5)
    return result, event, resolution


@pytest.fixture(autouse=True)
def _clear_sinks():
    copilot._safe_write_sinks.clear()
    copilot._pending_tool_approvals.clear()
    yield
    copilot._safe_write_sinks.clear()
    copilot._pending_tool_approvals.clear()


def test_build_options_safe_write_routes_everything_through_callback() -> None:
    async def cb(name, tool_input, ctx):  # noqa: ANN001
        return PermissionResultAllow()

    opts = copilot.build_options("https://x", "key", "/ws", can_use_tool=cb)
    # R8.1: 读类三件 + 零审批 MCP 声明式直放(不再进回调);Write/Edit/Bash
    # 不在 allowlist,仍走 "ask" 路径经 can_use_tool 进审批 UX。
    assert "Read" in opts.allowed_tools
    for gated in ("Write", "Edit", "Bash"):
        assert gated not in opts.allowed_tools
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


# ── Bash 挂起式审批 ──────────────────────────────────────────────────────────


def test_approved_bash_returns_allow_and_backend_runs_nothing(tmp_path: Path) -> None:
    queue = _register_sink("skill-approve", tmp_path)

    async def scenario() -> None:
        result, event, resolution = await _held_call(
            "skill-approve",
            queue,
            "Bash",
            {"command": "echo hi > approved.txt", "description": "write"},
            "tu-approve",
            approve=True,
        )
        # 批准 = Allow 回给 SDK,由 CLI 自己执行;后端绝不代跑。
        assert isinstance(result, PermissionResultAllow)
        assert event.tool_name == "Bash"
        assert event.detail == "echo hi > approved.txt"
        assert resolution.resolved is True

    asyncio.run(scenario())
    assert not (tmp_path / "approved.txt").exists()


def test_rejected_bash_returns_deny(tmp_path: Path) -> None:
    queue = _register_sink("skill-reject", tmp_path)

    async def scenario() -> None:
        result, _event, resolution = await _held_call(
            "skill-reject",
            queue,
            "Bash",
            {"command": "rm -rf build"},
            "tu-reject",
            approve=False,
        )
        assert isinstance(result, PermissionResultDeny)
        assert "denied" in result.message
        assert resolution.resolved is True

    asyncio.run(scenario())


def test_bash_approval_times_out_to_deny(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(copilot, "_TOOL_APPROVAL_TIMEOUT_S", 0.01)
    queue = _register_sink("skill-timeout", tmp_path)
    cb = copilot._make_safe_write_can_use_tool("skill-timeout")

    result = asyncio.run(
        cb(
            "Bash",
            {"command": "echo never"},
            ToolPermissionContext(tool_use_id="tu-timeout"),
        )
    )

    assert isinstance(result, PermissionResultDeny)
    assert "not approved" in result.message
    assert isinstance(_drain(queue)[0], CopilotEventToolApprovalRequired)
    # 超时后审批号已清理,再批复报 not found。
    late = copilot.resolve_tool_approval("skill-timeout", "tu-timeout", approve=True)
    assert late.resolved is False
    assert late.message == "approval_not_found"


def test_resolve_twice_reports_not_found(tmp_path: Path) -> None:
    queue = _register_sink("skill-twice", tmp_path)

    async def scenario() -> None:
        await _held_call(
            "skill-twice",
            queue,
            "Bash",
            {"command": "echo once"},
            "tu-twice",
            approve=True,
        )
        second = copilot.resolve_tool_approval("skill-twice", "tu-twice", approve=True)
        assert second.resolved is False
        assert second.message == "approval_not_found"

    asyncio.run(scenario())


def test_reset_session_denies_pending_approval(tmp_path: Path) -> None:
    queue = _register_sink("skill-reset", tmp_path)
    cb = copilot._make_safe_write_can_use_tool("skill-reset")

    async def scenario() -> None:
        task = asyncio.create_task(
            cb(
                "Bash",
                {"command": "echo stale"},
                ToolPermissionContext(tool_use_id="tu-stale"),
            )
        )
        await asyncio.wait_for(queue.get(), 5)
        await copilot.reset_session("skill-reset")
        result = await asyncio.wait_for(task, 5)
        # 会话重置 = 在挂的审批一律按拒绝收尾,不留悬挂 future。
        assert isinstance(result, PermissionResultDeny)
        late = copilot.resolve_tool_approval("skill-reset", "tu-stale", approve=True)
        assert late.resolved is False

    asyncio.run(scenario())


# ── 读护栏:workspace + 挂载 spec 内放行,出圈审批 ───────────────────────────


def test_read_inside_workspace_is_allowed_without_events(tmp_path: Path) -> None:
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


def test_read_of_mounted_knowledge_dir_is_allowed(tmp_path: Path) -> None:
    from app.services import agent_assets

    queue = _register_sink("skill-kb-read", tmp_path)
    cb = copilot._make_safe_write_can_use_tool("skill-kb-read")

    result = asyncio.run(
        cb(
            "Read",
            {"file_path": str(agent_assets.knowledge_dir() / "KB-00-hub.md")},
            ToolPermissionContext(tool_use_id="tu-kb"),
        )
    )

    assert isinstance(result, PermissionResultAllow)
    assert _drain(queue) == []


def test_read_outside_workspace_is_held_then_follows_verdict(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "secret.md"
    outside.write_text("secret", encoding="utf-8")
    queue = _register_sink("skill-read-out", workspace)

    async def scenario() -> None:
        result, event, _resolution = await _held_call(
            "skill-read-out",
            queue,
            "Read",
            {"file_path": str(outside)},
            "tu-read-out",
            approve=True,
        )
        assert isinstance(result, PermissionResultAllow)
        assert event.tool_name == "Read"
        assert event.detail == str(outside)

        denied, _event2, _res2 = await _held_call(
            "skill-read-out",
            queue,
            "Read",
            {"file_path": str(outside)},
            "tu-read-out-2",
            approve=False,
        )
        assert isinstance(denied, PermissionResultDeny)

    asyncio.run(scenario())


def test_glob_outside_workspace_is_held(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    queue = _register_sink("skill-glob-out", workspace)

    async def scenario() -> None:
        result, event, _resolution = await _held_call(
            "skill-glob-out",
            queue,
            "Glob",
            {"pattern": "**/*.py", "path": str(tmp_path)},
            "tu-glob-out",
            approve=False,
        )
        assert isinstance(result, PermissionResultDeny)
        assert event.tool_name == "Glob"

    asyncio.run(scenario())


def test_glob_without_path_defaults_to_cwd_and_is_allowed(tmp_path: Path) -> None:
    queue = _register_sink("skill-glob-cwd", tmp_path)
    cb = copilot._make_safe_write_can_use_tool("skill-glob-cwd")

    result = asyncio.run(
        cb(
            "Glob",
            {"pattern": "**/*.md"},
            ToolPermissionContext(tool_use_id="tu-glob-cwd"),
        )
    )

    assert isinstance(result, PermissionResultAllow)
    assert _drain(queue) == []


def test_approval_event_streams_and_resolves_mid_stream(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """End-to-end: an approval raised during SDK drain is yielded on the ws
    stream, and approving mid-stream unblocks the awaiting callback."""

    class CredentialProvider:
        def get(self, _ref: str) -> SecretStr:
            return SecretStr("key")

    class FakeClient:
        def __init__(self, options: object) -> None:
            self.options = options
            self.connected = False
            self.permission: object | None = None

        async def connect(self) -> None:
            self.connected = True

        async def query(self, _prompt: str, session_id: str = "default") -> None:
            del session_id

        async def receive_response(self) -> AsyncIterator[object]:
            self.permission = await self.options.can_use_tool(
                "Bash",
                {"command": "echo mid-stream"},
                ToolPermissionContext(tool_use_id="tu-mid-stream"),
            )
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

    async def scenario() -> list[object]:
        events: list[object] = []
        async for event in copilot.stream_query(
            "skill-mid-stream", "run it", workspace_dir=tmp_path
        ):
            events.append(event)
            if isinstance(event, CopilotEventToolApprovalRequired):
                resolution = copilot.resolve_tool_approval(
                    "skill-mid-stream", event.tool_use_id, approve=True
                )
                assert resolution.resolved is True
        return events

    events = asyncio.run(scenario())
    approval_events = [e for e in events if isinstance(e, CopilotEventToolApprovalRequired)]
    assert len(approval_events) == 1
    assert approval_events[0].detail == "echo mid-stream"
