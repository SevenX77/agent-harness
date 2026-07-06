"""RED tests for WS-E1-io runtime file import and artifact contracts."""

from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent
from typing import Any

import pytest

from graph_agent.callbacks.events import InputFileInjectedEvent
from graph_agent.core.result import RunResult
from graph_agent.core.runner import run_skill

RAW_BUSINESS_MD = "## main\n- answer: raw ok\n\n<!-- preserve-me -->\n\n- note: keep spacing"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _schema_yaml(properties: dict[str, Any], *, required: list[str] | None = None) -> str:
    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required is not None:
        schema["required"] = required
    return json.dumps(schema, ensure_ascii=False, indent=4).replace("\n", "\n    ")


def _error_text(result: RunResult) -> str:
    payload = result.error.model_dump(mode="json") if result.error is not None else {}
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _runtime_text_file(phase_id: str, field: str, path: str) -> dict[str, Any]:
    return {
        "inputs": {
            "phases": {
                phase_id: {
                    field: {
                        "path": path,
                        "value_type": "string",
                        "content_type": "text/plain",
                    }
                }
            }
        }
    }


def _write_single_reader_skill(root: Path) -> None:
    graph_inputs = _schema_yaml(
        {
            "prefix": {"type": "string"},
            "hidden": {"type": "string"},
        },
        required=["prefix"],
    )
    graph_outputs = _schema_yaml(
        {
            "summary": {"type": "string"},
            "seen_keys": {"type": "array", "items": {"type": "string"}},
        },
        required=["summary", "seen_keys"],
    )
    phase_inputs = _schema_yaml(
        {
            "prefix": {"type": "string"},
            "document_text": {"type": "string"},
        },
        required=["prefix", "document_text"],
    )
    phase_outputs = _schema_yaml(
        {
            "summary": {"type": "string"},
            "seen_keys": {"type": "array", "items": {"type": "string"}},
        },
        required=["summary", "seen_keys"],
    )
    _write(
        root / "GRAPH.md",
        f"""---
schema_version: "v0.3.0"
name: ws-e1-io-reader
io:
  inputs:
    {graph_inputs}
  outputs:
    {graph_outputs}
phases:
  - reader
---
<phase depends_on="input" output>reader</phase>
""",
    )
    _write(
        root / "phases" / "reader" / "LOGIC.md",
        f"""---
io:
  inputs:
    {phase_inputs}
  outputs:
    {phase_outputs}
actions: [reader]
validator: false
---
<action>reader</action>
""",
    )
    _write(
        root / "phases" / "reader" / "actions" / "reader.py",
        dedent(
            """
            def reader(inputs):
                return {
                    "summary": f"{inputs['prefix']}::{inputs['document_text']}",
                    "seen_keys": sorted(inputs),
                }
            """
        ).lstrip(),
    )


def _write_guard_then_reader_skill(root: Path) -> None:
    graph_inputs = _schema_yaml({"prefix": {"type": "string"}}, required=["prefix"])
    graph_outputs = _schema_yaml({"summary": {"type": "string"}})
    guard_inputs = _schema_yaml({"prefix": {"type": "string"}}, required=["prefix"])
    guard_outputs = _schema_yaml({"guarded": {"type": "boolean"}})
    reader_inputs = _schema_yaml(
        {
            "guarded": {"type": "boolean"},
            "document_text": {"type": "string"},
        },
        required=["guarded", "document_text"],
    )
    reader_outputs = _schema_yaml({"summary": {"type": "string"}})
    _write(
        root / "GRAPH.md",
        f"""---
schema_version: "v0.3.0"
name: ws-e1-io-lazy-guard
io:
  inputs:
    {graph_inputs}
  outputs:
    {graph_outputs}
phases:
  - guard
  - reader
---
<phase depends_on="input">guard</phase>
<phase depends_on="guard" output>reader</phase>
""",
    )
    _write(
        root / "phases" / "guard" / "LOGIC.md",
        f"""---
io:
  inputs:
    {guard_inputs}
  outputs:
    {guard_outputs}
actions: [guard]
validator: false
---
<action>guard</action>
""",
    )
    _write(
        root / "phases" / "guard" / "actions" / "guard.py",
        "def guard(inputs):\n    raise RuntimeError('guard stopped before reader')\n",
    )
    _write(
        root / "phases" / "reader" / "LOGIC.md",
        f"""---
io:
  inputs:
    {reader_inputs}
  outputs:
    {reader_outputs}
actions: [reader]
validator: false
---
<action>reader</action>
""",
    )
    _write(
        root / "phases" / "reader" / "actions" / "reader.py",
        "def reader(inputs):\n    return {'summary': inputs['document_text']}\n",
    )


