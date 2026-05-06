"""Tests for loader rendering of prompt-schema XML tags."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from pydantic import BaseModel, Field, TypeAdapter

from graph_agent.core.loader import (
    _compose_agent_system_prompt,
    _phase_from_agent_skill,
    _phase_from_graph_phase,
    _render_skill_section_xml_tags,
)
from graph_agent.core.manifest import AgentSkillDef, GraphSkillDef, SkillManifest

_SKILL_ADAPTER = TypeAdapter(SkillManifest)


class OutputFormatSchema(BaseModel):
    title: str = Field(description="输出标题")
    score: int = Field(description="质量分")
    notes: str | None = Field(default=None, description="补充说明")


class NotPydanticSchema:
    title: str


def _output_schema_path(schema_cls: type[object]) -> str:
    return f"{schema_cls.__module__}.{schema_cls.__name__}"


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
    assert "<output_format>" not in prompt


def test_output_format_rendered_when_output_schema_set(tmp_path: Path) -> None:
    prompt = _phase_prompt(
        tmp_path,
        output_schema=_output_schema_path(OutputFormatSchema),
    )

    assert "<output_format>" in prompt
    assert "business_data_md" in prompt
    assert "## <item_id 标识符>" in prompt
    assert "- title: <值>" in prompt
    assert "- score: <值>" in prompt
    assert "- notes: <值>" in prompt
    assert "字段说明：" in prompt
    assert "**title**" in prompt
    assert "**score**" in prompt
    assert "**notes**" in prompt
    assert "输出标题" in prompt
    assert "质量分" in prompt
    assert "（必填）" in prompt
    assert "（可选）" in prompt
    assert "</output_format>" in prompt


def test_output_format_resolves_skill_local_schema_from_file(tmp_path: Path) -> None:
    schema_dir = tmp_path / "script"
    schema_dir.mkdir()
    (schema_dir / "schemas.py").write_text(
        "\n".join([
            "from pydantic import BaseModel, Field",
            "",
            "class SegmentationResult(BaseModel):",
            "    chapter_title: str = Field(description='章节标题')",
            "    segment_count: int = Field(description='分段数量')",
            "",
        ]),
        encoding="utf-8",
    )

    sys.modules.pop("script.schemas", None)
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
            "output_schema": "script.schemas.SegmentationResult",
        }],
    })
    assert isinstance(manifest, GraphSkillDef)
    phase = _phase_from_graph_phase(
        manifest.phases[0],
        tmp_path,
        callbacks=None,
        loading_stack=set(),
    )
    prompt = phase.system_prompt or ""

    assert "<output_format>" in prompt
    assert "- chapter_title: <值>" in prompt
    assert "- segment_count: <值>" in prompt
    assert "章节标题" in prompt
    assert "分段数量" in prompt
    assert phase.output_schema is not None
    assert phase.output_schema.__name__ == "SegmentationResult"

    namespaced_keys = [
        key
        for key in sys.modules
        if key.startswith("_graph_agent_skill_.") and key.endswith(".script.schemas")
    ]
    assert not namespaced_keys
    assert "script.schemas" not in sys.modules


def test_output_format_skipped_when_no_output_schema() -> None:
    rendered = _render_skill_section_xml_tags(object())

    assert "<output_format>" not in rendered


def test_output_format_skipped_when_schema_resolves_to_non_basemodel(
    caplog,
) -> None:
    caplog.set_level(logging.WARNING)

    rendered = _render_skill_section_xml_tags(
        type(
            "PhaseLike",
            (),
            {"output_schema": _output_schema_path(NotPydanticSchema)},
        )()
    )

    assert "<output_format>" not in rendered
    assert "not a Pydantic BaseModel" in caplog.text


def test_output_format_skipped_on_import_error(caplog) -> None:
    caplog.set_level(logging.WARNING)

    rendered = _render_skill_section_xml_tags(
        type("PhaseLike", (), {"output_schema": "does.not.Exist"})()
    )

    assert "<output_format>" not in rendered
    assert "failed to resolve output_schema does.not.Exist" in caplog.text


def test_steps_still_renders_as_markdown_after_new_xml_tags(tmp_path: Path) -> None:
    prompt = _phase_prompt(
        tmp_path,
        domain_protocols=["先检查输入"],
        steps=["调用工具", "返回结果"],
    )

    assert "[protocol:P1] 先检查输入" in prompt
    assert "<steps>" in prompt
    assert "1. 调用工具" in prompt
    assert "2. 返回结果" in prompt
    assert prompt.index("</domain_protocols>") < prompt.index("<steps>")
