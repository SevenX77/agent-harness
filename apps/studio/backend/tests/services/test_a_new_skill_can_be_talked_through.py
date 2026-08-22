"""The wizard that turns an idea into a skill skeleton is a shipped asset.

F6's two entries (the New Skill dialog, and asking in chat) both reach the same
place: MoirAI, running the `brainstorming` skill. That only works if the asset
ships and her row in the skill map names it — an asset on disk that nobody is
mapped to is unreachable, and a mapping to an asset that is not shipped fails
the map's own validation.

Design: copilot-assist/mvp1-alignment.md F6.
"""

from __future__ import annotations

from app.services import agent_assets

WIZARD = "brainstorming"


def test_the_wizard_ships_as_an_asset() -> None:
    assert WIZARD in agent_assets.skill_names()


def test_moirai_carries_the_wizard_herself() -> None:
    """Not delegated: the wizard is the front desk's own flow. What stays off
    her row is the specialists' DESIGN skills — carrying those would make her
    do Clotho's work every time instead of handing it over."""
    moirai = agent_assets.load_skill_map()["moirai"]

    assert WIZARD in moirai
    assert "graph-design" not in moirai
    assert "agent-prompt-design" not in moirai


def test_the_wizard_says_when_it_applies() -> None:
    """The chat entry ("help me build an X") is description matching, so the
    description has to name the occasion rather than only the subject."""
    text = (agent_assets.agents_dir() / "skills" / WIZARD / "SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "name: brainstorming" in text
    assert "description:" in text
    header = text.split("---")[1]
    assert "new skill" in header.lower()


def test_the_wizard_ends_on_disk_not_in_chat() -> None:
    """A design described in the chat is not a skeleton. The asset has to say
    so, because that is the one instruction the whole entry point exists for."""
    text = (agent_assets.agents_dir() / "skills" / WIZARD / "SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "compile_skill" in text
