"""N4 golden atoms #29 (content READ) + #35 (compile-time field-drift gate).

#29: GET /api/skills/{id}/golden/{golden_id}/content returns the persisted per-node
golden ``expected_output`` so the I/O panel can open a golden for editing (read-only,
no write guard). ``?node_id=`` narrows to one node's case.

#35: a persisted golden whose node's CURRENT io.outputs schema now ``required``s a field
the golden is missing (output-schema drift) FAILS compile with a fatal CompileError, so
the N3 compile-gating blocks predict until the golden is reconciled. The gate binds to the
output schema only (prompt/agent-internal edits never appear in ``required``).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from tests.conftest import register_skill_index_entry

if TYPE_CHECKING:
    from pathlib import Path

AGENT_SKILL = "agent-golden-skill"


def _write_agent_skill(skills_dir: Path, *, required_outputs: str) -> None:
    """Register an agent-node skill whose io.outputs ``required`` is parametrizable.

    ``required_outputs`` is the YAML array literal for the SKILL.md output ``required``
    (e.g. ``[segments]`` or ``[segments, headline]``), letting a test add a required
    field after a golden was written to simulate output-schema drift.
    """
    skill_dir = skills_dir / AGENT_SKILL
    (skill_dir / "phases" / "segment").mkdir(parents=True)
    (skill_dir / "GRAPH.md").write_text(
        """---
schema_version: "v0.3.0"
name: agent-golden-skill
description: Agent node with output schema
io:
  inputs:
    type: object
    required: [chapter_content]
    properties:
      chapter_content:
        type: string
    additionalProperties: false
  outputs:
    type: object
    required: [segments]
    properties:
      segments:
        type: array
        items:
          type: object
    additionalProperties: true
phases:
  - segment
---
<phase depends_on="input" output>segment</phase>
""",
        encoding="utf-8",
    )
    (skill_dir / "phases" / "segment" / "SKILL.md").write_text(
        f"""---
io:
  inputs:
    type: object
    required: [chapter_content]
    properties:
      chapter_content:
        type: string
  outputs:
    type: object
    required: {required_outputs}
    properties:
      segments:
        type: array
        items:
          type: object
      headline:
        type: string
tools: []
max_iterations: 5
---
<role>seg editor</role>
<goal>segment</goal>
<step id="S1" name="segment">do it</step>
""",
        encoding="utf-8",
    )


def _write_test_input(skills_dir: Path, content: dict[str, object], *, name: str = "case-a") -> None:
    path = skills_dir / AGENT_SKILL / ".workspace" / "import_files" / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content), encoding="utf-8")


def _write_golden_fixture(skills_dir: Path, node_id: str, expected_output: dict[str, object]) -> None:
    """Persist the on-disk golden layout (baseline/report/case) for one node.

    Test-local writer: the product only creates goldens through the run-promote plan
    (written by the Rust native-fs sole writer), which needs a sealed run. Tests that
    just need "a golden exists on disk" write the same three-file layout directly.
    """
    golden_dir = skills_dir / AGENT_SKILL / ".workspace" / "golden" / node_id
    (golden_dir / "cases").mkdir(parents=True, exist_ok=True)
    case_record = {
        "case_id": node_id,
        "node_id": node_id,
        "phase_id": node_id,
        "expected_output_ref": f"cases/{node_id}.json",
    }
    (golden_dir / "baseline.json").write_text(
        json.dumps(
            {
                "baseline_id": node_id,
                "source_run_id": None,
                "locked": False,
                "cases": [case_record],
            }
        ),
        encoding="utf-8",
    )
    (golden_dir / "report.json").write_text(
        json.dumps(
            {
                "baseline_id": node_id,
                "source_run_id": None,
                "case_count": 1,
                "node_ids": [node_id],
                "created_at": "2026-07-15T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    (golden_dir / "cases" / f"{node_id}.json").write_text(
        json.dumps(
            {
                "case_id": node_id,
                "node_id": node_id,
                "phase_id": node_id,
                "expected_output": expected_output,
            }
        ),
        encoding="utf-8",
    )


def _write_graph_with_source_file_and_missing_runtime_input(skill_dir: Path) -> None:
    (skill_dir / "GRAPH.md").write_text(
        """---
schema_version: "v0.3.0"
name: text-segmentation
description: Compile should aggregate independent input diagnostics
io:
  inputs:
    type: object
    required: [chapter, chapters]
    properties:
      chapter:
        type: object
      chapters:
        type: array
        source: file
        path: imports/chapters/chapters.json
  outputs:
    type: object
    properties:
      prepared:
        type: boolean
phases:
  - setup
