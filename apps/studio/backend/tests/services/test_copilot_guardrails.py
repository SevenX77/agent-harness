"""Task 2.4 — two-layer tool guardrails.

Hard boundary = PreToolUse hook (fires on EVERY tool call, immune to
allowed_tools/acceptEdits bypass): write whitelist = workspace ∪ skills root,
with the llm/ config truth dir and app_settings.json explicitly excluded.
Approval UX = can_use_tool: reads never reach it any more, in-whitelist
Write/Edit emit patch_proposed, Bash holds; approval timeout now STOPS the
task (interrupt=True) while preserving the session, instead of a silent
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
