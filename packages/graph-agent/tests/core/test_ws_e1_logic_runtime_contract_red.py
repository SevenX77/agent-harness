"""RED tests for WS-E1 Step3 LOGIC pure-return runtime contract."""

from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent
from typing import Any

import pytest

from graph_agent.core.compiler import compile_skill
from graph_agent.core.exceptions import GraphAgentFatalError, SkillLoadError
from graph_agent.core.graph_assembler import assemble_graph


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _schema_yaml(properties: dict[str, Any]) -> str:
    schema = {"type": "object", "properties": properties}
    return json.dumps(schema, ensure_ascii=False, indent=4).replace("\n", "\n    ")


def _logic_skill(
    root: Path,
    *,
    input_properties: dict[str, Any],
    output_properties: dict[str, Any],
    actions: dict[str, str],
) -> None:
    action_names = list(actions)
    graph_input_yaml = _schema_yaml(input_properties)
    graph_output_yaml = _schema_yaml(output_properties)
    action_yaml = "\n".join(f"  - {name}" for name in action_names)
    action_body = "\n".join(f"<action>{name}</action>" for name in action_names)

    _write(
        root / "GRAPH.md",
        f"""---
schema_version: "v0.3.0"
name: ws-e1-step3-logic-runtime-red
io:
  inputs:
    {graph_input_yaml}
  outputs:
    {graph_output_yaml}
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
    {graph_input_yaml}
  outputs:
    {graph_output_yaml}
actions:
{action_yaml}
validator: false
---
{action_body}
""",
    )
    for name, body in actions.items():
        _write(
            root / "phases" / "score" / "actions" / f"{name}.py",
            dedent(body).lstrip(),
        )


def _invoke(root: Path, mock_skill_resolver: object, data: dict[str, Any]) -> dict[str, Any]:
    compiled = compile_skill(root, cache=False, skill_resolver=mock_skill_resolver)
    graph = assemble_graph(compiled, skill_resolver=mock_skill_resolver).graph
    return graph.invoke({"data": data, "flow": {}, "messages": [], "run_id": "r1"})


def _business_data(result: dict[str, Any]) -> dict[str, Any]:
    data = result["data"]
    if hasattr(data, "model_dump"):
        return data.model_dump()
    return dict(data)


