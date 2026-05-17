from __future__ import annotations

import json
from pathlib import Path

import pytest
from graph_agent.core.compiler import compile_skill
from graph_agent.core.exceptions import GraphAgentFatalError
from graph_agent.core.graph_assembler import assemble_graph

REPO_ROOT = Path(__file__).resolve().parents[4]


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _base(root: Path, outputs: dict[str, object]) -> None:
    _write(
        root / "GRAPH.md",
        """---
schema_version: "2.1"
name: actions-keys-test
---
<input src="io/inputs.json" />
<output src="io/outputs.json" />
<phase id="logic" src="phases/logic" depends_on="" />
""",
    )
    _write(root / "io" / "inputs.json", "{}\n")
    _write(root / "io" / "outputs.json", json.dumps(outputs))
    _write(
        root / "phases" / "logic" / "LOGIC.md",
        """---
mode: logic
---
<python_callable>
write_value
</python_callable>
""",
    )


def _action(root: Path, body: str) -> None:
    _write(root / "phases" / "logic" / "actions" / "write_value.py", body)


def _outputs(*keys: str) -> dict[str, object]:
    return {
        "type": "object",
        "properties": {key: {"type": "integer"} for key in keys},
    }


def test_output_schema_keys_are_extracted_from_properties(tmp_path: Path) -> None:
    _base(tmp_path, _outputs("foo", "bar"))
    _action(tmp_path, "def write_value(context):\n    return {'foo': 1}\n")

    compiled = compile_skill(tmp_path, cache=False)

    assert compiled.raw["io"]["output_schema_keys"] == ["bar", "foo"]


def test_static_action_return_key_must_be_declared(tmp_path: Path) -> None:
    _base(tmp_path, _outputs("foo"))
    _action(tmp_path, "def write_value(context):\n    return {'missing': 1}\n")

    with pytest.raises(GraphAgentFatalError, match=r"\[F-v21-actions-keys\].*missing"):
        compile_skill(tmp_path, cache=False)


def test_runtime_action_dynamic_return_key_must_be_declared(tmp_path: Path) -> None:
    _base(tmp_path, _outputs("foo"))
    _action(
        tmp_path,
        "def write_value(context):\n    key = 'missing'\n    return {key: 1}\n",
    )
    graph = assemble_graph(compile_skill(tmp_path, cache=False)).graph

    with pytest.raises(GraphAgentFatalError, match=r"\[F-v21-actions-keys\].*missing"):
        graph.invoke({"data": {}, "flow": {}, "messages": [], "run_id": "keys"})


def test_context_write_intermediate_state_is_not_output_key_checked(tmp_path: Path) -> None:
    _base(tmp_path, _outputs("foo"))
    _action(tmp_path, "def write_value(context):\n    context.set('missing', 1)\n")
    graph = assemble_graph(compile_skill(tmp_path, cache=False)).graph

    result = graph.invoke({"data": {}, "flow": {}, "messages": [], "run_id": "keys"})

    assert result["data"]["missing"] == 1


def test_context_update_key_must_be_declared(tmp_path: Path) -> None:
    _base(tmp_path, _outputs("foo"))
    _action(tmp_path, "def write_value(context):\n    context.update(missing=1)\n")

    with pytest.raises(GraphAgentFatalError, match=r"\[F-v21-actions-keys\].*missing"):
        compile_skill(tmp_path, cache=False)


def test_text_segmentation_broken_skill_fails_compile_on_context_update() -> None:
    compiled = compile_skill(REPO_ROOT / "skills" / "text-segmentation", cache=False)

    assert compiled.manifest.name == "text-segmentation"
    assert "chapter_lines" in compiled.raw["io"]["output_schema_keys"]