---
<phase depends_on="input" output>setup</phase>
""",
        encoding="utf-8",
    )
    import_file = skill_dir / ".workspace" / "import_files" / "chapters.json"
    import_file.parent.mkdir(parents=True, exist_ok=True)
    import_file.write_text(json.dumps({"chapters": []}), encoding="utf-8")


@pytest.fixture
def agent_skill(studio_roots: tuple[Path, Path]) -> str:
    skills_dir, _workspaces = studio_roots
    _write_agent_skill(skills_dir, required_outputs="[segments]")
    register_skill_index_entry(AGENT_SKILL, skills_dir / AGENT_SKILL)
    return AGENT_SKILL


# --------------------------------------------------------------------------- #29


def test_read_golden_content_returns_expected_output(
    agent_skill: str,
    studio_roots: tuple[Path, Path],
    client: TestClient,
) -> None:
    """With a golden persisted on disk, GET /content returns that node's expected_output."""
    skills_dir, _workspaces = studio_roots
    expected: dict[str, object] = {"segments": [{"start": 0}], "headline": "Intro"}
    _write_golden_fixture(skills_dir, "segment", expected)

    response = client.get(f"/api/skills/{agent_skill}/golden/segment/content")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "segment"
    assert body["source_run_id"] is None
    assert body["locked"] is False
    assert len(body["cases"]) == 1
    case = body["cases"][0]
    assert case["node_id"] == "segment"
    assert case["expected_output"] == expected


def test_read_golden_content_node_filter(
    agent_skill: str,
    studio_roots: tuple[Path, Path],
    client: TestClient,
) -> None:
    """?node_id= narrows the returned cases to the requested node only."""
    skills_dir, _workspaces = studio_roots
    _write_golden_fixture(skills_dir, "segment", {"segments": []})

    response = client.get(
        f"/api/skills/{agent_skill}/golden/segment/content",
        params={"node_id": "segment"},
    )

    assert response.status_code == 200
    cases = response.json()["cases"]
    assert [c["node_id"] for c in cases] == ["segment"]


def test_read_golden_content_unknown_baseline_404(agent_skill: str, client: TestClient) -> None:
    response = client.get(f"/api/skills/{agent_skill}/golden/ghost/content")
    assert response.status_code == 404
    assert response.json()["error_code"] == "golden.baseline_not_found"


def test_read_golden_content_unknown_node_422(
    agent_skill: str,
    studio_roots: tuple[Path, Path],
    client: TestClient,
) -> None:
    skills_dir, _workspaces = studio_roots
    _write_golden_fixture(skills_dir, "segment", {"segments": []})

    response = client.get(
        f"/api/skills/{agent_skill}/golden/segment/content",
        params={"node_id": "ghost"},
    )

    assert response.status_code == 422
    assert response.json()["error_code"] == "golden.case_not_found"


def test_read_golden_content_is_read_only_no_write_guard(
    agent_skill: str,
    studio_roots: tuple[Path, Path],
    client: TestClient,
) -> None:
    """The content read needs no X-Studio-Write-Fallback header (it is read-only)."""
    skills_dir, _workspaces = studio_roots
    _write_golden_fixture(skills_dir, "segment", {"segments": []})

    # No write-guard header supplied -> still 200 (would be 409 NATIVE_FS_REQUIRED on a write route).
    response = client.get(f"/api/skills/{agent_skill}/golden/segment/content")
    assert response.status_code == 200


# --------------------------------------------------------------------------- #35


def test_compile_passes_when_golden_satisfies_output_schema(
    agent_skill: str,
    studio_roots: tuple[Path, Path],
    client: TestClient,
) -> None:
    """A golden carrying every required output field compiles cleanly."""
    skills_dir, _workspaces = studio_roots
    _write_test_input(skills_dir, {"chapter_content": "chapter one"})
    _write_golden_fixture(skills_dir, "segment", {"segments": [{"start": 0}]})

    response = client.post(f"/api/skills/{agent_skill}/compile")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_compile_passes_when_no_golden_exists(
    agent_skill: str,
    studio_roots: tuple[Path, Path],
    client: TestClient,
) -> None:
    """No golden persisted -> the field-drift gate is a no-op, compile succeeds."""
    skills_dir, _workspaces = studio_roots
    _write_test_input(skills_dir, {"chapter_content": "chapter one"})
    response = client.post(f"/api/skills/{agent_skill}/compile")
    assert response.status_code == 200


def test_compile_fails_when_required_runtime_input_is_missing(
    agent_skill: str,
    client: TestClient,
) -> None:
    """A skill with required runtime inputs must have a runtime_config root binding."""
    response = client.post(f"/api/skills/{agent_skill}/compile")

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "compile_failed"
    assert "runtime input" in body["detail"].lower()
    assert body["errors"] == [
        {
            "file": ".workspace/runtime_config.json",
            "line": None,
            "field": "chapter_content",
            "severity": "fatal",
            "message": (
                "Graph input schema requires runtime input field 'chapter_content', "
                "but runtime_config has no root import binding. Add a matching file under "
                ".workspace/import_files before predict/run."
            ),
            "error_code": "STUDIO_RUNTIME_INPUT_MISSING",
        }
    ]


