"""IO scan endpoint — file/folder field recognition for the input config tree.

Design: docs/studio/mvp1/03_regions/input/mvp1-alignment.md F5 (PM 2026-07-02).
Recognition must handle two real shapes:
- heterogeneous artifact folders (material-prep: json/md/txt/jsonl mixed)
- iterate batch folders (chapter_001..chapter_060 + latest/_v modifiers + history/)
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient


def _scan(client: TestClient, path: Path) -> dict:
    resp = client.post("/api/io/scan", json={"path": str(path)})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _entry(payload: dict, name: str) -> dict:
    matches = [e for e in payload["entries"] if e["name"] == name]
    assert matches, [e["name"] for e in payload["entries"]]
    return matches[0]


def test_scan_json_file_yields_top_level_fields(client: TestClient, tmp_path: Path) -> None:
    target = tmp_path / "quality_report.json"
    target.write_text(
        json.dumps({"project_id": "013", "validation": {"status": "pass"}}),
        encoding="utf-8",
    )

    payload = _scan(client, target)

    entry = _entry(payload, "quality_report.json")
    assert entry["kind"] == "file"
    assert entry["format"] == "json"
    fields = {f["name"]: f for f in entry["fields"]}
    assert fields["project_id"]["type"] == "string"
    assert fields["project_id"]["sample"] == "013"
    assert fields["validation"]["type"] == "object"


def test_scan_folder_lists_files_and_text_candidates(
    client: TestClient, tmp_path: Path
) -> None:
    folder = tmp_path / "material"
    folder.mkdir()
    (folder / "chapters.json").write_text(
        json.dumps([{"index": 1, "title": "第1章"}]), encoding="utf-8"
    )
    (folder / "novel.md").write_text("## 第1章\n正文", encoding="utf-8")
    (folder / "log.jsonl").write_text(
        json.dumps({"event": "x", "ts": 1}) + "\n" + json.dumps({"event": "y"}),
        encoding="utf-8",
    )

    payload = _scan(client, folder)

    chapters = _entry(payload, "chapters.json")
    assert chapters["format"] == "json"
    assert chapters["fields"][0]["type"] == "array"

    novel = _entry(payload, "novel.md")
    assert novel["format"] == "text"
    assert novel["fields"] == [
        {"name": "novel", "type": "string", "sample": None}
    ]
    assert novel["size"] > 0

    log = _entry(payload, "log.jsonl")
    assert log["format"] == "jsonl"
    assert {f["name"] for f in log["fields"]} == {"event", "ts"}


def test_scan_folds_numbered_batch_and_keeps_numbers(
    client: TestClient, tmp_path: Path
) -> None:
    folder = tmp_path / "abc_segmentation"
    folder.mkdir()
    for n in (1, 2, 7):
        (folder / f"chapter_{n:03d}_latest_20260414_0649{n:02d}.json").write_text(
            json.dumps({"chapter_number": n, "paragraphs": []}), encoding="utf-8"
        )

    payload = _scan(client, folder)

    assert len(payload["entries"]) == 1
    batch = payload["entries"][0]
    assert batch["kind"] == "batch"
    assert batch["numbers"] == [1, 2, 7]
    assert batch["count"] == 3
    field_names = {f["name"] for f in batch["fields"]}
    assert field_names == {"chapter_number", "paragraphs"}


def test_scan_takes_latest_version_and_ignores_history(
    client: TestClient, tmp_path: Path
) -> None:
    folder = tmp_path / "story_framework"
    folder.mkdir()
    (folder / "global_latest_20260414_124706.json").write_text(
        json.dumps({"scenes": []}), encoding="utf-8"
    )
    history = folder / "history"
    history.mkdir()
    (history / "global_v20260414_065740.json").write_text("{}", encoding="utf-8")

    payload = _scan(client, folder)

    names = [e["name"] for e in payload["entries"]]
    assert "history" not in names
    entry = _entry(payload, "global_latest_20260414_124706.json")
    assert entry["stem"] == "global"


def test_scan_recurses_one_level_into_subfolders(
    client: TestClient, tmp_path: Path
) -> None:
    root = tmp_path / "node1_output"
    sub = root / "event_timeline"
    sub.mkdir(parents=True)
    for n in (1, 2):
        (sub / f"chapter_{n:03d}_latest_x.json").write_text(
            json.dumps({"chapter_number": n}), encoding="utf-8"
        )

    payload = _scan(client, root)

    folder_entry = _entry(payload, "event_timeline")
    assert folder_entry["kind"] == "dir"
    assert folder_entry["entries"][0]["kind"] == "batch"
    assert folder_entry["entries"][0]["numbers"] == [1, 2]


def test_scan_large_text_reports_size_without_content(
    client: TestClient, tmp_path: Path
) -> None:
    big = tmp_path / "novel_utf8.txt"
    big.write_text("x" * 300_000, encoding="utf-8")

    payload = _scan(client, big)

    entry = _entry(payload, "novel_utf8.txt")
    assert entry["size"] == 300_000
    assert entry["fields"][0]["sample"] is None
    assert len(json.dumps(payload)) < 10_000


def test_scan_missing_path_returns_404(client: TestClient, tmp_path: Path) -> None:
    resp = client.post("/api/io/scan", json={"path": str(tmp_path / "nope")})
    assert resp.status_code == 404