def _write_structured_reader_skill(root: Path) -> None:
    graph_inputs = _schema_yaml({"prefix": {"type": "string"}}, required=["prefix"])
    graph_outputs = _schema_yaml({"summary": {"type": "string"}}, required=["summary"])
    phase_inputs = _schema_yaml(
        {
            "prefix": {"type": "string"},
            "records": {"type": "array"},
            "rows": {"type": "array"},
            "tsv_rows": {"type": "array"},
            "asset": {"type": "object"},
        },
        required=["prefix", "records", "rows", "tsv_rows", "asset"],
    )
    phase_outputs = _schema_yaml({"summary": {"type": "string"}}, required=["summary"])
    _write(
        root / "GRAPH.md",
        f"""---
schema_version: "v0.3.0"
name: ws-e1-io-structured
io:
  inputs:
    {graph_inputs}
  outputs:
    {graph_outputs}
phases:
  - reader
---
<phase depends_on="input" output>reader</phase>
""",
    )
    _write(
        root / "phases" / "reader" / "LOGIC.md",
        f"""---
io:
  inputs:
    {phase_inputs}
  outputs:
    {phase_outputs}
actions: [reader]
validator: false
---
<action>reader</action>
""",
    )
    _write(
        root / "phases" / "reader" / "actions" / "reader.py",
        dedent(
            """
            def reader(inputs):
                return {
                    "summary": (
                        f"{inputs['prefix']}|"
                        f"{inputs['records'][1]['title']}|"
                        f"{inputs['rows'][0]['name']}|"
                        f"{inputs['tsv_rows'][0]['code']}|"
                        f"{inputs['asset']['content_type']}"
                    )
                }
            """
        ).lstrip(),
    )


