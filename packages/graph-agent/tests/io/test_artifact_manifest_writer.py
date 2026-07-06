"""Artifact manifest writer — fixed-format persistence (MVP1 r3, PM 2026-07-02).

Design: engine mvp1 physical-layout §2.2.2 + skill-syntax §3.4.1.
runtime_config artifacts declares a list of {stem, fields, mode}; the writer
persists blackboard fields into fixed-format files:

- single:   ``<stem>_latest_<YYYYMMDD_HHMMSS>.json`` (+ old versions archived
            to ``history/<stem>_v<ts>.json``)
- per-item: ``<stem>/<stem>_<NNN>_latest_<ts>.json`` — one numbered file per
            list element; NNN inherits the element's ``chapter_number`` when
            present, else 1-based position.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from graph_agent.io.artifact_manifest import write_manifest_artifacts

TS1 = "20260702_120000"
TS2 = "20260702_130000"


def _read(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


class TestSingleMode:
    def test_writes_latest_file_with_checked_fields_only(self, tmp_path: Path) -> None:
        blackboard = {
            "story_framework": {"acts": 3},
            "unified_event_stream": {"events": []},
            "project_id": "013",
        }
        spec = [
            {
                "stem": "story_framework",
                "mode": "single",
                "fields": ["story_framework", "unified_event_stream"],
            }
        ]

        written = write_manifest_artifacts(spec, blackboard, tmp_path, timestamp=TS1)

        target = tmp_path / f"story_framework_latest_{TS1}.json"
        assert target in written
        payload = _read(target)
        assert payload == {
            "story_framework": {"acts": 3},
            "unified_event_stream": {"events": []},
        }

    def test_archives_previous_latest_into_history(self, tmp_path: Path) -> None:
        spec = [{"stem": "report", "mode": "single", "fields": ["report"]}]

        write_manifest_artifacts(spec, {"report": {"v": 1}}, tmp_path, timestamp=TS1)
        write_manifest_artifacts(spec, {"report": {"v": 2}}, tmp_path, timestamp=TS2)

        assert not (tmp_path / f"report_latest_{TS1}.json").exists()
        archived = tmp_path / "history" / f"report_v{TS1}.json"
        assert _read(archived) == {"report": {"v": 1}}
        assert _read(tmp_path / f"report_latest_{TS2}.json") == {"report": {"v": 2}}

    def test_missing_field_on_blackboard_is_skipped_not_fatal(self, tmp_path: Path) -> None:
        spec = [{"stem": "r", "mode": "single", "fields": ["present", "absent"]}]

        written = write_manifest_artifacts(spec, {"present": 1}, tmp_path, timestamp=TS1)

        assert _read(written[0]) == {"present": 1}

    def test_no_field_present_writes_nothing(self, tmp_path: Path) -> None:
        spec = [{"stem": "r", "mode": "single", "fields": ["absent"]}]

        written = write_manifest_artifacts(spec, {"other": 1}, tmp_path, timestamp=TS1)

        assert written == []
        assert list(tmp_path.iterdir()) == []


class TestPerItemMode:
    def test_numbered_files_inherit_chapter_number(self, tmp_path: Path) -> None:
        blackboard = {
            "segmentation_result": [
                {"chapter_number": 1, "paragraphs": ["a"]},
                {"chapter_number": 7, "paragraphs": ["b"]},
            ]
        }
        spec = [
            {"stem": "abc_segmentation", "mode": "per-item", "fields": ["segmentation_result"]}
        ]

        written = write_manifest_artifacts(spec, blackboard, tmp_path, timestamp=TS1)

        d = tmp_path / "abc_segmentation"
        assert (d / f"abc_segmentation_001_latest_{TS1}.json") in written
        assert (d / f"abc_segmentation_007_latest_{TS1}.json") in written
        assert _read(d / f"abc_segmentation_007_latest_{TS1}.json") == {
            "segmentation_result": {"chapter_number": 7, "paragraphs": ["b"]}
        }

    def test_falls_back_to_position_when_no_number(self, tmp_path: Path) -> None:
        spec = [{"stem": "out", "mode": "per-item", "fields": ["items"]}]

        write_manifest_artifacts(spec, {"items": ["x", "y"]}, tmp_path, timestamp=TS1)

        d = tmp_path / "out"
        assert (d / f"out_001_latest_{TS1}.json").exists()
        assert (d / f"out_002_latest_{TS1}.json").exists()

    def test_per_item_archives_same_number_into_history(self, tmp_path: Path) -> None:
        spec = [{"stem": "out", "mode": "per-item", "fields": ["items"]}]

        write_manifest_artifacts(
            spec, {"items": [{"chapter_number": 1, "v": 1}]}, tmp_path, timestamp=TS1
        )
        write_manifest_artifacts(
            spec, {"items": [{"chapter_number": 1, "v": 2}]}, tmp_path, timestamp=TS2
        )

        d = tmp_path / "out"
        assert not (d / f"out_001_latest_{TS1}.json").exists()
        assert _read(d / "history" / f"out_001_v{TS1}.json") == {
            "items": {"chapter_number": 1, "v": 1}
        }
        assert _read(d / f"out_001_latest_{TS2}.json") == {
            "items": {"chapter_number": 1, "v": 2}
        }

    def test_md_format_writes_raw_string_verbatim(self, tmp_path: Path) -> None:
        raw_md = "## Report\n\nExact **markdown**, not re-serialized JSON.\n"
        spec = [
            {"stem": "report", "mode": "single", "fields": ["business_data_md"], "format": "md"}
        ]

        written = write_manifest_artifacts(
            spec, {"business_data_md": raw_md}, tmp_path, timestamp=TS1
        )

        target = tmp_path / f"report_latest_{TS1}.md"
        assert written == [target]
        assert target.read_text(encoding="utf-8") == raw_md

    def test_non_list_field_in_per_item_mode_is_fatal(self, tmp_path: Path) -> None:
        spec = [{"stem": "out", "mode": "per-item", "fields": ["scalar"]}]

        with pytest.raises(Exception) as exc_info:
            write_manifest_artifacts(spec, {"scalar": 42}, tmp_path, timestamp=TS1)

        assert "per-item" in str(exc_info.value)
