"""Tests for scripts/snapshot_diff.py (I-2)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# The script is not a package — import the module by path.
_SCRIPT_DIR = Path(__file__).resolve().parents[5] / "scripts"
sys.path.insert(0, str(_SCRIPT_DIR))

import snapshot_diff  # noqa: E402


@pytest.fixture()
def workdir(tmp_path: Path) -> Path:
    return tmp_path


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )


class TestNormalisation:
    def test_timestamp_dropped(self):
        ev = {"event_type": "phase_start", "timestamp": "2026-04-23T..."}
        out = snapshot_diff._normalise(ev, {})
        assert "timestamp" not in out
        assert out["event_type"] == "phase_start"

    def test_uuid_replaced_deterministically(self):
        uuid_map: dict = {}
        a = snapshot_diff._normalise(
            "12345678-1234-5678-1234-567812345678", uuid_map, in_id_field=False
        )
        b = snapshot_diff._normalise(
            "12345678-1234-5678-1234-567812345678", uuid_map, in_id_field=False
        )
        assert a == b == "normalized_uuid_1"
        c = snapshot_diff._normalise("abcdef123456-0001", uuid_map, in_id_field=False)
        assert c == "normalized_uuid_2"

    def test_id_field_name_forces_normalisation(self):
        # Custom id format that doesn't match UUID_RE on its own — but
        # because the FIELD name is run_id, it's still normalised.
        uuid_map: dict = {}
        ev = {"run_id": "human-readable-id-123"}
        out = snapshot_diff._normalise(ev, uuid_map)
        assert out["run_id"] == "normalized_uuid_1"

    def test_plain_strings_untouched(self):
        uuid_map: dict = {}
        ev = {
            "event_type": "phase_start",
            "phase_name": "segmentation",
            "content": "plain old text",
        }
        out = snapshot_diff._normalise(ev, uuid_map)
        assert out == {
            "event_type": "phase_start",
            "phase_name": "segmentation",
            "content": "plain old text",
        }

    def test_nested_list_and_dict(self):
        uuid_map: dict = {}
        ev = {
            "run_id": "abc123def456",
            "children": [
                {"sub_run_id": "abc123def456-0001"},
                {"sub_run_id": "abc123def456-0002"},
            ],
        }
        out = snapshot_diff._normalise(ev, uuid_map)
        assert out["run_id"] == "normalized_uuid_1"
        assert out["children"][0]["sub_run_id"] == "normalized_uuid_2"
        assert out["children"][1]["sub_run_id"] == "normalized_uuid_3"


class TestRecord:
    def test_saves_normalised_baseline(self, workdir: Path):
        run = workdir / "run.jsonl"
        _write_jsonl(
            run,
            [
                {"event_type": "phase_start", "timestamp": "t1", "run_id": "aaa111222333"},
                {"event_type": "phase_end", "timestamp": "t2", "run_id": "aaa111222333"},
            ],
        )
        out = workdir / "baseline.json"
        rc = snapshot_diff._record(run, out)
        assert rc == 0
        baseline = json.loads(out.read_text(encoding="utf-8"))
        assert len(baseline) == 2
        # Same run_id in both events → same normalised id.
        assert baseline[0]["run_id"] == baseline[1]["run_id"] == "normalized_uuid_1"
        for event in baseline:
            assert "timestamp" not in event


class TestDiff:
    def test_identical_after_normalisation_passes(self, workdir: Path):
        # Baseline with one set of random UUIDs:
        baseline = workdir / "base.json"
        baseline.write_text(
            json.dumps(
                [
                    {"event_type": "phase_start", "run_id": "normalized_uuid_1"},
                    {"event_type": "phase_end", "run_id": "normalized_uuid_1"},
                ]
            ),
            encoding="utf-8",
        )
        # Fresh run with *different* real UUIDs + different timestamps:
        run = workdir / "run.jsonl"
        _write_jsonl(
            run,
            [
                {"event_type": "phase_start", "timestamp": "2026-...", "run_id": "bbb444555666"},
                {"event_type": "phase_end", "timestamp": "2026-...", "run_id": "bbb444555666"},
            ],
        )
        rc = snapshot_diff._diff(run, baseline)
        assert rc == 0

    def test_real_difference_is_caught(self, workdir: Path, capfd):
        baseline = workdir / "base.json"
        baseline.write_text(
            json.dumps([{"event_type": "phase_start", "phase_name": "setup"}]),
            encoding="utf-8",
        )
        run = workdir / "run.jsonl"
        _write_jsonl(
            run,
            [
                {"event_type": "phase_start", "timestamp": "t1", "phase_name": "renamed"},
            ],
        )
        rc = snapshot_diff._diff(run, baseline)
        assert rc == 1
        captured = capfd.readouterr()
        assert "setup" in captured.out or "renamed" in captured.out

    def test_missing_run_file_errors_out(self, workdir: Path):
        rc = snapshot_diff._diff(workdir / "nope.jsonl", workdir / "also_nope.json")
        assert rc == 2
