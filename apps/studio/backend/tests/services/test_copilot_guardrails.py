"""Task 2.4 — two-layer tool guardrails.

Hard boundary = PreToolUse hook (fires on EVERY tool call, immune to
allowed_tools/acceptEdits bypass): write whitelist = workspace ∪ skills root,
with the llm/ config truth dir and app_settings.json explicitly excluded.
Approval UX = can_use_tool, three explicit tiers: the declarative allow-list
(reads + TodoWrite/Skill + read/probe MCP tools) passes; in-whitelist
Write/Edit emit patch_proposed; EVERYTHING else — execution class
(Bash/PowerShell), MCP writes, unknown tools — holds for approval (exp-B
regression: no default-allow tier exists). Approval timeout STOPS the task
(interrupt=True) while preserving the session, instead of a silent
deny-and-continue.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from app.models.copilot import CopilotEventError, CopilotEventToolApprovalRequired
from app.services import copilot
from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny
from claude_agent_sdk.types import ToolPermissionContext


@pytest.fixture(autouse=True)
def _clean_registries():  # noqa: ANN202
    copilot._safe_write_sinks.clear()
    copilot._pending_tool_approvals.clear()
    yield
    copilot._safe_write_sinks.clear()
    copilot._pending_tool_approvals.clear()


def _register_sink(skill_id: str, workspace: Path) -> asyncio.Queue:
    queue: asyncio.Queue = asyncio.Queue()
    copilot._safe_write_sinks[skill_id] = copilot._SafeWriteSink(
        queue=queue, workspace_root=workspace
    )
    return queue


def _hook_input(tool_name: str, file_path: str) -> dict[str, Any]:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": tool_name,
        "tool_input": {"file_path": file_path},
        "tool_use_id": "tu-hook",
    }


def _decision(output: dict[str, Any]) -> tuple[str | None, str | None]:
    spec = output.get("hookSpecificOutput", {})
    return spec.get("permissionDecision"), spec.get("permissionDecisionReason")


# ── hard boundary layer (PreToolUse hook) ───────────────────────────────────


def test_hook_denies_write_outside_whitelist(tmp_path: Path) -> None:
    _register_sink("s-hook", tmp_path / "ws")
    hook = copilot._make_write_boundary_hook("s-hook")
    outside = str(tmp_path / "elsewhere" / "x.md")

    output = asyncio.run(hook(_hook_input("Write", outside), "tu-hook", {}))

    decision, reason = _decision(output)
    assert decision == "deny"
    assert reason and "x.md" in reason


def test_hook_passes_workspace_and_skills_root_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core import config

    skills_root = tmp_path / "Skills"
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", tmp_path)
    workspace = tmp_path / "ws"
    _register_sink("s-hook", workspace)
    hook = copilot._make_write_boundary_hook("s-hook")

    inside = asyncio.run(
        hook(_hook_input("Write", str(workspace / "GRAPH.md")), "tu", {})
    )
    in_skills = asyncio.run(
        hook(_hook_input("Edit", str(skills_root / "demo" / "GRAPH.md")), "tu", {})
    )

    # in-whitelist: NO decision — the normal permission flow (ask →
    # can_use_tool → patch card) must still run; "allow" here would bypass it.
    assert _decision(inside)[0] is None
    assert _decision(in_skills)[0] is None


def test_hook_excludes_llm_truth_and_app_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core import config

    monkeypatch.setattr(config, "APP_SETTINGS_DIR", tmp_path)
    # workspace deliberately set to the settings dir itself: even if a future
    # whitelist covers the settings dir, the exclusions must still hold.
    _register_sink("s-hook", tmp_path)
    hook = copilot._make_write_boundary_hook("s-hook")

    llm_write = asyncio.run(
        hook(_hook_input("Write", str(tmp_path / "llm" / "llm_roles.yaml")), "tu", {})
    )
    settings_write = asyncio.run(
        hook(_hook_input("Edit", str(tmp_path / "app_settings.json")), "tu", {})
    )

    assert _decision(llm_write)[0] == "deny"
    assert _decision(settings_write)[0] == "deny"


def test_hook_denies_when_no_active_session(tmp_path: Path) -> None:
    hook = copilot._make_write_boundary_hook("no-such-skill")
    output = asyncio.run(hook(_hook_input("Write", str(tmp_path / "x")), "tu", {}))
    assert _decision(output)[0] == "deny"


def test_hook_ignores_non_write_tools(tmp_path: Path) -> None:
    _register_sink("s-hook", tmp_path)
    hook = copilot._make_write_boundary_hook("s-hook")
    output = asyncio.run(hook(_hook_input("Read", "/anywhere/at/all"), "tu", {}))
    assert _decision(output)[0] is None


def test_build_options_wires_write_boundary_hook(tmp_path: Path) -> None:
    async def cb(name, tool_input, ctx):  # noqa: ANN001
        return PermissionResultAllow()

    hook = copilot._make_write_boundary_hook("s-hook")
    chat = copilot.build_options(
        None, "key", tmp_path, can_use_tool=cb, write_boundary_hook=hook
    )
    probe = copilot.build_options(None, "key", tmp_path)

    assert chat.hooks is not None and "PreToolUse" in chat.hooks
    matcher = chat.hooks["PreToolUse"][0]
    assert "Write" in (matcher.matcher or "")
    assert matcher.hooks == [hook]
    assert probe.hooks is None


# ── approval UX layer (can_use_tool) ────────────────────────────────────────


def test_reads_never_reach_held_approval(tmp_path: Path) -> None:
    queue = _register_sink("s-read", tmp_path)
    cb = copilot._make_safe_write_can_use_tool("s-read")

    result = asyncio.run(
        cb(
            "Read",
            {"file_path": "/definitely/outside/everything"},
            ToolPermissionContext(tool_use_id="tu-r"),
        )
    )

    assert isinstance(result, PermissionResultAllow)
    assert queue.empty()
    assert not copilot._pending_tool_approvals


def test_approval_timeout_stops_task_but_preserves_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(copilot, "_TOOL_APPROVAL_TIMEOUT_S", 0.05)
    queue = _register_sink("s-timeout", tmp_path)
    cb = copilot._make_safe_write_can_use_tool("s-timeout")

    result = asyncio.run(
        cb("Bash", {"command": "ls"}, ToolPermissionContext(tool_use_id="tu-t"))
    )

    assert isinstance(result, PermissionResultDeny)
    assert result.interrupt is True  # stop the task...
    events = []
    while not queue.empty():
        events.append(queue.get_nowait())
    assert any(isinstance(e, CopilotEventToolApprovalRequired) for e in events)
    timeout_events = [e for e in events if isinstance(e, CopilotEventError)]
    assert timeout_events and timeout_events[0].error_code == "tool_approval_timeout"
    # ...but the session itself is preserved (registry keeps the sink)
    assert "s-timeout" in copilot._safe_write_sinks


def test_default_timeout_is_thirty_minutes() -> None:
    assert copilot._TOOL_APPROVAL_TIMEOUT_S == 1800.0


# ── MCP config-write tools hold for approval (命门) ──────────────────────────
#
# Empirically proven (probe against the real claude CLI): an ``mcp__studio__``
# config-write tool removed from the pre-allowed whitelist DOES reach
# ``can_use_tool`` — MCP tools have no Bash-style sandbox auto-run — so approval
# fires through can_use_tool alone (no PreToolUse hook needed for MCP writes).


async def _hold_and_resolve(
    skill_id: str, tool_name: str, tool_input: dict[str, Any], *, approve: bool
):  # noqa: ANN202
    cb = copilot._make_safe_write_can_use_tool(skill_id)
    task = asyncio.ensure_future(
        cb(tool_name, tool_input, ToolPermissionContext(tool_use_id="tu-cfg"))
    )
    # Let the callback register the pending approval + emit the event.
    for _ in range(50):
        await asyncio.sleep(0)
        if (skill_id, "tu-cfg") in copilot._pending_tool_approvals:
            break
    held = not task.done()
    copilot.resolve_tool_approval(skill_id, "tu-cfg", approve=approve)
    result = await task
    return held, result


def test_mcp_config_write_holds_for_approval_then_approves(tmp_path: Path) -> None:
    queue = _register_sink("s-cfg", tmp_path)

    held, result = asyncio.run(
        _hold_and_resolve(
            "s-cfg",
            "mcp__studio__create_llm_role",
            {"name": "writer", "model_groups": []},
            approve=True,
        )
    )

    assert held is True  # the write did NOT proceed before user approval
    assert isinstance(result, PermissionResultAllow)
    events = []
    while not queue.empty():
        events.append(queue.get_nowait())
    approval_events = [
        e for e in events if isinstance(e, CopilotEventToolApprovalRequired)
    ]
    assert approval_events and approval_events[0].tool_name == "mcp__studio__create_llm_role"


def test_mcp_config_write_denied_returns_deny(tmp_path: Path) -> None:
    _register_sink("s-cfg-deny", tmp_path)

    held, result = asyncio.run(
        _hold_and_resolve(
            "s-cfg-deny",
            "mcp__studio__delete_llm_endpoint",
            {"endpoint_id": "prov-x"},
            approve=False,
        )
    )

    assert held is True
    assert isinstance(result, PermissionResultDeny)


def test_mcp_config_write_detail_redacts_api_key(tmp_path: Path) -> None:
    queue = _register_sink("s-cfg-key", tmp_path)

    def _run():  # noqa: ANN202
        return asyncio.run(
            _hold_and_resolve(
                "s-cfg-key",
                "mcp__studio__upsert_llm_endpoint",
                {"endpoint_id": "prov-x", "api_key": "sk-supersecret-123"},
                approve=False,
            )
        )

    _run()
    events = []
    while not queue.empty():
        events.append(queue.get_nowait())
    approval = next(
        e for e in events if isinstance(e, CopilotEventToolApprovalRequired)
    )
    assert "sk-supersecret-123" not in approval.detail
    assert "upsert_llm_endpoint" in approval.detail.lower() or "Endpoint" in approval.detail


def test_read_probe_mcp_tools_are_pre_allowed_not_held() -> None:
    # Read/probe MCP tools ride the declarative allow-list (never reach approval);
    # write tools do NOT appear there.
    allowed = set(copilot._DECLARATIVE_ALLOWED_TOOLS)
    assert "mcp__studio__search_llm_registry" in allowed
    assert "mcp__studio__test_llm_endpoint" in allowed
    assert "mcp__studio__probe_llm_route" in allowed
    assert "mcp__studio__get_run_detail" in allowed
    assert "mcp__studio__list_golden" in allowed
    assert "mcp__studio__get_golden_content" in allowed
    assert "mcp__studio__get_resume_validity" in allowed
    for write_tool in (
        "mcp__studio__create_skill",
        "mcp__studio__run_skill",
        "mcp__studio__resume_run",
        "mcp__studio__publish_skill",
        "mcp__studio__fork_skill",
        "mcp__studio__set_golden_baseline",
        "mcp__studio__delete_golden_baseline",
        "mcp__studio__create_llm_role",
        "mcp__studio__update_llm_role",
        "mcp__studio__delete_llm_role",
        "mcp__studio__upsert_llm_endpoint",
        "mcp__studio__delete_llm_endpoint",
        "mcp__studio__update_llm_route",
        "mcp__studio__delete_llm_route",
        "mcp__studio__apply_model_profile_to_role",
    ):
        assert write_tool not in allowed


def test_mcp_create_skill_holds_for_approval_then_approves(tmp_path: Path) -> None:
    # skill 实体写与配置写同一条审批语义:先挂起、用户批准后放行。
    queue = _register_sink("s-skill", tmp_path)

    held, result = asyncio.run(
        _hold_and_resolve(
            "s-skill",
            "mcp__studio__create_skill",
            {"skill_id": "brand-new"},
            approve=True,
        )
    )

    assert held is True
    assert isinstance(result, PermissionResultAllow)
    events = []
    while not queue.empty():
        events.append(queue.get_nowait())
    approval_events = [
        e for e in events if isinstance(e, CopilotEventToolApprovalRequired)
    ]
    assert approval_events and approval_events[0].tool_name == "mcp__studio__create_skill"


def test_mcp_run_skill_holds_for_approval_then_approves(tmp_path: Path) -> None:
    # 真实执行(调 LLM、花钱)与写工具同一条审批语义:先挂起、批准后放行。
    queue = _register_sink("s-run", tmp_path)

    held, result = asyncio.run(
        _hold_and_resolve(
            "s-run",
            "mcp__studio__run_skill",
            {"skill_id": "text-segmentation", "input_data": {"text": "hi"}},
            approve=True,
        )
    )

    assert held is True
    assert isinstance(result, PermissionResultAllow)
    events = []
    while not queue.empty():
        events.append(queue.get_nowait())
    approval_events = [
        e for e in events if isinstance(e, CopilotEventToolApprovalRequired)
    ]
    assert approval_events and approval_events[0].tool_name == "mcp__studio__run_skill"


# ── exp-B 事故回归:白名单之外一律审批,未知工具绝不默认放行 ──────────────────
#
# 实测事故(2026-08-01 无头实验 exp-B):Write 被写白名单拒绝后,模型改用 Windows
# CLI 自带的 PowerShell 工具把 runtime_config.json 和 import 文件直接写进了无权
# 目录,全程零审批 —— 根源是 can_use_tool 末行对一切未显式处理的工具默认
# PermissionResultAllow。权限模型必须是"已知语义白名单"(声明式名单直放,其余
# 一律挂起审批),不是"已知危险黑名单"。


def test_powershell_holds_for_approval_then_approves(tmp_path: Path) -> None:
    queue = _register_sink("s-pwsh", tmp_path)
    command = 'Set-Content -Path "D:/elsewhere/runtime_config.json" -Value "{}"'

    held, result = asyncio.run(
        _hold_and_resolve("s-pwsh", "PowerShell", {"command": command}, approve=True)
    )

    assert held is True  # the command did NOT run before user approval
    assert isinstance(result, PermissionResultAllow)
    events = []
    while not queue.empty():
        events.append(queue.get_nowait())
    approval_events = [
        e for e in events if isinstance(e, CopilotEventToolApprovalRequired)
    ]
    assert approval_events and approval_events[0].tool_name == "PowerShell"
    assert command in approval_events[0].detail


def test_powershell_denied_returns_deny(tmp_path: Path) -> None:
    _register_sink("s-pwsh-deny", tmp_path)

    held, result = asyncio.run(
        _hold_and_resolve(
            "s-pwsh-deny", "PowerShell", {"command": "Remove-Item x"}, approve=False
        )
    )

    assert held is True
    assert isinstance(result, PermissionResultDeny)


def test_unknown_tool_holds_for_approval_not_allowed(tmp_path: Path) -> None:
    # 未来 SDK 新增的任何执行/写类工具,在被显式分类前必须走审批,不是放行。
    queue = _register_sink("s-unknown", tmp_path)

    held, result = asyncio.run(
        _hold_and_resolve(
            "s-unknown", "FutureExecTool", {"target": "anything"}, approve=True
        )
    )

    assert held is True
    assert isinstance(result, PermissionResultAllow)
    events = []
    while not queue.empty():
        events.append(queue.get_nowait())
    approval_events = [
        e for e in events if isinstance(e, CopilotEventToolApprovalRequired)
    ]
    assert approval_events and approval_events[0].tool_name == "FutureExecTool"


def test_unknown_tool_without_session_is_denied() -> None:
    # 没有活跃会话流就无法挂审批卡:未知工具必须 Deny,而不是静默 Allow。
    cb = copilot._make_safe_write_can_use_tool("s-no-sink")

    result = asyncio.run(
        cb("FutureExecTool", {}, ToolPermissionContext(tool_use_id="tu-x"))
    )

    assert isinstance(result, PermissionResultDeny)


def test_execution_hook_forces_ask_for_powershell() -> None:
    # R8.3 同因:CLI 沙箱对"安全只读命令"的自动放行会绕过 can_use_tool,
    # PowerShell 与 Bash 同等对待,PreToolUse "ask" 压回权限流。
    output = asyncio.run(
        copilot._execution_requires_approval_hook(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "PowerShell",
                "tool_input": {"command": "Get-ChildItem"},
                "tool_use_id": "tu-pwsh",
            },
            "tu-pwsh",
            {},
        )
    )

    spec = output["hookSpecificOutput"]
    assert spec["permissionDecision"] == "ask"
    assert "PowerShell" in spec["permissionDecisionReason"]


def test_build_options_execution_ask_matcher_covers_powershell(tmp_path: Path) -> None:
    # 执行类工具集合是单一事实源:hook matcher 从 _EXECUTION_CLASS_TOOLS 派生,
    # 不再在 build_options 里手写第二份 "Bash" 字符串。
    async def cb(name, tool_input, ctx):  # noqa: ANN001
        return PermissionResultAllow()

    options = copilot.build_options(None, "key", tmp_path, can_use_tool=cb)

    assert set(copilot._EXECUTION_CLASS_TOOLS) == {"Bash", "PowerShell"}
    assert options.hooks is not None
    matchers = {m.matcher: m for m in options.hooks["PreToolUse"]}
    matcher = matchers[copilot._EXECUTION_BOUNDARY_MATCHER]
    assert matcher.hooks == [copilot._execution_requires_approval_hook]


def test_todowrite_and_skill_ride_declarative_allow_list(tmp_path: Path) -> None:
    # 默认档翻成审批后,已知声明式工具必须显式进免审批名单,不能靠 fall-through:
    # TodoWrite 只写 CLI 内部计划状态,Skill 只加载随包场景技能说明(其后续工具
    # 调用逐一走本权限流)。
    allowed = set(copilot._DECLARATIVE_ALLOWED_TOOLS)
    assert "TodoWrite" in allowed
    assert "Skill" in allowed

    queue = _register_sink("s-decl", tmp_path)
    cb = copilot._make_safe_write_can_use_tool("s-decl")
    result = asyncio.run(
        cb("TodoWrite", {"todos": []}, ToolPermissionContext(tool_use_id="tu-td"))
    )

    assert isinstance(result, PermissionResultAllow)
    assert queue.empty()
    assert not copilot._pending_tool_approvals


def test_gated_tool_classes_never_enter_declarative_list() -> None:
    # 三档分类互斥:执行类 / 写类 / MCP 写类与声明式免审批名单永不相交。
    declarative = set(copilot._DECLARATIVE_ALLOWED_TOOLS)
    assert not set(copilot._EXECUTION_CLASS_TOOLS) & declarative
    assert not set(copilot._WRITE_CLASS_TOOLS) & declarative
    assert not copilot._MCP_APPROVAL_WRITE_TOOLS & declarative
