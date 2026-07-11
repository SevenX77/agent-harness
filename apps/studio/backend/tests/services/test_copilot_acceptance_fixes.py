"""Regressions from the 2026-07-11 manual acceptance run (PR #491 follow-up).

1. MCP tool results are content-block ARRAYS; the summary must surface the
   inner text (the JSON-array wrapper broke the role-change card silently).
2. Role-write tools must reject canonical_id/route_id vocabulary mismatches at
   the boundary — the poison entry rendered empty in Settings and the next
   autosave wiped the group from truth.
3. Bash must ALWAYS enter the ask flow: the CLI's sandbox auto-run for
   read-only commands bypassed can_use_tool, so no approval card ever showed.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from app.services import copilot, copilot_tools
from claude_agent_sdk import PermissionResultAllow


def test_tool_result_summary_unwraps_mcp_text_blocks() -> None:
    inner = '{"role_name": "writer", "before": null, "after": {}}'
    assert copilot._tool_result_summary([{"type": "text", "text": inner}]) == inner
    two = copilot._tool_result_summary(
        [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]
    )
    assert two == "a\nb"
    # non-text blocks keep the JSON dump (no information loss)
    mixed = copilot._tool_result_summary([{"type": "image", "data": "…"}])
    assert mixed.startswith("[")


def test_create_llm_role_rejects_canonical_route_mismatch() -> None:
    result = asyncio.run(
        copilot_tools.create_llm_role_tool.handler(
            {
                "name": "poison",
                "model_groups": [
                    {
                        # the exact failure shape from the acceptance run:
                        # provider-prefixed model name used as canonical_id
                        "canonical_id": "anthropic.claude-opus-4.8",
                        "display_name": "Claude Opus 4.8",
                        "provider_models": [
                            {"route_id": "anthropic-official:claude-opus-4.8"}
                        ],
                    }
                ],
            }
        )
    )

    assert result["is_error"] is True
    text = result["content"][0]["text"]
    assert "anthropic-official:claude-opus-4.8" in text
    assert "canonical_id" in text


def test_update_llm_role_rejects_canonical_route_mismatch(monkeypatch) -> None:  # noqa: ANN001
    from app.models.llm_config import RoleEntry, RolesData
    from app.routers import llm

    data = RolesData()
    data.roles["writer"] = RoleEntry()
    monkeypatch.setattr(llm, "_load_roles_or_empty", lambda: data)

    result = asyncio.run(
        copilot_tools.update_llm_role_tool.handler(
            {
                "role_name": "writer",
                "ops": {
                    "set_model_groups": [
                        {
                            "canonical_id": "deepseek.deepseek-v4-pro",
                            "display_name": "DeepSeek V4 Pro",
                            "provider_models": [
                                {"route_id": "deepseek-official:deepseek-v4-pro"}
                            ],
                        }
                    ]
                },
            }
        )
    )

    assert result["is_error"] is True
    assert "deepseek-official:deepseek-v4-pro" in result["content"][0]["text"]


def test_matching_vocabulary_passes_boundary_check() -> None:
    from app.models.llm_config import RoleModelGroup, RoleProviderModel

    groups = [
        RoleModelGroup(
            canonical_id="claude-opus-4.8",
            display_name="Claude Opus 4.8",
            provider_models=[
                RoleProviderModel(route_id="anthropic-official:claude-opus-4.8"),
                RoleProviderModel(route_id="openrouter-x:claude-opus-4.8"),
            ],
        )
    ]
    assert copilot_tools._model_groups_violation(groups) is None


def test_bash_hook_forces_ask_flow(tmp_path: Path) -> None:
    output = asyncio.run(
        copilot._bash_requires_approval_hook(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "find phases -name '*.md' | wc -l"},
                "tool_use_id": "tu-bash",
            },
            "tu-bash",
            {},
        )
    )
    spec = output["hookSpecificOutput"]
    assert spec["permissionDecision"] == "ask"
    assert spec["permissionDecisionReason"]


def test_build_options_registers_bash_ask_matcher(tmp_path: Path) -> None:
    async def cb(name, tool_input, ctx):  # noqa: ANN001
        return PermissionResultAllow()

    options = copilot.build_options(None, "key", tmp_path, can_use_tool=cb)
    assert options.hooks is not None
    matchers = {m.matcher: m for m in options.hooks["PreToolUse"]}
    assert "Bash" in matchers
    assert matchers["Bash"].hooks == [copilot._bash_requires_approval_hook]
