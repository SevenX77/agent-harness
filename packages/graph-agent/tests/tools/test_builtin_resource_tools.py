from __future__ import annotations

from pathlib import Path

import pytest
from graph_agent.core.exceptions import GraphAgentFatalError
from graph_agent.core.manifest import ExampleSpec, ReferenceSpec
from graph_agent.tools.builtin.read_example import build_read_example_tool
from graph_agent.tools.builtin.read_reference import build_read_reference_tool


def test_read_reference_reads_current_phase_registry(tmp_path: Path) -> None:
    (tmp_path / "refs").mkdir()
    (tmp_path / "refs" / "r1.md").write_text("Reference body", encoding="utf-8")
    tool = build_read_reference_tool(
        skill_root=tmp_path,
        references=[ReferenceSpec(id="R1", path="refs/r1.md", summary="Rules")],
    )

    result = tool.invoke({"reference_id": "R1"})

    assert "Reference R1: Rules" in result
    assert "Reference body" in result


def test_read_reference_unknown_id_fails(tmp_path: Path) -> None:
    tool = build_read_reference_tool(skill_root=tmp_path, references=[])

    with pytest.raises(GraphAgentFatalError, match=r"\[F-v3-resource-reference-not-found\]"):
        tool.invoke({"reference_id": "R1"})


def test_read_example_reads_inline_and_document_examples(tmp_path: Path) -> None:
    (tmp_path / "examples").mkdir()
    (tmp_path / "examples" / "e2.md").write_text("Document example", encoding="utf-8")
    tool = build_read_example_tool(
        skill_root=tmp_path,
        examples=[
            ExampleSpec(id="E1", type="inline", content="Inline example"),
            ExampleSpec(id="E2", type="document", path="examples/e2.md", summary="Long"),
        ],
    )

    inline = tool.invoke({"example_id": "E1"})
    document = tool.invoke({"example_id": "E2"})

    assert "Inline example" in inline
    assert "Document example" in document
