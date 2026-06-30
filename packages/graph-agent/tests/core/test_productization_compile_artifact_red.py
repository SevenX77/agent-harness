from __future__ import annotations

import importlib
import json
import os
import shutil
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_logic_skill(root: Path, *, ui_metadata: dict[str, Any] | None = None) -> None:
    metadata = ui_metadata or {"ui": {"nodes": {"draft": {"x": 1, "y": 2}}}}
    _write_text(
        root / "GRAPH.md",
        f"""---
schema_version: "v0.3.0"
name: productization-compile-artifact
metadata: {metadata!r}
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
  - draft
---
<phase depends_on="input" output>draft</phase>
""",
    )
    _write_text(
        root / "phases" / "draft" / "LOGIC.md",
        """---
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
<action>draft</action>
""",
    )
    _write_text(
        root / "phases" / "draft" / "actions" / "draft.py",
        "def draft(inputs):\n"
        "    return {'answer': 'draft:' + str(inputs.get('topic', ''))}\n",
    )


def _compile_artifact(source_root: Path, *, skill_resolver: Any) -> Any:
    artifacts = importlib.import_module("graph_agent.core.artifacts")
    return artifacts.compile_artifact(source_root=source_root, skill_resolver=skill_resolver)


def test_compile_artifact_hash_is_stable_across_temp_roots_and_mtime(
    tmp_path: Path,
    mock_skill_resolver: Any,
) -> None:
    first_root = tmp_path / "first" / "skill"
    second_root = tmp_path / "second" / "skill"
    _write_logic_skill(first_root)
    shutil.copytree(first_root, second_root)

    first = _compile_artifact(first_root, skill_resolver=mock_skill_resolver)
    os.utime(second_root / "GRAPH.md", (1_900_000_000, 1_900_000_000))
    second = _compile_artifact(second_root, skill_resolver=mock_skill_resolver)

    assert first.artifact_ref.content_hash == second.artifact_ref.content_hash
    assert first.execution_fingerprint == second.execution_fingerprint


def test_compile_artifact_archive_does_not_use_deflate_compression_for_identity_bytes(
    tmp_path: Path,
    mock_skill_resolver: Any,
) -> None:
    skill_root = tmp_path / "skill"
    _write_logic_skill(skill_root)

    manifest = _compile_artifact(skill_root, skill_resolver=mock_skill_resolver)

    assert manifest.artifact_bytes is not None
    archive_path = tmp_path / "artifact.zip"
    archive_path.write_bytes(manifest.artifact_bytes)
    with zipfile.ZipFile(archive_path) as archive:
        compression = {info.filename: info.compress_type for info in archive.infolist()}

    assert compression
    assert set(compression.values()) == {zipfile.ZIP_STORED}


def test_execution_fingerprint_ignores_ui_metadata(
    tmp_path: Path,
    mock_skill_resolver: Any,
) -> None:
    first_root = tmp_path / "ui-a" / "skill"
    second_root = tmp_path / "ui-b" / "skill"
    _write_logic_skill(first_root, ui_metadata={"ui": {"nodes": {"draft": {"x": 10, "y": 20}}}})
    _write_logic_skill(second_root, ui_metadata={"ui": {"nodes": {"draft": {"x": 900, "y": 1200}}}})

    first = _compile_artifact(first_root, skill_resolver=mock_skill_resolver)
    second = _compile_artifact(second_root, skill_resolver=mock_skill_resolver)

    assert first.execution_fingerprint == second.execution_fingerprint


def test_execution_fingerprint_changes_when_graph_execution_semantics_change(
    tmp_path: Path,
    mock_skill_resolver: Any,
) -> None:
    first_root = tmp_path / "semantic-a" / "skill"
    second_root = tmp_path / "semantic-b" / "skill"
    _write_logic_skill(first_root)
    shutil.copytree(first_root, second_root)

    graph_path = second_root / "GRAPH.md"
    graph_path.write_text(
        """---
schema_version: "v0.3.0"
name: productization-compile-artifact
metadata: {'ui': {'nodes': {'draft': {'x': 1, 'y': 2}}}}
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
  - review
  - draft
---
<phase depends_on="input">review</phase>
<phase depends_on="review" output>draft</phase>
""",
        encoding="utf-8",
    )
    _write_text(
        second_root / "phases" / "review" / "LOGIC.md",
        """---
io:
  inputs:
    type: object
    properties:
      topic:
        type: string
  outputs:
    type: object
    properties:
      topic:
        type: string
---
<action>review</action>
""",
    )
    _write_text(
        second_root / "phases" / "review" / "actions" / "review.py",
        "def review(inputs):\n"
        "    return {'topic': inputs.get('topic', '')}\n",
    )

    first = _compile_artifact(first_root, skill_resolver=mock_skill_resolver)
    second = _compile_artifact(second_root, skill_resolver=mock_skill_resolver)

    assert first.execution_fingerprint != second.execution_fingerprint


