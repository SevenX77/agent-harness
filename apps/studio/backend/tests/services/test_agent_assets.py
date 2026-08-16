"""Task 2.1 — agent_assets: four-layer asset loading, fail-loud missing report,
full-tree fingerprint, and the in-memory assembly contract (R1.4/1.6/1.7)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from app.services import agent_assets

_AGENT_NAMES = ("moirai", "clotho", "lachesis", "atropos")


def test_agents_dir_is_the_packaged_single_source() -> None:
    root = agent_assets.agents_dir()
    assert root.name == "agents"
    assert (root / "operating-manual.md").is_file()


def test_loads_all_four_roles_manual_and_both_contexts() -> None:
    for name in _AGENT_NAMES:
        text = agent_assets.load_role(name)
        assert text.strip(), f"role {name} must not be empty"
    assert agent_assets.load_operating_manual().strip()
    assert agent_assets.load_context("panel").strip()
    assert agent_assets.load_context("cli").strip()


def test_unknown_role_and_surface_fail_fast() -> None:
    with pytest.raises(agent_assets.AgentAssetsError):
        agent_assets.load_role("zeus")
    with pytest.raises(agent_assets.AgentAssetsError):
        agent_assets.load_context("tui")


def test_skill_map_matches_shipped_skills() -> None:
    skill_map = agent_assets.load_skill_map()
    assert set(skill_map) == set(_AGENT_NAMES)
    shipped = set(agent_assets.skill_names())
    for agent, skills in skill_map.items():
        assert skills, f"{agent} must map to at least one skill"
        assert set(skills) <= shipped, f"{agent} maps to unshipped skills"
    # the raw file and the loader agree (single source, no side-cache drift)
    raw = json.loads(
        (agent_assets.agents_dir() / "agent-skill-map.json").read_text(encoding="utf-8")
    )
    assert raw == skill_map


def test_knowledge_dir_has_hub_and_all_articles() -> None:
    knowledge = agent_assets.knowledge_dir()
    assert (knowledge / "KB-00-hub.md").is_file()
    articles = sorted(p.name for p in knowledge.glob("KB-*.md"))
    assert len(articles) >= 14  # hub + KB-01..13


def test_missing_assets_reported_as_complete_list(tmp_path: Path) -> None:
    # fail loud with EVERY missing path in one diagnostic, not just the first
    incomplete = tmp_path / "agents"
    (incomplete / "roles").mkdir(parents=True)
    (incomplete / "roles" / "moirai.md").write_text("x", encoding="utf-8")
    missing = agent_assets.missing_assets(incomplete)
    joined = "\n".join(missing)
    assert "roles/clotho.md" in joined
    assert "operating-manual.md" in joined
    assert "contexts/panel.md" in joined
    assert "contexts/cli.md" in joined
    assert "knowledge/KB-00-hub.md" in joined
    assert "agent-skill-map.json" in joined
    assert "roles/moirai.md" not in joined


def test_assets_fingerprint_is_stable_short_hex_and_covers_all_layers() -> None:
    digest = agent_assets.assets_fingerprint()
    assert re.fullmatch(r"[0-9a-f]{8}", digest)
    assert digest == agent_assets.assets_fingerprint()


def test_fingerprint_changes_when_any_layer_changes(tmp_path: Path) -> None:
    # full-asset coverage (R1.7): roles, manual, contexts, knowledge, skills, map
    import shutil

    clone = tmp_path / "agents"
    shutil.copytree(agent_assets.agents_dir(), clone)
    base = agent_assets.fingerprint_of(clone)
    for rel in (
        "roles/moirai.md",
        "operating-manual.md",
        "contexts/cli.md",
        "knowledge/KB-00-hub.md",
        "skills/moirai-intro/SKILL.md",
        "agent-skill-map.json",
    ):
        target = clone / rel
        original = target.read_bytes()
        target.write_bytes(original + b"\nchanged")
        assert agent_assets.fingerprint_of(clone) != base, f"{rel} not covered"
        target.write_bytes(original)
        assert agent_assets.fingerprint_of(clone) == base


def test_assemble_inline_has_header_line_only_no_section_markers() -> None:
    # R1.4: in-memory products carry ONE header source list, no BEGIN/END markers
    text = agent_assets.assemble_inline(
        ["roles/moirai.md", "operating-manual.md", "contexts/panel.md"]
    )
    first_line = text.splitlines()[0]
    assert first_line.startswith("<!-- assembled-by=studio sources=")
    assert "roles/moirai.md,operating-manual.md,contexts/panel.md" in first_line
    assert "BEGIN assembled-section" not in text
    assert agent_assets.load_role("moirai") in text
    assert agent_assets.load_operating_manual() in text
    assert agent_assets.load_context("panel") in text


def test_moirai_intro_skill_carries_no_runtime_surface_verb() -> None:
    """R5.4 + design.md:214 "无表面维度(intro 已中立)": one skill is loaded by
    both runtimes, so it may not branch on which runtime is reading it.

    It used to spell out both fleet-status verbs ("CLI Mode: run `ah ps`" /
    "Panel Mode: subagents are resident"), which made a shared skill the
    authority on a surface fact and put an `ah` command outside the CLI
    surface layer. Where fleet state comes from belongs to the surface:
    `contexts/panel.md` for the panel, ah's own injected built-in skills for
    the CLI.
    """

    text = (agent_assets.agents_dir() / "skills" / "moirai-intro" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert not re.search(r"`ah\s+\w", text), "no ah command belongs in a shared skill"
    for surface_word in ("CLI Mode", "Panel Mode", "ah ps"):
        assert surface_word not in text, f"{surface_word!r} is a surface fact, not a protocol step"


def test_cli_context_names_only_the_one_command_the_spec_allows() -> None:
    """R7.5: `contexts/cli.md` shall 仅承载 Studio 专属的 CLI 表面 delta（女神
    agent id 绑定，经 `ah ask <id> --wait` 派遣；与工作区事实），并 shall 不复述
    ah 命令语法、不做命令可用性断言 —— 理由是复述可用性必然随 ah 升级漂移，而
    ah 自己注入的内置技能才是 CLI 侧命令事实的权威基座。

    `ah ask` is the single command the clause names, so it is the single
    command this file may mention. Any other one is the drift the clause exists
    to prevent.
    """

    commands = set(re.findall(r"`ah\s+([a-z-]+)", agent_assets.load_context("cli")))
    assert commands == {"ask"}, f"cli.md may only name `ah ask`, found: {sorted(commands)}"
