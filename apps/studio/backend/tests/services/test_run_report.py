"""The run report is a readable projection of one run's sealed artifacts.

Design: docs/studio/mvp1/02_capabilities/run-execution/mvp1-alignment.md F6
(RUN_EXECUTION-5/6/7). It adds no facts of its own — everything it prints is
read back out of the run directory, so it can be regenerated at any time and
deleting it loses nothing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.core.adapters.run_artifact_store_local import LocalRunArtifactStore


def _seal_run(run_dir: Path, *, status: str = "success", error: dict[str, str] | None = None) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    events = [
        {"event_type": "run_started", "timestamp": "2026-08-08T10:00:00+00:00", "run_id": run_dir.name},
        {
            "event_type": "input_dispatch",
            "timestamp": "2026-08-08T10:00:01+00:00",
            "to_phase": "draft",
            "dispatched_keys": ["topic"],
        },
        {"event_type": "phase_start", "timestamp": "2026-08-08T10:00:01+00:00", "phase_name": "draft"},
        {"event_type": "agent_loop_iteration", "timestamp": "2026-08-08T10:00:02+00:00", "phase_name": "draft", "iteration": 1},
        {
            "event_type": "llm_call",
            "timestamp": "2026-08-08T10:00:03+00:00",
            "phase_name": "draft",
            "input_tokens": 10,
            "output_tokens": 5,
            "resolved_model": "claude-sonnet-5",
        },
        {
            "event_type": "tool_call",
            "timestamp": "2026-08-08T10:00:04+00:00",
            "phase_name": "draft",
            "tool_name": "read_file",
            "result": "ok",
        },
        {"event_type": "agent_loop_iteration", "timestamp": "2026-08-08T10:00:05+00:00", "phase_name": "draft", "iteration": 2},
        {"event_type": "phase_end", "timestamp": "2026-08-08T10:00:11+00:00", "phase_name": "draft"},
        {"event_type": "phase_start", "timestamp": "2026-08-08T10:00:11+00:00", "phase_name": "review"},
        {
            "event_type": "llm_call",
            "timestamp": "2026-08-08T10:00:12+00:00",
            "phase_name": "review",
            "input_tokens": 3,
            "output_tokens": 2,
            "resolved_model": "deepseek-v4-flash",
        },
        {"event_type": "phase_end", "timestamp": "2026-08-08T10:00:14+00:00", "phase_name": "review"},
        {
            "event_type": "run_ended",
            "timestamp": "2026-08-08T10:00:14+00:00",
            "run_id": run_dir.name,
            "status": "completed" if status == "success" else "crashed",
            "wall_time_seconds": 14.0,
        },
    ]
    (run_dir / "trace.jsonl").write_text(
        "".join(json.dumps(event, ensure_ascii=False) + "\n" for event in events), encoding="utf-8"
    )
    metadata: dict[str, object] = {
        "run_id": run_dir.name,
        "status": status,
        "started_at": "2026-08-08T10:00:00Z",
        "kind": "run",
        "git_status": "committed",
        "metrics": {"input_tokens": 13, "output_tokens": 7, "total_tokens": 20, "wall_time_sec": 14.0},
    }
    if error is not None:
        metadata["error"] = error
    (run_dir / "run_metadata.json").write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
    (run_dir / "metrics.json").write_text(
        json.dumps({"input_tokens": 13, "output_tokens": 7, "total_tokens": 20, "wall_time_sec": 14.0}),
        encoding="utf-8",
    )
    # Shape mirrors a real snapshot: every declared input FIELD carries its own
    # binding, and several fields usually come from the same file.
    (run_dir / "runtime_config.snapshot.json").write_text(
        json.dumps(
            {
                "inputs": {
                    "import_root": "import_files",
                    "active": {
                        "root": {
                            "topic": {
                                "path": "import_files/chapter.json",
                                "sha256": "abc123",
                                "json_path": ["topic"],
                            },
                            "chapter_number": {
                                "path": "import_files/chapter.json",
                                "sha256": "abc123",
                                "json_path": ["chapter_number"],
                            },
                        },
                        "phases": {"draft": {}, "review": {}},
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "artifacts").mkdir(exist_ok=True)
    (run_dir / "artifacts" / "result.json").write_text('{"ok": true}', encoding="utf-8")


def test_report_summarizes_the_whole_run(tmp_path: Path) -> None:
    from app.services.run_report import build_run_report

    run_dir = tmp_path / "runs" / "2026-08-08T10-00-00_abcd"
    _seal_run(run_dir)

    report = build_run_report(run_dir)

    assert "2026-08-08T10-00-00_abcd" in report
    assert "success" in report.lower()
    # totals come from the llm_call events, not from metrics.json
    assert "13" in report and "7" in report
    assert "14.0" in report or "14.00" in report


def test_report_breaks_the_run_down_by_node(tmp_path: Path) -> None:
    from app.services.run_report import build_run_report

    run_dir = tmp_path / "runs" / "run-nodes"
    _seal_run(run_dir)

    report = build_run_report(run_dir)

    assert "draft" in report
    assert "claude-sonnet-5" in report
    assert "review" in report
    assert "deepseek-v4-flash" in report
    # draft: 2 loop iterations, 1 llm call, 1 tool call, 10s wall
    draft_line = next(line for line in report.splitlines() if line.startswith("| `draft`"))
    assert "10" in draft_line and "5" in draft_line


def test_report_links_inputs_and_artifacts_relative_to_the_run_dir(tmp_path: Path) -> None:
    from app.services.run_report import build_run_report

    run_dir = tmp_path / "runs" / "run-links"
    _seal_run(run_dir)

    report = build_run_report(run_dir)

    assert "import_files/chapter.json" in report
    assert "abc123" in report
    # one line per file, naming the fields it supplied — not one line per field
    assert report.count("import_files/chapter.json") == 1
    assert "topic" in report and "chapter_number" in report
    assert "(artifacts/result.json)" in report
    assert "(trace.jsonl)" in report
    assert str(tmp_path) not in report


def test_report_states_why_a_failed_run_failed(tmp_path: Path) -> None:
    from app.services.run_report import build_run_report

    run_dir = tmp_path / "runs" / "run-failed"
    _seal_run(
        run_dir,
        status="failed",
        error={"code": "llm.provider_invoke_failed", "message": "All providers failed for role=analyst"},
    )

    report = build_run_report(run_dir)

    assert "llm.provider_invoke_failed" in report
    assert "All providers failed for role=analyst" in report


def test_report_is_stable_for_the_same_sealed_run(tmp_path: Path) -> None:
    from app.services.run_report import build_run_report

    run_dir = tmp_path / "runs" / "run-stable"
    _seal_run(run_dir)

    assert build_run_report(run_dir) == build_run_report(run_dir)


def test_writing_the_report_puts_it_in_the_run_dir(tmp_path: Path) -> None:
    from app.services.run_report import write_run_report

    run_dir = tmp_path / "runs" / "run-write"
    _seal_run(run_dir)

    path = write_run_report(run_dir)

    assert path == run_dir / "report.md"
    assert path.read_text(encoding="utf-8").startswith("# Run report")


def _registered_run_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A skill in the index with one sealed run, so RunDetail can be read back."""
    from app.core import config
    from app.core.backends import clear_backend_caches

    from tests.conftest import register_skill_index_entry

    skill_dir = tmp_path / "skills" / "demo"
    run_dir = skill_dir / ".workspace" / "runs" / "run-detail"
    (skill_dir / "GRAPH.md").parent.mkdir(parents=True, exist_ok=True)
    (skill_dir / "GRAPH.md").write_text("# Demo\n", encoding="utf-8")
    _seal_run(run_dir)
    # RunDetail reads a run through the artifact store, so the fixture seals it
    # the same way a real run does rather than faking a manifest.
    store = LocalRunArtifactStore(root=run_dir.parent.parent)
    store.begin_run(run_dir.name)
    store.put_batch(
        run_dir.name,
        {
            "final_state.json": json.dumps({"answer": "ok"}).encode("utf-8"),
            "trace.jsonl": (run_dir / "trace.jsonl").read_bytes(),
        },
    )
    store.seal_run(run_dir.name)
    global_config_dir = tmp_path / "global-config"
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", global_config_dir)
    monkeypatch.setattr(config, "SKILL_INDEX_PATH", global_config_dir / "skill_index.json")
    register_skill_index_entry("demo.skill", skill_dir)
    clear_backend_caches()
    return run_dir


def test_run_detail_points_at_the_report_so_the_ui_can_open_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The report exists on disk; a reader with no shell needs its path (D5)."""
    from app.services.run_manager import RunManager
    from app.services.run_report import write_run_report

    run_dir = _registered_run_dir(tmp_path, monkeypatch)
    write_run_report(run_dir)

    detail = RunManager().get_run_detail(skill_id="demo.skill", run_id=run_dir.name)

    assert detail.metadata.report_path == str(run_dir / "report.md")


def test_run_detail_reports_no_path_when_the_run_left_no_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.run_manager import RunManager

    run_dir = _registered_run_dir(tmp_path, monkeypatch)

    detail = RunManager().get_run_detail(skill_id="demo.skill", run_id=run_dir.name)

    assert detail.metadata.report_path is None
