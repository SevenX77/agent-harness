"""Tasks 2.1–2.3 — session assembly: preset+append system prompt, native
subagents (AgentDefinition), declarative allowed_tools, knowledge-only mount,
and the assets@ fingerprint echo. Replaces the copilot-rules chain."""

from __future__ import annotations

from pathlib import Path

from app.services import agent_assets, copilot
from claude_agent_sdk import PermissionResultAllow

# Read/probe MCP tools ride the declarative allow-list (zero approval). WRITE
# tools (config truth + skill entities) are deliberately absent — they hold for
# approval via can_use_tool.
_MCP_TOOL_NAMES = [
    "mcp__studio__get_llm_roles",
    "mcp__studio__search_llm_registry",
    "mcp__studio__compile_skill",
    "mcp__studio__get_skill_overview",
    "mcp__studio__read_skill_file",
    "mcp__studio__get_workspace_config",
    "mcp__studio__list_run_artifacts",
    "mcp__studio__read_run_artifact",
    "mcp__studio__run_role_test",
    "mcp__studio__get_skill_output_contract",
    "mcp__studio__predict_skill",
    "mcp__studio__get_run_detail",
    "mcp__studio__query_run_trace",
    "mcp__studio__wait_for_run",
    "mcp__studio__list_golden",
    "mcp__studio__get_golden_content",
    "mcp__studio__get_resume_validity",
    "mcp__studio__test_llm_endpoint",
    "mcp__studio__test_llm_endpoint_models",
    "mcp__studio__probe_llm_route",
]

_MCP_APPROVAL_WRITE_TOOL_NAMES = [
    "mcp__studio__create_skill",
    "mcp__studio__run_skill",
    "mcp__studio__resume_run",
    "mcp__studio__pause_run",
    "mcp__studio__stop_run",
    "mcp__studio__publish_skill",
    "mcp__studio__fork_skill",
    "mcp__studio__set_golden_baseline",
    "mcp__studio__write_golden_case",
    "mcp__studio__delete_golden_baseline",
    "mcp__studio__create_llm_role",
    "mcp__studio__update_llm_role",
    "mcp__studio__delete_llm_role",
    "mcp__studio__apply_model_profile_to_role",
    "mcp__studio__upsert_llm_endpoint",
    "mcp__studio__delete_llm_endpoint",
    "mcp__studio__update_llm_route",
    "mcp__studio__delete_llm_route",
]


async def _allow(name, tool_input, ctx):  # noqa: ANN001, ANN202
    return PermissionResultAllow()


def _chat_options(tmp_path: Path):  # noqa: ANN202
    return copilot.build_options(None, "key", tmp_path, can_use_tool=_allow)


def test_system_prompt_is_preset_plus_assembled_append(tmp_path: Path) -> None:
    options = _chat_options(tmp_path)
    sp = options.system_prompt
    assert isinstance(sp, dict)
    assert sp["type"] == "preset"
    assert sp["preset"] == "claude_code"
    append = sp["append"]
    # R1.4 in-memory assembly: one header source list, bodies follow
    assert append.splitlines()[0].startswith("<!-- assembled-by=studio sources=")
    assert "roles/moirai.md" in append.splitlines()[0]
    assert agent_assets.load_role("moirai") in append
    assert agent_assets.load_operating_manual() in append
    assert agent_assets.load_context("panel") in append
    # cli surface must NOT leak into the panel assembly
    assert agent_assets.load_context("cli") not in append


def test_three_goddesses_registered_as_native_subagents(tmp_path: Path) -> None:
    options = _chat_options(tmp_path)
    agents = options.agents
    assert agents is not None and set(agents) == {"clotho", "lachesis", "atropos"}
    skill_map = agent_assets.load_skill_map()
    for name, definition in agents.items():
        assert definition.description.strip()
        # subagent prompt = role + manual (thin-base self-sufficiency, R3.9)
        assert agent_assets.load_role(name) in definition.prompt
        assert agent_assets.load_operating_manual() in definition.prompt
        assert definition.skills == skill_map[name]
        assert definition.model is None  # inherit the session route
    assert agents["clotho"].tools == ["Read", "Glob", "Grep"]
    assert agents["atropos"].tools == ["Read", "Glob", "Grep"]
    # lachesis additionally drives the compile→predict diagnostic chain
    assert agents["lachesis"].tools == [
        "Read",
        "Glob",
        "Grep",
        "mcp__studio__compile_skill",
        "mcp__studio__predict_skill",
    ]


