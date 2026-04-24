"""Unit tests for the schema-2.0 phase builders in loader.py (dead code).

These tests exercise ``_phase_from_agent_skill`` and ``_phase_from_graph_phase``
in isolation, without touching ``load_workflow_from_md``. They confirm the
builders produce a runtime ``Phase`` dataclass whose fields match what the
migrated SKILL.md files will declare once PR #6 Commit 2 lands.

The fixtures are shaped as if they came from a migrated production skill
(``beat_extractor`` → agent, a logic+llm+delegate graph). No filesystem I/O
— every manifest is constructed via ``TypeAdapter(SkillManifest).validate_python``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import TypeAdapter

from graph_agent.core.loader import (
    _compose_agent_system_prompt,
    _phase_from_agent_skill,
    _phase_from_graph_phase,
)
from graph_agent.core.manifest import (
    AgentSkillDef,
    DelegatePhase,
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
        assert "你是专业的影视剧本拆解员" in prompt
        assert "你的目标:客观地将小说原著切分为动作节拍。" in prompt

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
        assert "1. 调用 build_objective_scenes" in prompt
        assert "2. 调用 extract_beats_concurrently" in prompt
        assert "3. 调用 dispatch_producer_strategy" in prompt

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
        assert "- 不加入改编创意" in prompt
        assert "- 严禁寒暄" in prompt


class TestPhaseFromAgentSkill:
    """Agent skill → runtime Phase."""

    def test_phase_fields_propagated(self, tmp_path: Path):
        manifest = _SKILL_ADAPTER.validate_python({
            "name": "sample-agent",
            "description": "d",
            "type": "agent",
            "tier": "premium",
            "model_override": "CL47T",
            "agent_profile": {"role": "r", "goal": "g"},
            "agent_tools": [],
            "subagent_enabled": True,
            "user_prompt_template": "Process: {input}",
        })
        assert isinstance(manifest, AgentSkillDef)

        phase = _phase_from_agent_skill(manifest, tmp_path, callbacks=None, loading_stack=set())
        assert isinstance(phase, Phase)
        assert phase.name == "sample-agent"
        assert phase.tier == "premium"
        assert phase.model_override == "CL47T"
        assert phase.subagent_enabled is True
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

    def test_llm_phase_builds_reactive_phase(self, tmp_path: Path):
        manifest = _SKILL_ADAPTER.validate_python({
            "name": "g",
            "description": "d",
            "type": "graph",
            "io": {"inputs": [], "outputs": []},
            "phases": [{
                "mode": "llm",
                "name": "segment",
                "tier": "balanced",
                "prompt": "You are a segmenter.",
                "user_prompt_template": "Segment: {text}",
                "max_iterations": 12,
                "max_nudges": 3,
                "max_retries": 2,
                "retry_target": "earlier_phase",
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
        assert phase.retry_target == "earlier_phase"
        assert phase.requires_llm is True

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

    def test_delegate_phase_missing_subgraph_raises(self, tmp_path: Path):
        """DelegatePhase with a path that doesn't exist → SkillLoadError."""
        manifest = _SKILL_ADAPTER.validate_python({
            "name": "g",
            "description": "d",
            "type": "graph",
            "io": {"inputs": [], "outputs": []},
            "phases": [{
                "mode": "delegate",
                "name": "delegate_step",
                "subgraph": "./does/not/exist",
                "context_bridge": {"inputs": {}, "outputs": {}},
            }],
        })
        phase_def = manifest.phases[0]
        assert isinstance(phase_def, DelegatePhase)

        from graph_agent.core.exceptions import SkillLoadError
        with pytest.raises(SkillLoadError, match="subgraph not found"):
            _phase_from_graph_phase(phase_def, tmp_path, callbacks=None, loading_stack=set())
