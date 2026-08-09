from __future__ import annotations

from pathlib import Path

from app.core import native_fs_write_boundary
from app.core.native_fs_write_boundary import classify_workspace_write_path

BACKEND_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "app").is_dir() and (parent / "tests").is_dir()
)


def test_workspace_run_artifacts_do_not_require_native_fs_source_writer() -> None:
    runtime_paths = (
        ".workspace/runs/run-1/input_data.json",
        ".workspace/runs/run-1/final_state.json",
        ".workspace/runs/run-1/trace.jsonl",
        ".workspace/runs/run-1/metrics.json",
        ".workspace/runs/run-1/run_metadata.json",
    )

    for workspace_path in runtime_paths:
        classification = classify_workspace_write_path(workspace_path)

        assert classification.kind == "runtime_artifact"
        assert classification.requires_native_fs_source_writer is False


def test_studio_owned_workspace_data_requires_native_fs_source_writer() -> None:
    studio_workspace_paths = (
        ".workspace/import_files/case.json",
        ".workspace/golden/run-1/baseline.json",
        ".workspace/golden/run-1/report.json",
        ".workspace/golden/run-1/cases/setup.json",
    )

    for workspace_path in studio_workspace_paths:
        classification = classify_workspace_write_path(workspace_path)

        assert classification.kind == "studio_workspace_data"
        assert classification.requires_native_fs_source_writer is True


def test_source_files_require_native_fs_source_writer() -> None:
    source_paths = (
        "GRAPH.md",
        "phases/draft/LOGIC.md",
        "io/outputs.json",
    )

    for workspace_path in source_paths:
        classification = classify_workspace_write_path(workspace_path)

        assert classification.kind == "source_file"
        assert classification.requires_native_fs_source_writer is True


def test_nested_workspace_runs_segment_inside_source_path_remains_source_file() -> None:
    classification = classify_workspace_write_path("phases/draft/.workspace/runs/LOGIC.md")

    assert classification.kind == "source_file"
    assert classification.requires_native_fs_source_writer is True


def test_workspace_paths_with_parent_segments_are_invalid() -> None:
    classification = classify_workspace_write_path(".workspace/runs/../../GRAPH.md")

    assert classification.kind == "invalid_path"
    assert classification.requires_native_fs_source_writer is False


def test_run_manager_literal_candidate_scanner_ignores_runtime_artifact_filenames() -> None:
    candidates = native_fs_write_boundary.collect_native_fs_source_writer_candidates(
        BACKEND_ROOT / "app" / "services" / "run_manager.py"
    )
    runtime_artifact_names = {
        "final_state.json",
        "trace.jsonl",
        "metrics.json",
        "run_metadata.json",
    }

    assert [
        candidate
        for candidate in candidates
        if any(
            runtime_artifact_name in candidate
            for runtime_artifact_name in runtime_artifact_names
        )
    ] == []


def test_literal_candidate_scanner_uses_candidate_diagnostics(tmp_path: Path) -> None:
    path = tmp_path / "example.py"
    path.write_text('SOURCE_PATH = "GRAPH.md"\n', encoding="utf-8")

    candidates = native_fs_write_boundary.collect_native_fs_source_writer_candidates(path)

    assert len(candidates) == 1
    assert "source-writer candidate" in candidates[0]
    assert "writes" not in candidates[0]
    assert "without native-fs" not in candidates[0]
