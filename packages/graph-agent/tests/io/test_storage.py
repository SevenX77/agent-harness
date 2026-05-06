"""Unit tests for graph_agent.io.storage.StorageManager.

Covered scenarios (match tasks.md Task 3.1):

* default on-disk layout (no pipeline_prefix)
* pipeline_prefix injection via get_output_dir
* ``.golden`` runs are never pruned
* retention trims oldest non-golden runs when the count exceeds the budget
* cleanup emits an INFO log line naming the deleted run_id and its byte size
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import pytest

# Allow running the tests without the package installed: add the in-tree
# source root that holds ``graph_agent/``.
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src" / "core"))

from graph_agent.io.storage import StorageManager, sanitize_run_id  # noqa: E402


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    return tmp_path / "ws"


class TestStorageManagerBasics:
    def test_default_layout_without_pipeline_prefix(self, workspace: Path) -> None:
        mgr = StorageManager(workspace, skill_id="story", run_id="20260423_1200")
        out = mgr.get_output_dir()
        assert out == workspace / "runs" / "story" / "20260423_1200"
        assert out.is_dir()

    def test_pipeline_prefix_rooted_under_runs(self, workspace: Path) -> None:
        mgr = StorageManager(workspace, skill_id="story", run_id="20260423_1200")
        out = mgr.get_output_dir(pipeline_prefix="ep1")
        assert out == workspace / "runs" / "ep1" / "story" / "20260423_1200"

    def test_pipeline_prefix_rebinding_is_refused(self, workspace: Path) -> None:
        mgr = StorageManager(workspace, skill_id="s", run_id="r1")
        mgr.get_output_dir(pipeline_prefix="ep1")
        with pytest.raises(ValueError):
            mgr.get_output_dir(pipeline_prefix="ep2")

    def test_save_artifact_writes_str_bytes_and_json(self, workspace: Path) -> None:
        mgr = StorageManager(workspace, skill_id="s", run_id="r1")
        mgr.get_output_dir()

        text_path = mgr.save_artifact("report.md", "# hello")
        bytes_path = mgr.save_artifact("blob.bin", b"\x00\x01\x02")
        json_path = mgr.save_artifact("data.json", {"k": 1})

        assert text_path.read_text(encoding="utf-8") == "# hello"
        assert bytes_path.read_bytes() == b"\x00\x01\x02"
        assert json.loads(json_path.read_text(encoding="utf-8")) == {"k": 1}

    def test_save_artifact_per_phase(self, workspace: Path) -> None:
        mgr = StorageManager(workspace, skill_id="s", run_id="r1")
        mgr.get_output_dir()
        path = mgr.save_artifact("out.txt", "hi", phase="extraction")
        assert path == workspace / "runs" / "s" / "r1" / "phases" / "extraction" / "out.txt"
        assert path.read_text(encoding="utf-8") == "hi"

    def test_load_latest_returns_newest_run(self, workspace: Path) -> None:
        # Seed two runs; the lexicographically greater name should win.
        mgr_old = StorageManager(workspace, skill_id="s", run_id="20260101")
        mgr_old.get_output_dir()
        mgr_old.save_artifact("report.md", "old")

        mgr_new = StorageManager(workspace, skill_id="s", run_id="20260401")
        mgr_new.get_output_dir()
        mgr_new.save_artifact("report.md", "new")

        mgr_query = StorageManager(workspace, skill_id="s", run_id="_probe")
        mgr_query.get_output_dir()
        # Sharing the cached run, load_latest still picks the newest artifact
        # across all sibling runs.
        assert mgr_query.load_latest(phase=None, name="report.md") == "new"


class TestRetention:
    def _make_run(self, workspace: Path, run_id: str, payload: str = "x") -> None:
        mgr = StorageManager(workspace, skill_id="s", run_id=run_id)
        mgr.get_output_dir()
        mgr.save_artifact("file.txt", payload)

    def test_over_limit_runs_are_pruned(self, workspace: Path) -> None:
        # history_retention=2 means any third run triggers pruning of the
        # oldest. We seed 4 runs via 4 manager constructions.
        for ts in ("20260101", "20260201", "20260301", "20260401"):
            StorageManager(
                workspace,
                skill_id="s",
                run_id=ts,
                history_retention=2,
            ).get_output_dir()

        surviving = sorted(
            p.name for p in (workspace / "runs" / "s").iterdir() if p.is_dir()
        )
        assert surviving == ["20260301", "20260401"]

    def test_golden_runs_are_never_pruned(self, workspace: Path) -> None:
        # One regular + one golden run exist first. Then a newer regular run
        # is added with retention=1, so the older regular run must be
        # pruned while the golden directory is preserved regardless.
        StorageManager(workspace, skill_id="s", run_id="20260101", history_retention=1).get_output_dir()
        # Manually create a golden dir so we exercise the protection logic
        # without needing a dedicated API for promoting a run to golden.
        golden_dir = workspace / "runs" / "s" / "baseline.golden"
        golden_dir.mkdir(parents=True)
        (golden_dir / "note.md").write_text("keep me", encoding="utf-8")

        StorageManager(workspace, skill_id="s", run_id="20260301", history_retention=1).get_output_dir()

        surviving = sorted(p.name for p in (workspace / "runs" / "s").iterdir() if p.is_dir())
        assert "baseline.golden" in surviving
        assert "20260301" in surviving  # newest regular survives
        assert "20260101" not in surviving  # pruned as the only over-budget regular run

    def test_cleanup_logs_deleted_run_id_and_bytes(
        self, workspace: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        # Seed three runs, retention=1, so two should be pruned with INFO logs.
        for ts, payload in (
            ("20260101", "a"),
            ("20260201", "bb"),
            ("20260301", "ccc"),
        ):
            StorageManager(
                workspace,
                skill_id="s",
                run_id=ts,
                history_retention=1,
            ).get_output_dir()
            StorageManager(workspace, skill_id="s", run_id=ts).save_artifact("x.txt", payload)

        caplog.clear()
        with caplog.at_level(logging.INFO, logger="graph_agent.io.storage"):
            # Trigger cleanup explicitly by constructing a new manager + get_output_dir.
            StorageManager(
                workspace,
                skill_id="s",
                run_id="20260401",
                history_retention=1,
            ).get_output_dir()

        cleanup_lines = [r.message for r in caplog.records if "cleanup removed" in r.message]
        summary_lines = [r.message for r in caplog.records if "cleanup summary" in r.message]
        assert cleanup_lines, "expected at least one cleanup INFO record"
        # Every cleanup line must name a run_id and include a freed_bytes figure.
        for line in cleanup_lines:
            assert "run_id=" in line
            assert "freed_bytes=" in line
        assert summary_lines, "expected the summary INFO record"


class TestConstructorValidation:
    def test_empty_skill_id_rejected(self, workspace: Path) -> None:
        with pytest.raises(ValueError):
            StorageManager(workspace, skill_id="", run_id="r1")

    def test_empty_run_id_rejected(self, workspace: Path) -> None:
        with pytest.raises(ValueError):
            StorageManager(workspace, skill_id="s", run_id="")

    def test_negative_retention_rejected(self, workspace: Path) -> None:
        with pytest.raises(ValueError):
            StorageManager(workspace, skill_id="s", run_id="r1", history_retention=-1)


class TestSanitizeRunId:
    def test_replaces_unsafe_chars_with_hyphens(self) -> None:
        assert sanitize_run_id("ep1 / run*1") == "ep1-run-1"

    def test_defaults_when_all_chars_stripped(self) -> None:
        assert sanitize_run_id("///") == "run"