def test_file_import_injects_before_phase_slice_and_combines_with_parent_blackboard(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    skill_root = tmp_path / "skill"
    workspace_dir = tmp_path / "workspace"
    _write(workspace_dir / "import_files" / ".phase" / "reader" / "story.md", "chapter alpha")
    _write_single_reader_skill(skill_root)

    result = run_skill(
        skill_root,
        workspace_dir=workspace_dir,
        thread_id="ws-e1-io-import-success",
        skill_resolver=mock_skill_resolver,
        runtime_config=_runtime_text_file("reader", "document_text", "import_files/.phase/reader/story.md"),
        prefix="story",
        hidden="must-not-leak",
    )

    assert result.success is True
    assert result.context["summary"] == "story::chapter alpha"
    assert result.context["seen_keys"] == ["document_text", "prefix"]


def test_runtime_config_imports_structured_and_file_ref_formats(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    skill_root = tmp_path / "skill"
    workspace_dir = tmp_path / "workspace"
    import_dir = workspace_dir / "import_files" / ".phase" / "reader"
    _write(import_dir / "records.jsonl", '{"title":"first"}\n{"title":"second"}\n')
    _write(import_dir / "people.csv", "name,age\nAda,37\n")
    _write(import_dir / "codes.tsv", "code\tlabel\nA1\tAlpha\n")
    _write(import_dir / "brief.pdf", "%PDF-1.4\n")
    _write_structured_reader_skill(skill_root)

    result = run_skill(
        skill_root,
        workspace_dir=workspace_dir,
        thread_id="ws-e1-io-structured",
        skill_resolver=mock_skill_resolver,
        runtime_config={
            "inputs": {
                "phases": {
                    "reader": {
                        "records": {
                            "path": "import_files/.phase/reader/records.jsonl",
                            "value_type": "jsonl",
                        },
                        "rows": {
                            "path": "import_files/.phase/reader/people.csv",
                            "value_type": "csv",
                        },
                        "tsv_rows": {
                            "path": "import_files/.phase/reader/codes.tsv",
                            "value_type": "tsv",
                        },
                        "asset": {
                            "path": "import_files/.phase/reader/brief.pdf",
                            "value_type": "file_ref",
                            "content_type": "application/pdf",
                        },
                    }
                }
            }
        },
        prefix="fmt",
    )

    assert result.success is True
    assert result.context["summary"] == "fmt|second|Ada|A1|application/pdf"


def test_file_import_is_lazy_when_upstream_failure_prevents_target_phase(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    skill_root = tmp_path / "skill"
    workspace_dir = tmp_path / "workspace"
    events: list[object] = []
    _write_guard_then_reader_skill(skill_root)

    result = run_skill(
        skill_root,
        workspace_dir=workspace_dir,
        thread_id="ws-e1-io-lazy-upstream-fail",
        event_subscriber=events.append,
        skill_resolver=mock_skill_resolver,
        runtime_config=_runtime_text_file("reader", "document_text", "../outside/missing.md"),
        prefix="story",
    )

    assert result.success is False
    assert "guard stopped before reader" in _error_text(result)
    assert not any(isinstance(event, InputFileInjectedEvent) for event in events)


def test_file_import_workspace_escape_fails_with_stable_engine_error(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    skill_root = tmp_path / "skill"
    workspace_dir = tmp_path / "workspace"
    _write_single_reader_skill(skill_root)

    result = run_skill(
        skill_root,
        workspace_dir=workspace_dir,
        thread_id="ws-e1-io-escape",
        skill_resolver=mock_skill_resolver,
        runtime_config=_runtime_text_file("reader", "document_text", "../outside.md"),
        prefix="story",
        hidden="unused",
    )

    error_text = _error_text(result)
    assert result.success is False
    assert "escapes workspace_dir" in error_text
    assert "Traceback" not in error_text
    assert "KeyError" not in error_text


@pytest.mark.parametrize(
    ("file_ref", "write_payload", "expected_message"),
    [
        ("inputs/missing.md", None, "not found"),
        ("inputs/binary.bin", b"\xff\x00\xff", "binary"),
    ],
)
def test_file_import_io_errors_are_stable_and_do_not_become_business_input(
    tmp_path: Path,
    mock_skill_resolver: object,
    file_ref: str,
    write_payload: bytes | None,
    expected_message: str,
) -> None:
    skill_root = tmp_path / "skill"
    workspace_dir = tmp_path / "workspace"
    if write_payload is not None:
        binary_path = workspace_dir / file_ref
        binary_path.parent.mkdir(parents=True, exist_ok=True)
        binary_path.write_bytes(write_payload)
    _write_single_reader_skill(skill_root)

    result = run_skill(
        skill_root,
        workspace_dir=workspace_dir,
        thread_id=f"ws-e1-io-error-{Path(file_ref).stem}",
        skill_resolver=mock_skill_resolver,
        runtime_config=_runtime_text_file("reader", "document_text", file_ref),
        prefix="story",
        hidden="unused",
    )

    error_text = _error_text(result)
    assert result.success is False
    assert expected_message in error_text
    assert "[read_file Error]" not in error_text
    assert "Traceback" not in error_text
    assert "KeyError" not in error_text


def test_markdown_artifact_uses_validated_business_data_md_instead_of_parsed_json(
    tmp_path: Path,
) -> None:
    from graph_agent.io.artifact_manifest import write_manifest_artifacts

    artifacts_dir = tmp_path / "artifacts"
    blackboard = {
        "report": {"answer": "raw ok", "note": "keep spacing"},
        "business_data_md": RAW_BUSINESS_MD,
    }
    spec = [
        {"stem": "report", "mode": "single", "format": "md", "fields": ["business_data_md"]}
    ]

    written = write_manifest_artifacts(
        spec, blackboard, artifacts_dir, timestamp="20260702_120000"
    )

    expected_path = artifacts_dir / "report_latest_20260702_120000.md"
    assert written == [expected_path]
    assert expected_path.read_text(encoding="utf-8") == RAW_BUSINESS_MD