def test_logic_action_receives_plain_dict_inputs_and_writes_only_returned_output(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    _logic_skill(
        tmp_path,
        input_properties={"text": {"type": "string"}},
        output_properties={"report": {"type": "string"}},
        actions={
            "score": """
                def score(inputs):
                    return {"report": f"{type(inputs).__name__}:{inputs['text']}"}
            """,
        },
    )

    result = _invoke(tmp_path, mock_skill_resolver, {"inputs": {"text": "hello"}})

    assert _business_data(result)["report"] == "dict:hello"
    assert result["data"]["phase_outputs"]["score"] == {"report": "dict:hello"}


def test_logic_action_sees_only_declared_phase_inputs(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    _logic_skill(
        tmp_path,
        input_properties={"public": {"type": "string"}},
        output_properties={"report": {"type": "string"}},
        actions={
            "score": """
                def score(inputs):
                    return {"report": ",".join(sorted(inputs.keys()))}
            """,
        },
    )

    result = _invoke(
        tmp_path,
        mock_skill_resolver,
        {
            "inputs": {"public": "visible", "root_secret": "hidden"},
            "phase_outputs": {"upstream": {"upstream_secret": "hidden"}},
        },
    )

    assert _business_data(result)["report"] == "public"


def test_logic_action_chain_reads_previous_returned_outputs_as_input_increment(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    _logic_skill(
        tmp_path,
        input_properties={"text": {"type": "string"}},
        output_properties={
            "normalized": {"type": "string"},
            "report": {"type": "string"},
        },
        actions={
            "normalize": """
                def normalize(inputs):
                    return {"normalized": inputs["text"].strip().upper()}
            """,
            "score": """
                def score(inputs):
                    return {"report": inputs.get("normalized", "missing")}
            """,
        },
    )

    result = _invoke(tmp_path, mock_skill_resolver, {"inputs": {"text": " hello "}})

    assert _business_data(result)["report"] == "HELLO"
    assert result["data"]["phase_outputs"]["score"] == {"report": "HELLO"}


@pytest.mark.parametrize(
    ("case_name", "mutation_body"),
    [
        (
            "set",
            """
            def score(inputs):
                inputs.set("report", "from-set")
                return {}
            """,
        ),
        (
            "update",
            """
            def score(inputs):
                inputs.update(report="from-update")
                return {}
            """,
        ),
        (
            "item_assignment",
            """
            def score(inputs):
                inputs["report"] = "from-item"
                return {}
            """,
        ),
        (
            "setdefault",
            """
            def score(inputs):
                inputs.setdefault("report", "from-setdefault")
                return {}
            """,
        ),
    ],
)
def test_action_inputs_mutation_is_compile_fatal(
    tmp_path: Path,
    mock_skill_resolver: object,
    case_name: str,
    mutation_body: str,
) -> None:
    _logic_skill(
        tmp_path,
        input_properties={"text": {"type": "string"}},
        output_properties={"report": {"type": "string"}},
        actions={"score": mutation_body},
    )

    with pytest.raises(SkillLoadError) as exc_info:
        compile_skill(tmp_path, cache=False, skill_resolver=mock_skill_resolver)

    assert case_name in str(exc_info.value)
    assert exc_info.value.payload.code == "[F-v3-logic-action-purity-violation]"


@pytest.mark.parametrize("param_name", ["context", "ctx"])
def test_logic_action_context_or_ctx_parameter_is_compile_fatal(
    tmp_path: Path,
    mock_skill_resolver: object,
    param_name: str,
) -> None:
    _logic_skill(
        tmp_path,
        input_properties={"text": {"type": "string"}},
        output_properties={"report": {"type": "string"}},
        actions={
            "score": f"""
                def score({param_name}):
                    return {{"report": {param_name}["text"]}}
            """,
        },
    )

    with pytest.raises(SkillLoadError) as exc_info:
        compile_skill(tmp_path, cache=False, skill_resolver=mock_skill_resolver)

    assert exc_info.value.payload.code == "[F-v3-logic-action-entrypoint-missing]"
    assert "inputs" in str(exc_info.value)


def test_compile_importing_actions_does_not_write_pycache_under_skill_source(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    _logic_skill(
        tmp_path,
        input_properties={"text": {"type": "string"}},
        output_properties={"report": {"type": "string"}},
        actions={
            "score": """
                def score(inputs):
                    return {"report": inputs["text"]}
            """,
        },
    )

    compile_skill(tmp_path, cache=False, skill_resolver=mock_skill_resolver)

    assert list(tmp_path.rglob("__pycache__")) == []


def test_undeclared_return_key_still_uses_logic_output_field_error(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    _logic_skill(
        tmp_path,
        input_properties={"text": {"type": "string"}},
        output_properties={"report": {"type": "string"}},
        actions={
            "score": """
                def score(inputs):
                    return {"missing": inputs["text"]}
            """,
        },
    )

    with pytest.raises(GraphAgentFatalError) as exc_info:
        _invoke(tmp_path, mock_skill_resolver, {"inputs": {"text": "hello"}})

    assert exc_info.value.payload.code == "[F-v3-logic-output-field-undeclared]"
    assert "missing" in str(exc_info.value)


def test_non_dict_return_still_uses_logic_action_return_invalid_error(
    tmp_path: Path, mock_skill_resolver: object
) -> None:
    _logic_skill(
        tmp_path,
        input_properties={"text": {"type": "string"}},
        output_properties={"report": {"type": "string"}},
        actions={
            "score": """
                def score(inputs):
                    return ["not", "a", "dict"]
            """,
        },
    )

    with pytest.raises(GraphAgentFatalError) as exc_info:
        _invoke(tmp_path, mock_skill_resolver, {"inputs": {"text": "hello"}})

    assert exc_info.value.payload.code == "[F-v3-logic-action-return-invalid]"
