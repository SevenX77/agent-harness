"""Naming a skill is not enabling it — the CLI also has to be able to find it.

`skills=[...]` is a *filter*: it decides which of the DISCOVERED skills the
model may call. Discovery itself comes from the `"project"` setting source,
which is what makes the CLI read `<cwd>/.claude/skills/`. Studio materializes
the shipped pool into exactly that directory before it opens the session, so
the two halves have to agree: pass the names AND leave the source that finds
them switched on.

They did not agree. `setting_sources=[]` — passed to keep the DEV MACHINE's
`~/.claude` out — also switched off project discovery, so every name in
`skills` referred to a skill the CLI had never seen. Real-machine evidence
2026-08-22: asking MoirAI to run `brainstorming` came back "brainstorming 这个
技能在我当前的可用技能列表里不存在(报 Unknown skill)", with
`.claude/skills/brainstorming/SKILL.md` sitting in that very workspace.

Design: copilot-assist/mvp1-alignment.md COPILOT_ASSIST-12.
"""

from __future__ import annotations

from pathlib import Path

from app.services import agent_assets, copilot
from claude_agent_sdk import PermissionResultAllow

from tests.support.copilot_binding import binding_for


async def _allow(name, tool_input, ctx):  # noqa: ANN001, ANN202
    return PermissionResultAllow()


def _chat_options(tmp_path: Path):  # noqa: ANN202
    return copilot.build_options(
        None, "key", tmp_path, can_use_tool=_allow, skill_binding=binding_for(tmp_path)
    )


def test_a_chat_session_can_find_the_skills_it_was_given(tmp_path: Path) -> None:
    """The source that reads `<cwd>/.claude/skills/` has to be on."""
    options = _chat_options(tmp_path)

    assert options.skills == agent_assets.load_skill_map()["moirai"]
    assert "project" in (options.setting_sources or [])


def test_a_chat_session_still_ignores_this_machine_s_own_config(tmp_path: Path) -> None:
    """Discovery is turned on for the WORKSPACE, not for the developer's home.

    `"user"` would pull in `~/.claude` — the drift the empty list existed to
    prevent, and the half of it that was right.
    """
    options = _chat_options(tmp_path)

    assert "user" not in (options.setting_sources or [])
    assert options.strict_mcp_config is True


def test_the_probe_session_loads_no_filesystem_settings_at_all(tmp_path: Path) -> None:
    """The SDK smoke path wants a bare configuration and enables no skills, so
    it has nothing to discover and keeps full isolation."""
    options = copilot.build_options(None, "claude-key", tmp_path)

    assert options.skills == []
    assert options.setting_sources == []