def test_execution_fingerprint_changes_when_phase_io_schema_changes(
    tmp_path: Path,
    mock_skill_resolver: Any,
) -> None:
    first_root = tmp_path / "io-a" / "skill"
    second_root = tmp_path / "io-b" / "skill"
    _write_logic_skill(first_root)
    shutil.copytree(first_root, second_root)

    logic_path = second_root / "phases" / "draft" / "LOGIC.md"
    logic_path.write_text(
        logic_path.read_text(encoding="utf-8").replace(
            "answer:\n        type: string",
            "answer:\n        type: number",
        ),
        encoding="utf-8",
    )

    first = _compile_artifact(first_root, skill_resolver=mock_skill_resolver)
    second = _compile_artifact(second_root, skill_resolver=mock_skill_resolver)

    assert first.execution_fingerprint != second.execution_fingerprint


def test_execution_fingerprint_changes_when_action_code_changes(
    tmp_path: Path,
    mock_skill_resolver: Any,
) -> None:
    first_root = tmp_path / "action-a" / "skill"
    second_root = tmp_path / "action-b" / "skill"
    _write_logic_skill(first_root)
    shutil.copytree(first_root, second_root)

    action_path = second_root / "phases" / "draft" / "actions" / "draft.py"
    action_path.write_text(
        "def draft(inputs):\n"
        "    return {'answer': 'changed:' + str(inputs.get('topic', ''))}\n",
        encoding="utf-8",
    )

    first = _compile_artifact(first_root, skill_resolver=mock_skill_resolver)
    second = _compile_artifact(second_root, skill_resolver=mock_skill_resolver)

    assert first.execution_fingerprint != second.execution_fingerprint


def test_compile_artifact_writes_source_map_for_runtime_nodes(
    tmp_path: Path,
    mock_skill_resolver: Any,
) -> None:
    skill_root = tmp_path / "skill"
    _write_logic_skill(skill_root)

    manifest = _compile_artifact(skill_root, skill_resolver=mock_skill_resolver)

    source_map_path = _file_uri_path(manifest.source_map_ref)
    assert source_map_path.is_file()
    source_map = json.loads(source_map_path.read_text(encoding="utf-8"))
    graph_lines = (skill_root / "GRAPH.md").read_text(encoding="utf-8").splitlines()
    draft_line = next(index for index, line in enumerate(graph_lines, start=1) if line.strip() == "- draft")

    assert source_map["schema_version"] == "mvp1.source_map.v1"
    assert source_map["nodes"]["draft"]["node_id"] == "draft"
    assert source_map["nodes"]["draft"]["source"]["path"] == "GRAPH.md"
    assert source_map["nodes"]["draft"]["source"]["line"] == draft_line
    assert source_map["nodes"]["draft"]["source"]["span"] == {
        "start_line": draft_line,
        "end_line": draft_line,
    }

    manifest_path = _file_uri_path(manifest.artifact_ref.manifest_ref)
    assert manifest_path.is_file()


def test_compile_artifact_does_not_write_manifest_side_effects_into_source_root(
    tmp_path: Path,
    mock_skill_resolver: Any,
) -> None:
    skill_root = tmp_path / "skill"
    _write_logic_skill(skill_root)

    manifest = _compile_artifact(skill_root, skill_resolver=mock_skill_resolver)

    manifest_path = _file_uri_path(manifest.artifact_ref.manifest_ref)
    source_map_path = _file_uri_path(manifest.source_map_ref)
    assert manifest_path.is_file()
    assert source_map_path.is_file()
    assert skill_root not in manifest_path.parents
    assert skill_root not in source_map_path.parents
    assert not (skill_root / ".graph_agent").exists()


def _file_uri_path(ref: str) -> Path:
    parsed = urlparse(ref)
    assert parsed.scheme == "file"
    return Path(url2pathname(unquote(parsed.path)))