def test_compile_fails_when_runtime_input_violates_graph_input_schema(
    agent_skill: str,
    studio_roots: tuple[Path, Path],
    client: TestClient,
) -> None:
    """Input file format drift is compile-fatal, not a predict-time surprise."""
    skills_dir, _workspaces = studio_roots
    _write_test_input(skills_dir, {"chapter_content": 123})

    response = client.post(f"/api/skills/{agent_skill}/compile")

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "compile_failed"
    assert "runtime input" in body["detail"].lower()
    assert body["errors"][0]["file"] == ".workspace/runtime_config.json"
    assert body["errors"][0]["field"] == "chapter_content"
    assert body["errors"][0]["error_code"] == "STUDIO_RUNTIME_INPUT_SCHEMA_INVALID"
    assert "string" in body["errors"][0]["message"]


def test_compile_aggregates_engine_io_error_with_missing_runtime_input(
    studio_roots: tuple[Path, Path],
    client: TestClient,
) -> None:
    """Engine structural failures must not hide independent Studio runtime preflight errors."""
    skills_dir, _workspaces = studio_roots
    skill_dir = skills_dir / "text-segmentation"
    _write_graph_with_source_file_and_missing_runtime_input(skill_dir)

    response = client.post("/api/skills/text-segmentation/compile")

    assert response.status_code == 422
    body = response.json()
    by_code_and_field = {
        (error["error_code"], error["field"])
        for error in body["errors"]
    }
    assert ("F-v3-graph-io-schema-invalid", "io.inputs.properties.chapters.source") in by_code_and_field
    assert ("STUDIO_RUNTIME_INPUT_MISSING", "chapter") in by_code_and_field


def test_compile_fails_when_golden_missing_newly_required_field(
    studio_roots: tuple[Path, Path],
    client: TestClient,
) -> None:
    """Output-schema drift: add a required field after the golden was written -> fatal.

    The golden has only ``segments``; the schema later requires ``segments`` AND
    ``headline``. The missing ``headline`` must fail compile with a fatal CompileError
    keyed ``segment.headline``, blocking predict.
    """
    skills_dir, _workspaces = studio_roots
    _write_agent_skill(skills_dir, required_outputs="[segments, headline]")
    _write_test_input(skills_dir, {"chapter_content": "chapter one"})
    register_skill_index_entry(AGENT_SKILL, skills_dir / AGENT_SKILL)
    # Golden written WITHOUT the (later) required headline field.
    _write_golden_fixture(skills_dir, "segment", {"segments": [{"start": 0}]})

    response = client.post(f"/api/skills/{AGENT_SKILL}/compile")

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "compile_failed"
    assert "golden" in body["detail"].lower()
    fields = {error["field"] for error in body["errors"]}
    assert "segment.headline" in fields
    assert all(error["severity"] == "fatal" for error in body["errors"])
    # The satisfied field never appears as a gap.
    assert "segment.segments" not in fields


def test_compile_fails_when_golden_value_violates_output_schema(
    studio_roots: tuple[Path, Path],
    client: TestClient,
) -> None:
    """Golden output files are part of the preflight path and must match output schema."""
    skills_dir, _workspaces = studio_roots
    _write_agent_skill(skills_dir, required_outputs="[segments]")
    _write_test_input(skills_dir, {"chapter_content": "chapter one"})
    register_skill_index_entry(AGENT_SKILL, skills_dir / AGENT_SKILL)
    _write_golden_fixture(skills_dir, "segment", {"segments": "not an array"})

    response = client.post(f"/api/skills/{AGENT_SKILL}/compile")

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "compile_failed"
    assert "golden" in body["detail"].lower()
    assert body["errors"][0]["field"] == "segment.segments"
    assert body["errors"][0]["error_code"] == "STUDIO_GOLDEN_SCHEMA_INVALID"
    assert "array" in body["errors"][0]["message"]


def test_compile_gate_binds_to_output_schema_not_prompt(
    studio_roots: tuple[Path, Path],
    client: TestClient,
) -> None:
    """Changing only the agent prompt (not the output schema) must NOT trip the gate.

    The golden satisfies the output schema; editing the <role>/<goal>/<step> body leaves
    the io.outputs ``required`` untouched, so compile still succeeds.
    """
    skills_dir, _workspaces = studio_roots
    _write_agent_skill(skills_dir, required_outputs="[segments]")
    _write_test_input(skills_dir, {"chapter_content": "chapter one"})
    register_skill_index_entry(AGENT_SKILL, skills_dir / AGENT_SKILL)
    _write_golden_fixture(skills_dir, "segment", {"segments": [{"start": 0}]})

    skill_md = skills_dir / AGENT_SKILL / "phases" / "segment" / "SKILL.md"
    skill_md.write_text(
        skill_md.read_text(encoding="utf-8").replace(
            "<role>seg editor</role>",
            "<role>a completely rewritten narrative segmentation persona</role>",
        ),
        encoding="utf-8",
    )

    response = client.post(f"/api/skills/{AGENT_SKILL}/compile")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
