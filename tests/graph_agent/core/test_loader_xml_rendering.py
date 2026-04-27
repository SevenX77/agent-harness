"""Tests for loader rendering of prompt-schema XML tags."""

from __future__ import annotations

from pathlib import Path

from pydantic import TypeAdapter

from graph_agent.core.loader import (
    _compose_agent_system_prompt,
    _phase_from_agent_skill,
    _phase_from_graph_phase,
)
from graph_agent.core.manifest import AgentSkillDef, SkillManifest


_SKILL_ADAPTER = TypeAdapter(SkillManifest)


def _agent_prompt(**profile_fields: object) -> str:
    manifest = _SKILL_ADAPTER.validate_python({
        "schema_version": "2.0",
        "name": "agent",
        "description": "agent",
        "type": "agent",
        "agent_profile": {
            "role": "Role",
            "goal": "Goal",
            **profile_fields,
        },
    })
    assert isinstance(manifest, AgentSkillDef)
    return _compose_agent_system_prompt(manifest)


def _phase_prompt(tmp_path: Path, **phase_fields: object) -> str:
    manifest = _SKILL_ADAPTER.validate_python({
        "schema_version": "2.0",
        "name": "graph",
        "description": "graph",
        "type": "graph",
        "io": {"inputs": [], "outputs": []},
        "phases": [{
            "mode": "llm",
            "name": "phase",
            "prompt": "Base prompt.",
            **phase_fields,
        }],
    })
    phase = _phase_from_graph_phase(
        manifest.phases[0],
        tmp_path,
        callbacks=None,
        loading_stack=set(),
    )
    return phase.system_prompt or ""


def test_domain_protocols_renders_to_xml_tag() -> None:
    prompt = _agent_prompt(domain_protocols=["先读输入", "再输出结论"])

    assert "<domain_protocols>" in prompt
    assert "[protocol:P1] 先读输入" in prompt
    assert "[protocol:P2] 再输出结论" in prompt


def test_few_shot_examples_renders_to_xml_tag(tmp_path: Path) -> None:
    prompt = _phase_prompt(
        tmp_path,
        few_shot_examples=["Input A -> Output A", "Input B -> Output B"],
    )

    assert "<examples>" in prompt
    assert '<example id="1">Input A -> Output A</example>' in prompt
    assert '<example id="2">Input B -> Output B</example>' in prompt


def test_references_renders_to_knowledge_base_tag(tmp_path: Path) -> None:
    prompt = _phase_prompt(tmp_path, references=["docs/a.md", "docs/b.md"])

    assert "<knowledge_base>" in prompt
    assert "调用 read_file 查阅" in prompt
    assert "- docs/a.md" in prompt
    assert "- docs/b.md" in prompt


def test_graph_phase_references_thread_to_runtime_phase(tmp_path: Path) -> None:
    manifest = _SKILL_ADAPTER.validate_python({
        "schema_version": "2.0",
        "name": "graph",
        "description": "graph",
        "type": "graph",
        "io": {"inputs": [], "outputs": []},
        "phases": [{
            "mode": "llm",
            "name": "phase",
            "references": ["references/guide.md"],
        }],
    })

    phase = _phase_from_graph_phase(
        manifest.phases[0],
        tmp_path,
        callbacks=None,
        loading_stack=set(),
    )

    assert phase.references == ["references/guide.md"]
    assert phase.skill_base_dir == tmp_path


def test_agent_profile_references_thread_to_runtime_phase(tmp_path: Path) -> None:
    manifest = _SKILL_ADAPTER.validate_python({
        "schema_version": "2.0",
        "name": "agent",
        "description": "agent",
        "type": "agent",
        "agent_profile": {
            "role": "Role",
            "goal": "Goal",
            "references": ["references/agent.md"],
        },
    })
    assert isinstance(manifest, AgentSkillDef)

    phase = _phase_from_agent_skill(
        manifest,
        tmp_path,
        callbacks=None,
        loading_stack=set(),
    )

    assert phase.references == ["references/agent.md"]
    assert phase.skill_base_dir == tmp_path


def test_graph_phase_context_access_threads_to_runtime_phase(tmp_path: Path) -> None:
    manifest = _SKILL_ADAPTER.validate_python({
        "schema_version": "2.0",
        "name": "graph",
        "description": "graph",
        "type": "graph",
        "io": {"inputs": [], "outputs": []},
        "phases": [{
            "mode": "llm",
            "name": "phase",
            "context_access": ["artifact", "working_memory"],
        }],
    })

    phase = _phase_from_graph_phase(
        manifest.phases[0],
        tmp_path,
        callbacks=None,
        loading_stack=set(),
    )

    assert phase.context_access == ["artifact", "working_memory"]


def test_agent_profile_context_access_threads_to_runtime_phase(tmp_path: Path) -> None:
    manifest = _SKILL_ADAPTER.validate_python({
        "schema_version": "2.0",
        "name": "agent",
        "description": "agent",
        "type": "agent",
        "agent_profile": {
            "role": "Role",
            "goal": "Goal",
            "context_access": ["artifact"],
        },
    })
    assert isinstance(manifest, AgentSkillDef)

    phase = _phase_from_agent_skill(
        manifest,
        tmp_path,
        callbacks=None,
        loading_stack=set(),
    )

    assert phase.context_access == ["artifact"]


def test_context_access_renders_to_context_access_tag(tmp_path: Path) -> None:
    prompt = _phase_prompt(
        tmp_path,
        context_access=["artifact", "working_memory"],
    )

    assert "<context_access>" in prompt
    assert "read_artifact" in prompt
    assert "read_working_memory" in prompt


def test_empty_fields_dont_render(tmp_path: Path) -> None:
    prompt = _phase_prompt(tmp_path)

    assert "<domain_protocols>" not in prompt
    assert "<examples>" not in prompt
    assert "<knowledge_base>" not in prompt
    assert "<context_access>" not in prompt


def test_steps_still_renders_as_markdown_after_new_xml_tags(tmp_path: Path) -> None:
    prompt = _phase_prompt(
        tmp_path,
        domain_protocols=["先检查输入"],
        steps=["调用工具", "返回结果"],
    )

    assert "[protocol:P1] 先检查输入" in prompt
    assert "## 工作流" in prompt
    assert "1. 调用工具" in prompt
    assert "2. 返回结果" in prompt
    assert prompt.index("</domain_protocols>") < prompt.index("## 工作流")
