"""E2E RED tests for WS-E1-io runtime IO contracts."""

from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent
from typing import Any

from graph_agent.core.runner import run_skill


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _schema_yaml(properties: dict[str, Any], *, required: list[str] | None = None) -> str:
    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required is not None:
        schema["required"] = required
    return json.dumps(schema, ensure_ascii=False, indent=4).replace("\n", "\n    ")


def _write_importing_logic_skill(root: Path) -> None:
    graph_inputs = _schema_yaml({"title": {"type": "string"}}, required=["title"])
    graph_outputs = _schema_yaml({"report_md": {"type": "string"}}, required=["report_md"])
    phase_inputs = _schema_yaml(
        {
            "title": {"type": "string"},
            "body": {"type": "string"},
        },
        required=["title", "body"],
    )
    phase_outputs = _schema_yaml({"report_md": {"type": "string"}}, required=["report_md"])
    _write(
        root / "GRAPH.md",
        f"""---
schema_version: "v0.3.0"
name: ws-e1-io-e2e-import
io:
  inputs:
    {graph_inputs}
  outputs:
    {graph_outputs}
phases:
  - report
---
<phase depends_on="input" output>report</phase>
""",
    )
    _write(
        root / "phases" / "report" / "LOGIC.md",
        f"""---
io:
  inputs:
    {phase_inputs}
  outputs:
    {phase_outputs}
actions: [report]
validator: false
---
<action>report</action>
""",
    )
    _write(
        root / "phases" / "report" / "actions" / "report.py",
        dedent(
            """
            def report(inputs):
                return {"report_md": f"## {inputs['title']}\\n\\n{inputs['body']}"}
            """
        ).lstrip(),
    )


def _write_artifact_logic_skill(root: Path) -> None:
    graph_inputs = _schema_yaml({"body": {"type": "string"}}, required=["body"])
    graph_outputs = _schema_yaml(
        {"report_md": {"type": "string"}},
        required=["report_md"],
    )
    phase_inputs = _schema_yaml({"body": {"type": "string"}}, required=["body"])
    phase_outputs = graph_outputs
    _write(
        root / "GRAPH.md",
        f"""---
schema_version: "v0.3.0"
name: ws-e1-io-e2e-artifact
io:
  inputs:
    {graph_inputs}
  outputs:
    {graph_outputs}
phases:
  - report
---
<phase depends_on="input" output>report</phase>
""",
    )
    _write(
        root / "phases" / "report" / "LOGIC.md",
        f"""---
io:
  inputs:
    {phase_inputs}
  outputs:
    {phase_outputs}
actions: [report]
validator: false
---
<action>report</action>
""",
    )
    _write(
        root / "phases" / "report" / "actions" / "report.py",
        "def report(inputs):\n    return {'report_md': inputs['body']}\n",
    )


