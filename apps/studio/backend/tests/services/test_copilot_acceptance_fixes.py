"""Regressions from the 2026-07-11 manual acceptance run (PR #491 follow-up).

1. MCP tool results are content-block ARRAYS; the summary must surface the
   inner text (the JSON-array wrapper broke the role-change card silently).
2. Role-write tools take a FLAT route_id list and DERIVE canonical_id server-side
   (Requirement 12), so the client can never submit the poison prefixed canonical
   that rendered empty in Settings and let the next autosave wipe the group. Unknown
   route_ids fail fast at the boundary instead.
3. Bash must ALWAYS enter the ask flow: the CLI's sandbox auto-run for
   read-only commands bypassed can_use_tool, so no approval card ever showed.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
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


def _credentials_with_routes(*specs: tuple[str, str]) -> object:
    """Build an LLMCredentialsFile whose provider_routes cover the given
    (route_id, provider_model_id) pairs. canonical_id is derived, never passed."""
    from app.models.llm_config import LLMCredentialsFile, ProviderRoute

    routes = {}
    for route_id, provider_model_id in specs:
        endpoint_id, _, route_slug = route_id.partition(":")
        routes[route_id] = ProviderRoute(
            route_id=route_id,
            endpoint_id=endpoint_id,
            route_slug=route_slug,
            provider_model_id=provider_model_id,
        )
    return LLMCredentialsFile(provider_routes=routes)


def test_flat_route_input_derives_clean_canonical_not_poison_prefix() -> None:
    # The route derives the clean canonical from its provider_model_id; because the
    # client only sends the route_id (no canonical), the provider-prefixed poison
    # ("anthropic.claude-opus-4.8") that broke Settings is structurally unreachable.
    credentials = _credentials_with_routes(
        ("anthropic-official:claude-opus-4.8", "claude-opus-4-8"),
    )

    groups = copilot_tools._transform_fallback_chain_to_model_groups(
        ["anthropic-official:claude-opus-4.8"], credentials
    )

    assert len(groups) == 1
    assert groups[0].canonical_id == "claude-opus-4.8"
    assert groups[0].canonical_id != "anthropic.claude-opus-4.8"


def test_flat_route_input_unknown_route_fails_fast() -> None:
    credentials = _credentials_with_routes(
        ("deepseek-official:deepseek-v4-pro", "deepseek-v4-pro"),
    )

    with pytest.raises(copilot_tools._FlatRouteInputError) as excinfo:
        copilot_tools._transform_fallback_chain_to_model_groups(
            ["deepseek-official:deepseek-v4-pro", "ghost-endpoint:missing"], credentials
        )

    assert "ghost-endpoint:missing" in str(excinfo.value)


def test_same_canonical_routes_collapse_to_one_group() -> None:
    credentials = _credentials_with_routes(
        ("anthropic-official:claude-opus-4-8", "claude-opus-4-8"),
        ("openrouter-x:claude-opus-4.8", "anthropic/claude-opus-4.8"),
    )

    groups = copilot_tools._transform_fallback_chain_to_model_groups(
        [
            "anthropic-official:claude-opus-4-8",
            "openrouter-x:claude-opus-4.8",
        ],
        credentials,
    )

    assert len(groups) == 1
    assert groups[0].canonical_id == "claude-opus-4.8"
    assert [pm.route_id for pm in groups[0].provider_models] == [
        "anthropic-official:claude-opus-4-8",
        "openrouter-x:claude-opus-4.8",
    ]


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
