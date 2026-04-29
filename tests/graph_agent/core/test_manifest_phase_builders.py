"""Unit tests for the schema-2.0 phase builders in loader.py (dead code).

These tests exercise ``_phase_from_agent_skill`` and ``_phase_from_graph_phase``
in isolation, without touching ``load_workflow_from_md``. They confirm the
builders produce a runtime ``Phase`` dataclass whose fields match what the
migrated SKILL.md files will declare once PR #6 Commit 2 lands.

The fixtures are shaped as if they came from a migrated production skill
(``beat_extractor`` → agent, a logic+llm graph). The 1.x ``delegate`` mode
fixtures were removed in MVP-0 B1 (2026-04-28). No filesystem I/O — every
manifest is constructed via ``TypeAdapter(SkillManifest).validate_python``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

from graph_agent.core.loader import (
    _compose_agent_system_prompt,
    _phase_from_agent_skill,
    _phase_from_graph_phase,
)
from graph_agent.core.manifest import (
    AgentSkillDef,
    LLMPhase,
    LogicPhase,
    SkillManifest,
)
from graph_agent.core.types import Phase

_SKILL_ADAPTER = TypeAdapter(SkillManifest)


class TestComposeAgentSystemPrompt:
    """Agent skill System Prompt composition from AgentProfile."""

    def test_basic_role_and_goal(self):
        manifest = _SKILL_ADAPTER.validate_python({
            "name": "beat-extractor",
            "description": "Extract beats from a chapter.",
            "type": "agent",
            "agent_profile": {
                "role": "专业的影视剧本拆解员",
                "goal": "客观地将小说原著切分为动作节拍。",
            },
        })
        assert isinstance(manifest, AgentSkillDef)

        prompt = _compose_agent_system_prompt(manifest)
        assert "<domain_expertise>" in prompt
        assert "专业的影视剧本拆解员" in prompt
        assert "</domain_expertise>" in prompt
        assert "<task_objective>" in prompt
        assert "客观地将小说原著切分为动作节拍。" in prompt
        assert "</task_objective>" in prompt

    def test_steps_render_as_numbered_workflow(self):
        manifest = _SKILL_ADAPTER.validate_python({
            "name": "plan-scenes",
            "description": "统筹制片大管家。",
            "type": "agent",
            "agent_profile": {
                "role": "统筹制片大管家",
                "goal": "从物理场拆解到编剧分镜。",
                "steps": [
                    "调用 build_objective_scenes",
                    "调用 extract_beats_concurrently",
                    "调用 dispatch_producer_strategy",
                ],
            },
        })
        assert isinstance(manifest, AgentSkillDef)

        prompt = _compose_agent_system_prompt(manifest)
        assert "<steps>" in prompt
        assert "1. 调用 build_objective_scenes" in prompt
        assert "2. 调用 extract_beats_concurrently" in prompt
        assert "3. 调用 dispatch_producer_strategy" in prompt
        assert "</steps>" in prompt

    def test_constraints_render_as_bullet_list(self):
        manifest = _SKILL_ADAPTER.validate_python({
            "name": "x",
            "description": "x",
            "type": "agent",
            "agent_profile": {
                "role": "r",
                "goal": "g",
                "constraints": ["不加入改编创意", "严禁寒暄"],
            },
        })
        assert isinstance(manifest, AgentSkillDef)

        prompt = _compose_agent_system_prompt(manifest)
        assert "<constraints>" in prompt
        assert "- 不加入改编创意" in prompt
        assert "- 严禁寒暄" in prompt
        assert "</constraints>" in prompt


class TestPhaseFromAgentSkill:
    """Agent skill → runtime Phase."""

    def test_phase_fields_propagated(self, tmp_path: Path):
        manifest = _SKILL_ADAPTER.validate_python({
            "name": "sample-agent",
            "description": "d",
            "type": "agent",
            "model_override": "CL47T",
            "agent_profile": {"role": "r", "goal": "g", "llm_role": "premium"},
            "agent_tools": [],
            "user_prompt_template": "Process: {input}",
        })
        assert isinstance(manifest, AgentSkillDef)

        phase = _phase_from_agent_skill(manifest, tmp_path, callbacks=None, loading_stack=set())
        assert isinstance(phase, Phase)
        assert phase.name == "sample-agent"
        assert phase.tier == "premium"
        assert phase.model_override == "CL47T"
        assert phase.user_prompt_template == "Process: {input}"
        assert phase.requires_llm is True

    def test_default_tier_when_unset(self, tmp_path: Path):
        manifest = _SKILL_ADAPTER.validate_python({
            "name": "x",
            "description": "d",
            "type": "agent",
            "agent_profile": {"role": "r", "goal": "g"},
        })
        assert isinstance(manifest, AgentSkillDef)

        phase = _phase_from_agent_skill(manifest, tmp_path, callbacks=None, loading_stack=set())
        assert phase.tier == "balanced"  # dataclass default


class TestPhaseFromGraphPhase:
    """Graph phase (LLM/Logic/Delegate) → runtime Phase."""

    def test_llm_phase_output_schema_threaded_to_runtime(self, tmp_path: Path):
        """Cohesion plan 方针 1.3 (2026-04-26): the schema declares
        ``LLMPhase.output_schema: str`` and the runtime PhaseExecutor
        reads ``Phase.output_schema_path`` — but the loader was missing
        the wire between them, so the field had no observable effect."""
        manifest = _SKILL_ADAPTER.validate_python({
            "name": "g",
            "description": "d",
            "type": "graph",
            "io": {"inputs": [], "outputs": []},
            "phases": [{
                "mode": "llm",
                "name": "extract",
                "llm_role": "balanced",
                "prompt": "extract",
                "output_schema": "pkg.module.MyResult",
            }],
        })
        phase_def = manifest.phases[0]
        phase = _phase_from_graph_phase(
            phase_def, tmp_path, callbacks=None, loading_stack=set()
        )
        assert phase.output_schema_path == "pkg.module.MyResult", (
            "Loader must pass LLMPhase.output_schema through to "
            "Phase.output_schema_path so PhaseExecutor can hand the "
            "schema dotted path to md_to_json. Without this wire the "
            "field is a documented no-op."
        )

    def test_llm_phase_builds_reactive_phase(self, tmp_path: Path):
        manifest = _SKILL_ADAPTER.validate_python({
            "name": "g",
            "description": "d",
            "type": "graph",
            "io": {"inputs": [], "outputs": []},
            "phases": [{
                "mode": "llm",
                "name": "segment",
                "llm_role": "balanced",
                "prompt": "You are a segmenter.",
                "user_prompt_template": "Segment: {text}",
                "max_iterations": 12,
                "max_nudges": 3,
                "max_retries": 2,
                "retry_target": "segment",
            }],
        })

        phase_def = manifest.phases[0]
        assert isinstance(phase_def, LLMPhase)

        phase = _phase_from_graph_phase(phase_def, tmp_path, callbacks=None, loading_stack=set())
        assert isinstance(phase, Phase)
        assert phase.name == "segment"
        assert phase.system_prompt == "You are a segmenter."
        assert phase.user_prompt_template == "Segment: {text}"
        assert phase.max_iterations == 12
        assert phase.max_nudges == 3
        assert phase.max_retries == 2
        assert phase.retry_target == "segment"
        assert phase.requires_llm is True

    def test_llm_phase_with_steps_renders_into_system_prompt(self, tmp_path: Path):
        manifest = _SKILL_ADAPTER.validate_python({
            "name": "g",
            "description": "d",
            "type": "graph",
            "io": {"inputs": [], "outputs": []},
            "phases": [{
                "mode": "llm",
                "name": "plan",
                "prompt": "Plan carefully.",
                "steps": ["调用 X 工具", "验证 Y", "返回结果"],
            }],
        })

        phase = _phase_from_graph_phase(
            manifest.phases[0], tmp_path, callbacks=None, loading_stack=set()
        )

        assert phase.system_prompt is not None
        assert phase.system_prompt.endswith(
            "<steps>\n  1. 调用 X 工具\n  2. 验证 Y\n  3. 返回结果\n</steps>"
        )
        assert "<steps>" in phase.system_prompt
        assert "1. 调用 X 工具" in phase.system_prompt
        assert "2. 验证 Y" in phase.system_prompt

    def test_llm_phase_without_steps_prompt_unchanged(self, tmp_path: Path):
        manifest = _SKILL_ADAPTER.validate_python({
            "name": "g",
            "description": "d",
            "type": "graph",
            "io": {"inputs": [], "outputs": []},
            "phases": [{
                "mode": "llm",
                "name": "plan",
                "prompt": "Plan carefully.",
            }],
        })

        phase = _phase_from_graph_phase(
            manifest.phases[0], tmp_path, callbacks=None, loading_stack=set()
        )

        assert phase.system_prompt == "Plan carefully."
        assert "<steps>" not in phase.system_prompt

    def test_llm_phase_dead_end_threshold_default_and_override(self, tmp_path: Path):
        default_manifest = _SKILL_ADAPTER.validate_python({
            "name": "g",
            "description": "d",
            "type": "graph",
            "io": {"inputs": [], "outputs": []},
            "phases": [{
                "mode": "llm",
                "name": "segment",
                "prompt": "p",
            }],
        })
        default_phase = _phase_from_graph_phase(
            default_manifest.phases[0], tmp_path, callbacks=None, loading_stack=set()
        )
        assert default_phase.dead_end_threshold == 3, (
            "LLMPhase without an explicit dead_end_threshold must default to 3 "
            "so the cognitive middleware's pruning behaviour matches the "
            "documented runtime default."
        )

        overridden_manifest = _SKILL_ADAPTER.validate_python({
            "name": "g",
            "description": "d",
            "type": "graph",
            "io": {"inputs": [], "outputs": []},
            "phases": [{
                "mode": "llm",
                "name": "segment",
                "prompt": "p",
                "dead_end_threshold": 7,
            }],
        })
        overridden_phase = _phase_from_graph_phase(
            overridden_manifest.phases[0], tmp_path, callbacks=None, loading_stack=set()
        )
        assert overridden_phase.dead_end_threshold == 7, (
            "PM-supplied dead_end_threshold must thread through the loader "
            "into the runtime Phase so the schema knob is not silently dead."
        )

    def test_llm_phase_dead_end_threshold_rejects_zero(self):
        with pytest.raises(ValidationError):
            _SKILL_ADAPTER.validate_python({
                "name": "g",
                "description": "d",
                "type": "graph",
                "io": {"inputs": [], "outputs": []},
                "phases": [{
                    "mode": "llm",
                    "name": "segment",
                    "prompt": "p",
                    "dead_end_threshold": 0,
                }],
            })

    def test_logic_phase_builds_nonllm_phase(self, tmp_path: Path):
        # A real test of execute_steps resolution would require a module
        # present on the filesystem. Here we use a stub import path and
        # expect a resolver failure — confirming the builder attempts
        # resolution. When PR #6 Commit 2 wires this in, the production
        # skills' execute_steps will point to real modules.
        manifest = _SKILL_ADAPTER.validate_python({
            "name": "g",
            "description": "d",
            "type": "graph",
            "io": {"inputs": [], "outputs": []},
            "phases": [{
                "mode": "logic",
                "name": "prep",
                "execute_steps": ["nonexistent.stub.module.func"],
            }],
        })
        phase_def = manifest.phases[0]
        assert isinstance(phase_def, LogicPhase)

        from graph_agent.core.exceptions import SkillLoadError
        with pytest.raises(SkillLoadError):
            _phase_from_graph_phase(phase_def, tmp_path, callbacks=None, loading_stack=set())

# DelegatePhase coverage removed in MVP-0 B1 (2026-04-28).


# =============================================================================
# Persona injection tests (PR #6 Commit 4)
# =============================================================================

def test_phase_from_agent_skill_injects_persona(tmp_path: Path) -> None:
    """Persona role_profile must be prepended to the composed system_prompt when an agent skill declares ``adopted_persona``."""
    from pydantic import TypeAdapter

    from graph_agent.core.loader import _phase_from_agent_skill
    from graph_agent.core.manifest import AgentSkillDef, SkillManifest

    base_dir = tmp_path / "skills" / "host"
    (base_dir / "subskills" / "p1").mkdir(parents=True)
    (base_dir / "subskills" / "p1" / "SKILL.md").write_text(
        "---\n"
        'schema_version: "2.0"\n'
        "name: p1\n"
        "description: tiny persona\n"
        "type: persona\n"
        'role_profile: "PERSONA-ROLE-MARKER"\n'
        "---\n",
        encoding="utf-8",
    )

    manifest = TypeAdapter(SkillManifest).validate_python({
        "schema_version": "2.0",
        "name": "host-agent",
        "description": "host",
        "type": "agent",
        "agent_profile": {
            "role": "测试角色",
            "goal": "测试目标",
        },
        "adopted_persona": "p1",
    })
    assert isinstance(manifest, AgentSkillDef)
    phase = _phase_from_agent_skill(manifest, base_dir, callbacks=None, loading_stack=set())
    assert "PERSONA-ROLE-MARKER" in (phase.system_prompt or "")
    assert phase.system_prompt.index("PERSONA-ROLE-MARKER") < phase.system_prompt.index("测试角色")


def test_phase_from_graph_phase_injects_persona(tmp_path: Path) -> None:
    """LLMPhase.adopted_persona must inject role_profile before the original prompt."""
    from pydantic import TypeAdapter

    from graph_agent.core.loader import _phase_from_graph_phase
    from graph_agent.core.manifest import LLMPhase, PhaseDef

    base_dir = tmp_path / "skills" / "host"
    (base_dir / "subskills" / "p2").mkdir(parents=True)
    (base_dir / "subskills" / "p2" / "SKILL.md").write_text(
        "---\n"
        'schema_version: "2.0"\n'
        "name: p2\n"
        "description: tiny persona\n"
        "type: persona\n"
        'role_profile: "GRAPH-PERSONA-MARKER"\n'
        "---\n",
        encoding="utf-8",
    )

    phase_def = TypeAdapter(PhaseDef).validate_python({
        "name": "p",
        "mode": "llm",
        "prompt": "ORIGINAL-PROMPT-BODY",
        "adopted_persona": "p2",
    })
    assert isinstance(phase_def, LLMPhase)
    phase = _phase_from_graph_phase(phase_def, base_dir, callbacks=None, loading_stack=set())
    assert "GRAPH-PERSONA-MARKER" in (phase.system_prompt or "")
    assert phase.system_prompt.index("GRAPH-PERSONA-MARKER") < phase.system_prompt.index("ORIGINAL-PROMPT-BODY")


def test_phase_from_agent_skill_injects_evaluation_rubrics(tmp_path: Path) -> None:
    """``evaluation_rubrics`` on the persona must land between role_profile and the host prompt."""
    from pydantic import TypeAdapter

    from graph_agent.core.loader import _phase_from_agent_skill
    from graph_agent.core.manifest import AgentSkillDef, SkillManifest

    base_dir = tmp_path / "skills" / "host"
    (base_dir / "subskills" / "rubric_persona").mkdir(parents=True)
    (base_dir / "subskills" / "rubric_persona" / "SKILL.md").write_text(
        "---\n"
        'schema_version: "2.0"\n'
        "name: rubric_persona\n"
        "description: persona with rubric\n"
        "type: persona\n"
        'role_profile: "ROLE-MARKER"\n'
        'evaluation_rubrics: "RUBRIC-MARKER"\n'
        "---\n",
        encoding="utf-8",
    )

    manifest = TypeAdapter(SkillManifest).validate_python({
        "schema_version": "2.0",
        "name": "host-agent",
        "description": "host",
        "type": "agent",
        "agent_profile": {"role": "host-role", "goal": "host-goal"},
        "adopted_persona": "rubric_persona",
    })
    assert isinstance(manifest, AgentSkillDef)
    phase = _phase_from_agent_skill(manifest, base_dir, callbacks=None, loading_stack=set())
    sp = phase.system_prompt or ""
    assert "ROLE-MARKER" in sp and "RUBRIC-MARKER" in sp and "host-role" in sp
    assert sp.index("ROLE-MARKER") < sp.index("RUBRIC-MARKER") < sp.index("host-role")
    assert "## 评估标准" in sp


def test_persona_few_shot_examples_render_as_examples_tag(tmp_path: Path) -> None:
    """Persona few_shot_examples now render into the prompt <examples> tag."""
    from pydantic import TypeAdapter

    from graph_agent.core.loader import _phase_from_agent_skill
    from graph_agent.core.manifest import AgentSkillDef, SkillManifest

    base_dir = tmp_path / "skills" / "host"
    (base_dir / "subskills" / "shotty").mkdir(parents=True)
    (base_dir / "subskills" / "shotty" / "SKILL.md").write_text(
        "---\n"
        'schema_version: "2.0"\n'
        "name: shotty\n"
        "description: persona with examples\n"
        "type: persona\n"
        'role_profile: "ROLE"\n'
        "few_shot_examples:\n"
        "  - example one\n"
        "  - example two\n"
        "---\n",
        encoding="utf-8",
    )

    manifest = TypeAdapter(SkillManifest).validate_python({
        "schema_version": "2.0",
        "name": "host-agent",
        "description": "host",
        "type": "agent",
        "agent_profile": {"role": "r", "goal": "g"},
        "adopted_persona": "shotty",
    })
    assert isinstance(manifest, AgentSkillDef)
    phase = _phase_from_agent_skill(manifest, base_dir, callbacks=None, loading_stack=set())
    sp = phase.system_prompt or ""
    assert "<examples>" in sp
    assert '<example id="1">example one</example>' in sp
    assert '<example id="2">example two</example>' in sp