def test_allowed_tools_declarative_reads_and_zero_approval_mcp(tmp_path: Path) -> None:
    options = _chat_options(tmp_path)
    assert options.allowed_tools == [
        "Read",
        "Glob",
        "Grep",
        "TodoWrite",
        "Skill",
        *_MCP_TOOL_NAMES,
    ]
    # Execution/write tools stay OFF the allowlist so they route through
    # approval UX (exp-B: PowerShell is execution-class, same as Bash).
    for gated in ("Write", "Edit", "Bash", "PowerShell"):
        assert gated not in options.allowed_tools
    # Write MCP tools are gated too: they hold for approval via can_use_tool.
    for gated in _MCP_APPROVAL_WRITE_TOOL_NAMES:
        assert gated not in options.allowed_tools
    assert options.permission_mode == "default"


def test_mount_converged_to_knowledge_only(tmp_path: Path) -> None:
    options = _chat_options(tmp_path)
    assert options.add_dirs == [str(agent_assets.knowledge_dir())]


def test_probe_path_stays_bare(tmp_path: Path) -> None:
    options = copilot.build_options(None, "key", tmp_path)
    assert options.agents is None
    assert options.skills == []
    assert options.mcp_servers == {}


def test_chat_skills_come_from_agents_tree(tmp_path: Path) -> None:
    options = _chat_options(tmp_path)
    assert options.skills == agent_assets.skill_names()
    assert "moirai-intro" in options.skills
    assert "eval-judgement" in options.skills


def test_materialize_copies_agents_skills_into_workspace(tmp_path: Path) -> None:
    names = copilot._materialize_copilot_skills(tmp_path)
    assert names == agent_assets.skill_names()
    for name in names:
        assert (tmp_path / ".claude" / "skills" / name / "SKILL.md").is_file()
    assert copilot._materialize_copilot_skills(tmp_path) == names  # idempotent


def test_context_resolved_event_echoes_assets_fingerprint() -> None:
    event = copilot._context_resolved_event("skill-a")
    assert f"assets@{agent_assets.assets_fingerprint()}" in event.summary
    assert event.detail == "(no request context)"


def test_copilot_rules_chain_is_gone() -> None:
    # no-backward-compat: the old single-document rules layer is deleted outright
    assert not hasattr(copilot, "load_copilot_rules")
    assert not hasattr(copilot, "copilot_rules_hash")
    assert not hasattr(copilot, "build_session_system_prompt")
    assert not (agent_assets.agents_dir().parent / "prompts").exists()


def test_skill_documents_have_frontmatter_name_matching_dir() -> None:
    skills_root = agent_assets.agents_dir() / "skills"
    for name in agent_assets.skill_names():
        text = (skills_root / name / "SKILL.md").read_text(encoding="utf-8")
        assert text.startswith("---"), name
        assert f"name: {name}" in text, name
        assert "description:" in text, name


def test_turn_prompt_injects_only_explicit_judge_context() -> None:
    prompt = copilot._prompt_with_turn_context(
        "skill-a",
        "why?",
        judge_context={
            "compare_result_ref": "skills/s/golden/g1/compare/r1/compare_result.json",
            "judge_context_ref": "skills/s/runs/r1/copilot_judge/g1/judge_context.json",
            "baseline_ref": "skills/s/golden/g1/baseline.json",
            "diff_summary": {"total_score": 88},
        },
    )

    assert "## Copilot Judge Context" in prompt
    assert "<judge_context>" in prompt
    assert "compare_result_ref" in prompt
    assert prompt.rstrip().endswith("## 用户消息\nwhy?")


def test_turn_prompt_without_context_is_plain_user_message() -> None:
    assert copilot._prompt_with_turn_context("no-context-skill", "hello") == "hello"
