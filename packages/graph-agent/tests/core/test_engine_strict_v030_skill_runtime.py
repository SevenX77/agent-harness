from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent
from typing import Any

import pytest
from langchain_core.messages import AIMessage

from graph_agent.core.compiler import compile_skill
from graph_agent.core.exceptions import GraphAgentFatalError, SkillLoadError
from graph_agent.core.graph_assembler import assemble_graph
from graph_agent.core.runner import run_skill
from graph_agent.core.schema_engine import SchemaEngine


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_phase_config_agent_skill(root: Path) -> None:
    _write(
        root / "GRAPH.md",
        """---
schema_version: "v0.3.0"
name: strict-phase-config
io:
  inputs:
    type: object
    properties:
      topic:
        type: string
  outputs:
    type: object
    properties:
      answer:
        type: string
phases:
  - main
---
<phase depends_on="input" output>main</phase>
""",
    )
    _write(
        root / "phases" / "main" / "SKILL.md",
        """---
phase_config:
  io:
    inputs:
      type: object
      properties:
        topic:
          type: string
    outputs:
      type: object
      properties:
        answer:
          type: string
---
<role>Strict contract verifier.</role>
<goal>Return an answer.</goal>
""",
    )


def test_agent_skill_phase_config_is_compile_fatal(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    _write_phase_config_agent_skill(tmp_path)

    with pytest.raises(SkillLoadError) as exc_info:
        compile_skill(tmp_path, cache=False, skill_resolver=mock_skill_resolver)

    assert exc_info.value.payload.code == "[F-v3-agent-schema-unknown-field]"
    assert exc_info.value.payload.field_path == "phase_config"


def _write_validator_logic_skill(
    root: Path,
    *,
    validator_source: str,
    output_properties: dict[str, Any] | None = None,
) -> None:
    properties = output_properties or {"answer": {"type": "string"}}
    output_schema = json.dumps(
        {
            "type": "object",
            "required": sorted(properties),
            "properties": properties,
        },
        ensure_ascii=False,
        indent=4,
    ).replace("\n", "\n    ")
    _write(
        root / "GRAPH.md",
        f"""---
schema_version: "v0.3.0"
name: strict-validator
io:
  inputs:
    type: object
    properties:
      topic:
        type: string
  outputs:
    {output_schema}
phases:
  - score
---
<phase depends_on="input" output>score</phase>
""",
    )
    _write(
        root / "phases" / "score" / "LOGIC.md",
        f"""---
io:
  inputs:
    type: object
    properties:
      topic:
        type: string
  outputs:
    {output_schema}
actions:
  - score
validator: true
---
<action>score</action>
""",
    )
    _write(
        root / "phases" / "score" / "actions" / "score.py",
        "def score(inputs):\n    return {'answer': inputs.get('topic', '').strip()}\n",
    )
    _write(root / "phases" / "score" / "validator.py", dedent(validator_source).lstrip())


def _invoke_logic(root: Path, mock_skill_resolver: object) -> dict[str, Any]:
    compiled = compile_skill(root, cache=False, skill_resolver=mock_skill_resolver)
    graph = assemble_graph(compiled, skill_resolver=mock_skill_resolver).graph
    return graph.invoke(
        {"data": {"topic": " alpha "}, "flow": {}, "messages": [], "run_id": "r1"}
    )


def test_phase_validator_py_dict_return_enriches_output(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    _write_validator_logic_skill(
        tmp_path,
        validator_source="""
            def validate(output, state_slice, **kwargs):
                assert state_slice == {"topic": " alpha "}
                return {"answer": output["answer"].upper()}
        """,
    )

    result = _invoke_logic(tmp_path, mock_skill_resolver)

    assert result["data"].model_dump()["answer"] == "ALPHA"
    assert result["data"]["phase_outputs"]["score"] == {"answer": "ALPHA"}


def test_phase_validator_py_extra_key_uses_phase_kind_error(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    _write_validator_logic_skill(
        tmp_path,
        validator_source="""
            def validate(output, state_slice, **kwargs):
                return {"answer": output["answer"], "extra": "nope"}
        """,
    )

    with pytest.raises(GraphAgentFatalError) as exc_info:
        _invoke_logic(tmp_path, mock_skill_resolver)

    assert exc_info.value.payload.code == "[F-v3-logic-validator-failed]"
    assert "extra" in str(exc_info.value)


def test_phase_validator_py_exception_uses_phase_kind_error(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    _write_validator_logic_skill(
        tmp_path,
        validator_source="""
            def validate(output, state_slice, **kwargs):
                raise ValueError("bad answer")
        """,
    )

    with pytest.raises(GraphAgentFatalError) as exc_info:
        _invoke_logic(tmp_path, mock_skill_resolver)

    assert exc_info.value.payload.code == "[F-v3-logic-validator-failed]"
    assert "bad answer" in str(exc_info.value)


def _segmentation_result_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["segmentation_result"],
        "properties": {
            "segmentation_result": {
                "type": "object",
                "required": ["paragraphs"],
                "properties": {
                    "paragraphs": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["paragraph_id", "text"],
                            "properties": {
                                "paragraph_id": {"type": "string"},
                                "text": {"type": "string"},
                            },
                        },
                    }
                },
            }
        },
    }


def test_schema_engine_accepts_json_schema_array_items_object_shape() -> None:
    schema = SchemaEngine().parse_from_md(json.dumps(_segmentation_result_schema()))

    good = {
        "segmentation_result": {
            "paragraphs": [{"paragraph_id": "p1", "text": "Opening paragraph."}]
        }
    }
    bad = {"segmentation_result": {"paragraphs": [{"paragraph_id": "p1"}]}}

    good_result = SchemaEngine().validate(good, schema)
    bad_result = SchemaEngine().validate(bad, schema)

    assert good_result.ok is True
    assert bad_result.ok is False
    assert "segmentation_result.paragraphs.0.text" in bad_result.field_errors


class _SegmentReviewChatModel:
    def __init__(self) -> None:
        self.invocations = 0

    def bind_tools(self, tools: list[Any], **kwargs: Any) -> _SegmentReviewChatModel:
        del tools, kwargs
        return self

    def invoke(self, messages: list[Any]) -> AIMessage:
        self.invocations += 1
        joined = "\n".join(str(getattr(message, "content", "")) for message in messages)
        if "Review segmentation quality" in joined:
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "finish_task",
                        "args": {
                            "reasoning": "review complete",
                            "diagnostics_md": "reviewed deterministic fixture",
                            "business_data_md": (
                                "## review_decision\n"
                                "```json\n"
                                '{"approved": true}\n'
                                "```\n"
                            ),
                        },
                        "id": "finish-review",
                    }
                ],
            )
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "finish_task",
                    "args": {
                        "reasoning": "segmented text",
                        "diagnostics_md": "one paragraph fixture",
                        "business_data_md": (
                            "## segmentation_result\n"
                            "```json\n"
                            '{"paragraphs": [{"paragraph_id": "p1", "text": "Alpha beta."}]}\n'
                            "```\n"
                        ),
                    },
                    "id": "finish-segment",
                }
            ],
        )