def test_real_run_imports_workspace_file_into_phase_input(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    skill_root = tmp_path / "skill"
    workspace_dir = tmp_path / "workspace"
    _write(workspace_dir / "import_files" / ".phase" / "report" / "body.md", "Imported body.")
    _write_importing_logic_skill(skill_root)

    result = run_skill(
        skill_root,
        workspace_dir=workspace_dir,
        thread_id="ws-e1-io-e2e-import",
        skill_resolver=mock_skill_resolver,
        runtime_config={
            "inputs": {
                "active": {
                    "phases": {
                        "report": {
                            "body": {
                                "path": "import_files/.phase/report/body.md",
                                "value_type": "string",
                            }
                        }
                    },
                }
            }
        },
        title="Runtime IO",
    )

    assert result.success is True
    assert result.context["report_md"] == "## Runtime IO\n\nImported body."


def test_real_run_manifest_artifact_writes_fixed_format_file(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    skill_root = tmp_path / "skill"
    workspace_dir = tmp_path / "workspace"
    run_id = "ws-e1-io-e2e-artifact"
    _write_artifact_logic_skill(skill_root)

    result = run_skill(
        skill_root,
        workspace_dir=workspace_dir,
        thread_id=run_id,
        skill_resolver=mock_skill_resolver,
        runtime_config={
            "artifacts": [
                {"stem": "report", "mode": "single", "format": "md", "fields": ["report_md"]}
            ]
        },
        body="## Artifact\n\nEngine-owned output.",
    )

    assert result.success is True
    artifacts_dir = workspace_dir / "runs" / run_id / "artifacts"
    latest = sorted(artifacts_dir.glob("report_latest_*.md"))
    assert len(latest) == 1, list(artifacts_dir.iterdir())
    assert latest[0].read_text(encoding="utf-8") == "## Artifact\n\nEngine-owned output."


def test_real_run_imports_root_workspace_file_into_graph_input(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    skill_root = tmp_path / "skill"
    workspace_dir = tmp_path / "workspace"
    body_path = workspace_dir / "import_files" / "body.md"
    body_path.parent.mkdir(parents=True, exist_ok=True)
    body_path.write_bytes(b"\xef\xbb\xbfRoot imported input.")
    _write_artifact_logic_skill(skill_root)

    result = run_skill(
        skill_root,
        workspace_dir=workspace_dir,
        thread_id="ws-e1-io-e2e-root-import",
        skill_resolver=mock_skill_resolver,
        runtime_config={
            "inputs": {
                "active": {
                    "root": {
                        "body": {
                            "path": "import_files/body.md",
                            "value_type": "string",
                        }
                    }
                }
            }
        },
    )

    assert result.success is True
    assert result.context["report_md"] == "Root imported input."


def _write_batch_importing_logic_skill(root: Path) -> None:
    graph_inputs = _schema_yaml({"title": {"type": "string"}}, required=["title"])
    graph_outputs = _schema_yaml({"count": {"type": "integer"}}, required=["count"])
    phase_inputs = _schema_yaml(
        {
            "title": {"type": "string"},
            "chapters": {"type": "array"},
        },
        required=["title", "chapters"],
    )
    phase_outputs = _schema_yaml({"count": {"type": "integer"}}, required=["count"])
    _write(
        root / "GRAPH.md",
        f"""---
schema_version: "v0.3.0"
name: ws-e1-io-e2e-batch-import
io:
  inputs:
    {graph_inputs}
  outputs:
    {graph_outputs}
phases:
  - report
---
<phase depends_on="input" output>report</phase>
""",
    )
    _write(
        root / "phases" / "report" / "LOGIC.md",
        f"""---
io:
  inputs:
    {phase_inputs}
  outputs:
    {phase_outputs}
actions: [report]
validator: false
---
<action>report</action>
""",
    )
    _write(
        root / "phases" / "report" / "actions" / "report.py",
        dedent(
            """
            def report(inputs):
                chapters = inputs["chapters"]
                numbers = [c["chapter_number"] for c in chapters]
                assert numbers == sorted(numbers), numbers
                return {"count": len(chapters)}
            """
        ).lstrip(),
    )


def test_real_run_batch_file_import_aggregates_numbered_json_files(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    """A batch runtime_config declaration (dir + pattern) aggregates the
    numbered files into a parsed array, ordered by extracted number
    (design: input region F5 batch numbers kept, PM 2026-07-02)."""
    skill_root = tmp_path / "skill"
    workspace_dir = tmp_path / "workspace"
    batch_dir = workspace_dir / "import_files" / ".phase" / "report" / "abc_segmentation"
    for n in (7, 1, 2):
        _write(
            batch_dir / f"chapter_{n:03d}_latest_20260414_0649{n:02d}.json",
            json.dumps({"chapter_number": n, "paragraphs": []}),
        )
    _write_batch_importing_logic_skill(skill_root)

    result = run_skill(
        skill_root,
        workspace_dir=workspace_dir,
        thread_id="ws-e1-io-e2e-batch",
        skill_resolver=mock_skill_resolver,
        runtime_config={
            "inputs": {
                "active": {
                    "phases": {
                        "report": {
                            "chapters": {
                                "dir": "import_files/.phase/report/abc_segmentation",
                                "pattern": "chapter_{n}_latest_*.json",
                                "value_type": "json",
                            }
                        }
                    },
                }
            }
        },
        title="Batch",
    )

    assert result.success is True, getattr(result, "error", None)
    assert result.context["count"] == 3
