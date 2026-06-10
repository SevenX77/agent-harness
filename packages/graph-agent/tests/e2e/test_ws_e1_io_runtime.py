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


def _write_importing_logic_skill(root: Path, *, input_file: str) -> None:
    graph_inputs = _schema_yaml({"title": {"type": "string"}}, required=["title"])
    graph_outputs = _schema_yaml({"report_md": {"type": "string"}}, required=["report_md"])
    phase_inputs = _schema_yaml(
        {
            "title": {"type": "string"},
            "body": {
                "type": "string",
                "source": "file",
                "path": input_file,
            },
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
            def report(context):
                return {"report_md": f"## {context['title']}\\n\\n{context['body']}"}
            """
        ).lstrip(),
    )


def _write_artifact_logic_skill(root: Path) -> None:
    graph_inputs = _schema_yaml({"body": {"type": "string"}}, required=["body"])
    graph_outputs = _schema_yaml(
        {
            "report_md": {
                "type": "string",
                "target": "artifact",
                "path": "report.md",
            }
        },
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
        "def report(context):\n    return {'report_md': context['body']}\n",
    )


def test_real_run_imports_workspace_file_into_phase_input(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    skill_root = tmp_path / "skill"
    workspace_dir = tmp_path / "workspace"
    _write(workspace_dir / "inputs" / "body.md", "Imported body.")
    _write_importing_logic_skill(skill_root, input_file="inputs/body.md")

    result = run_skill(
        skill_root,
        workspace_dir=workspace_dir,
        thread_id="ws-e1-io-e2e-import",
        skill_resolver=mock_skill_resolver,
        title="Runtime IO",
    )

    assert result.success is True
    assert result.context["report_md"] == "## Runtime IO\n\nImported body."


def test_real_run_declared_artifact_target_writes_run_artifact(
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
        body="## Artifact\n\nEngine-owned output.",
    )

    artifact_path = workspace_dir / "runs" / run_id / "artifacts" / "report.md"
    assert result.success is True
    assert artifact_path.read_text(encoding="utf-8") == "## Artifact\n\nEngine-owned output."