def _write_text_segmentation_like_skill(root: Path) -> None:
    _write(
        root / "GRAPH.md",
        """---
schema_version: "v0.3.0"
name: strict-text-segmentation-like
io:
  inputs:
    type: object
    required: [raw_text]
    properties:
      raw_text:
        type: string
  outputs:
    type: object
    required: [segmentation_result]
    properties:
      segmentation_result:
        type: object
        required: [paragraphs]
        properties:
          paragraphs:
            type: array
            items:
              type: object
              required: [paragraph_id, text]
              properties:
                paragraph_id:
                  type: string
                text:
                  type: string
phases:
  - setup
  - segment
  - review
---
<phase depends_on="input">setup</phase>
<phase depends_on="setup">segment</phase>
<phase depends_on="segment" output>review</phase>
""",
    )
    _write(
        root / "phases" / "setup" / "LOGIC.md",
        """---
io:
  inputs:
    type: object
    required: [raw_text]
    properties:
      raw_text:
        type: string
  outputs:
    type: object
    required: [normalized_text]
    properties:
      normalized_text:
        type: string
actions:
  - normalize
validator: false
---
<action>normalize</action>
""",
    )
    _write(
        root / "phases" / "setup" / "actions" / "normalize.py",
        "def normalize(inputs):\n    return {'normalized_text': inputs['raw_text'].strip()}\n",
    )
    _write(
        root / "phases" / "segment" / "SKILL.md",
        """---
max_iterations: 2
io:
  inputs:
    type: object
    required: [normalized_text]
    properties:
      normalized_text:
        type: string
  outputs:
    type: object
    required: [segmentation_result]
    properties:
      segmentation_result:
        type: object
        required: [paragraphs]
        properties:
          paragraphs:
            type: array
            items:
              type: object
              required: [paragraph_id, text]
              properties:
                paragraph_id:
                  type: string
                text:
                  type: string
---
<role>Segmenter.</role>
<goal>Segment paragraphs and call @tool:finish_task.</goal>
""",
    )
    _write(
        root / "phases" / "review" / "SKILL.md",
        """---
max_iterations: 2
io:
  inputs:
    type: object
    required: [segmentation_result]
    properties:
      segmentation_result:
        type: object
  outputs:
    type: object
    required: [review_decision]
    properties:
      review_decision:
        type: object
        required: [approved]
        properties:
          approved:
            type: boolean
---
<role>Reviewer.</role>
<goal>Review segmentation quality and call @tool:finish_task.</goal>
""",
    )


def test_text_segmentation_like_agent_chain_uses_phase_outputs_then_root_outputs(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    skill_root = tmp_path / "skill"
    _write_text_segmentation_like_skill(skill_root)

    compile_skill(skill_root, cache=False, skill_resolver=mock_skill_resolver)
    assert list(skill_root.rglob("__pycache__")) == []

    result = run_skill(
        skill_root,
        workspace_dir=tmp_path / "workspace",
        mock_llm=_SegmentReviewChatModel(),
        skill_resolver=mock_skill_resolver,
        raw_text="  Alpha beta.  ",
    )

    assert result.success is True
    assert result.context["segmentation_result"] == {
        "paragraphs": [{"paragraph_id": "p1", "text": "Alpha beta."}]
    }
    assert result.context["phase_outputs"]["segment"]["segmentation_result"] == (
        result.context["segmentation_result"]
    )
    assert result.context["phase_outputs"]["review"] == {"review_decision": {"approved": True}}
