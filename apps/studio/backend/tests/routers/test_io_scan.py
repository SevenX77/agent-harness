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


def test_scan_json_file_accepts_utf8_bom(client: TestClient, tmp_path: Path) -> None:
    target = tmp_path / "windows_export.json"
    target.write_text(
        json.dumps({"chapters": [{"title": "A"}], "topic": "manual verify"}),
        encoding="utf-8-sig",
    )

    payload = _scan(client, target)

    fields = {f["name"]: f for f in _entry(payload, "windows_export.json")["fields"]}
    assert fields["chapters"]["type"] == "array"
    assert fields["topic"]["type"] == "string"


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
    assert log["fields"][0]["name"] == "log"
    assert log["fields"][0]["type"] == "array"
    assert {f["name"] for f in log["fields"][0]["items"]} == {"event", "ts"}


def test_scan_structured_tables_and_file_refs(client: TestClient, tmp_path: Path) -> None:
    folder = tmp_path / "mixed"
    folder.mkdir()
    (folder / "people.csv").write_text("name,age\nAda,37\n", encoding="utf-8")
    (folder / "codes.tsv").write_text("code\tlabel\nA1\tAlpha\n", encoding="utf-8")
    (folder / "notes.md").write_text("# Notes\n", encoding="utf-8")
    (folder / "brief.pdf").write_bytes(b"%PDF-1.4\n")

    payload = _scan(client, folder)

    people = _entry(payload, "people.csv")
    assert people["format"] == "csv"
    assert people["fields"][0]["type"] == "array"
    assert [field["name"] for field in people["fields"][0]["items"]] == ["name", "age"]

    codes = _entry(payload, "codes.tsv")
    assert codes["format"] == "tsv"
    assert [field["name"] for field in codes["fields"][0]["items"]] == ["code", "label"]

    notes = _entry(payload, "notes.md")
    assert notes["format"] == "text"
    assert notes["content_type"] == "text/markdown"

    brief = _entry(payload, "brief.pdf")
    assert brief["format"] == "document"
    assert brief["content_type"] == "application/pdf"
    assert brief["fields"][0]["value_type"] == "file_ref"


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
    assert batch["fields"][0]["name"] == "chapter"
    assert batch["fields"][0]["type"] == "array"
    assert {f["name"] for f in batch["fields"][0]["items"]} == {"chapter_number", "paragraphs"}


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


def test_scan_ignores_dot_history(
    client: TestClient, tmp_path: Path
) -> None:
    folder = tmp_path / "story_framework"
    folder.mkdir()
    (folder / "global_latest_20260414_124706.json").write_text(
        json.dumps({"scenes": []}), encoding="utf-8"
    )
    dot_history = folder / ".history"
    dot_history.mkdir()
    (dot_history / "global_v20260414_065740.json").write_text("{}", encoding="utf-8")

    payload = _scan(client, folder)

    names = [e["name"] for e in payload["entries"]]
    assert ".history" not in names
    assert [e["name"] for e in payload["entries"]] == ["global_latest_20260414_124706.json"]


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


SKILL_ID = "text-segmentation"
IMPORT_URL = f"/api/skills/{SKILL_ID}/io/import"


def test_import_copies_folder_into_workspace_import_files_root(
    client: TestClient, studio_roots: tuple[Path, Path], tmp_path: Path
) -> None:
    source = tmp_path / "node1_output" / "abc_segmentation"
    source.mkdir(parents=True)
    for n in (1, 2):
        (source / f"chapter_{n:03d}_latest_x.json").write_text(
            json.dumps({"chapter_number": n}), encoding="utf-8"
        )
    (source / "history").mkdir()
    (source / "history" / "chapter_001_v0.json").write_text("{}", encoding="utf-8")
    (source / ".history").mkdir()
    (source / ".history" / "chapter_002_v0.json").write_text("{}", encoding="utf-8")

    resp = client.post(IMPORT_URL, json={"path": str(source)})
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["dir"] == "import_files/abc_segmentation"
    skills_dir, _ = studio_roots
    copied = skills_dir / SKILL_ID / ".workspace" / "import_files" / "abc_segmentation"
    assert (copied / "chapter_001_latest_x.json").exists()
    assert not (copied / "history").exists()
    assert not (copied / ".history").exists()
    assert body["entries"][0]["kind"] == "batch"
    assert body["entries"][0]["numbers"] == [1, 2]
    assert body["entries"][0]["dir"] == "import_files/abc_segmentation"


def test_import_copies_node_file_under_node_import_files(
    client: TestClient, studio_roots: tuple[Path, Path], tmp_path: Path
) -> None:
    source = tmp_path / "quality_report.json"
    source.write_text(json.dumps({"project_id": "013"}), encoding="utf-8")

    resp = client.post(IMPORT_URL, json={"path": str(source), "name": "material", "node_id": "setup"})
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["dir"] == "import_files/.phase/setup/material"
    skills_dir, _ = studio_roots
    copied = skills_dir / SKILL_ID / ".workspace" / "import_files" / ".phase" / "setup" / "material"
    assert (copied / "quality_report.json").exists()
    entry = body["entries"][0]
    assert entry["name"] == "quality_report.json"
    assert entry["path"] == "import_files/.phase/setup/material/quality_report.json"
    runtime_config = json.loads(
        (skills_dir / SKILL_ID / ".workspace" / "runtime_config.json").read_text(encoding="utf-8")
    )
    assert "golden" not in runtime_config
    assert "ui" not in runtime_config
    phase_entry = runtime_config["inputs"]["manifest"]["phases"]["setup"][0]["entries"][0]
    assert phase_entry["fields"][0]["json_path"] == ["project_id"]
    assert phase_entry["path"] == (
        "import_files/.phase/setup/material/quality_report.json"
    )
    assert runtime_config["inputs"]["active"]["phases"]["setup"] == {}


def test_import_single_file_lands_under_named_dir(
    client: TestClient, studio_roots: tuple[Path, Path], tmp_path: Path
) -> None:
    source = tmp_path / "quality_report.json"
    source.write_text(json.dumps({"project_id": "013"}), encoding="utf-8")

    resp = client.post(IMPORT_URL, json={"path": str(source), "name": "material"})
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["dir"] == "import_files/material"
    entry = body["entries"][0]
    assert entry["name"] == "quality_report.json"
    assert entry["path"] == "import_files/material/quality_report.json"


def test_runtime_config_get_refreshes_import_manifest(
    client: TestClient, studio_roots: tuple[Path, Path]
) -> None:
    skills_dir, _ = studio_roots
    skill_dir = skills_dir / SKILL_ID
    root_dir = skill_dir / ".workspace" / "import_files"
    root_dir.mkdir(parents=True)
    (root_dir / "brief.md").write_text("hello", encoding="utf-8")
    phase_dir = skill_dir / ".workspace" / "import_files" / ".phase" / "setup"
    phase_dir.mkdir(parents=True)
    (phase_dir / "chapters.json").write_text(json.dumps([{"chapter_number": 1}]), encoding="utf-8")

    resp = client.get(f"/api/skills/{SKILL_ID}/runtime-config")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["inputs"]["manifest"]["root"][0]["name"] == "brief.md"
    assert body["inputs"]["manifest"]["root"][0]["content_type"] == "text/markdown"
    assert body["inputs"]["active"]["root"] == {}
    assert body["inputs"]["manifest"]["phases"]["setup"][0]["name"] == "chapters.json"
    assert body["inputs"]["active"]["phases"]["setup"] == {}


def test_import_rejects_unknown_node_id(
    client: TestClient, tmp_path: Path
) -> None:
    source = tmp_path / "quality_report.json"
    source.write_text(json.dumps({"project_id": "013"}), encoding="utf-8")

    resp = client.post(IMPORT_URL, json={"path": str(source), "name": "material", "node_id": "segment"})

    assert resp.status_code == 422
    assert "unknown node id" in resp.text


def test_runtime_config_get_syncs_phase_import_dirs_to_graph(
    client: TestClient, studio_roots: tuple[Path, Path]
) -> None:
    skills_dir, _ = studio_roots
    skill_dir = skills_dir / SKILL_ID
    phase_root = skill_dir / ".workspace" / "import_files" / ".phase"
    (phase_root / "obsolete").mkdir(parents=True)
    (phase_root / "obsolete" / "stale.json").write_text("{}", encoding="utf-8")

    resp = client.get(f"/api/skills/{SKILL_ID}/runtime-config")
    assert resp.status_code == 200, resp.text

    assert (phase_root / "setup").is_dir()
    assert not (phase_root / "obsolete").exists()


def test_runtime_config_ignores_dot_history_and_reports_duplicate_conflicts(
    client: TestClient, studio_roots: tuple[Path, Path]
) -> None:
    skills_dir, _ = studio_roots
    skill_dir = skills_dir / SKILL_ID
    root_dir = skill_dir / ".workspace" / "import_files"
    root_dir.mkdir(parents=True)
    (root_dir / "a.json").write_text(json.dumps({"input_text": "first"}), encoding="utf-8")
    (root_dir / "b.json").write_text(json.dumps({"input_text": "second"}), encoding="utf-8")
    dot_history = root_dir / ".history"
    dot_history.mkdir()
    (dot_history / "archived.json").write_text(json.dumps({"input_text": "old"}), encoding="utf-8")

    resp = client.get(f"/api/skills/{SKILL_ID}/runtime-config")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert [entry["name"] for entry in body["inputs"]["manifest"]["root"]] == ["a.json", "b.json"]
    assert "input_text" not in body["inputs"]["active"]["root"]
    conflicts = body["inputs"]["conflicts"]["root"]
    assert conflicts == [
        {
            "field": "input_text",
            "normalized_field": "input_text",
            "scope": "root",
            "candidates": [
                {
                    "path": "import_files/a.json",
                    "type": "string",
                    "value_type": "json",
                    "content_type": "application/json",
                    "json_path": ["input_text"],
                },
                {
                    "path": "import_files/b.json",
                    "type": "string",
                    "value_type": "json",
                    "content_type": "application/json",
                    "json_path": ["input_text"],
                },
            ],
        }
    ]


def test_runtime_config_artifacts_put_updates_unified_runtime_config(
    client: TestClient, studio_roots: tuple[Path, Path]
) -> None:
    resp = client.put(
        f"/api/skills/{SKILL_ID}/runtime-config/artifacts",
        json={
            "artifacts": [
                {"stem": "report", "mode": "single", "format": "md", "fields": ["report_md"]}
            ]
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["artifacts"] == [
        {"stem": "report", "mode": "single", "format": "md", "fields": ["report_md"]}
    ]
    assert "golden" not in body
    assert "ui" not in body
    skills_dir, _ = studio_roots
    disk = json.loads((skills_dir / SKILL_ID / ".workspace" / "runtime_config.json").read_text(encoding="utf-8"))
    assert disk["artifacts"][0]["stem"] == "report"


def test_import_missing_source_is_404(client: TestClient, tmp_path: Path) -> None:
    resp = client.post(IMPORT_URL, json={"path": str(tmp_path / "nope")})
    assert resp.status_code == 404


def test_import_unsafe_name_is_422(client: TestClient, tmp_path: Path) -> None:
    src = tmp_path / "x.json"
    src.write_text("{}", encoding="utf-8")
    resp = client.post(IMPORT_URL, json={"path": str(src), "name": "../evil"})
    assert resp.status_code == 422


def test_import_unsafe_node_id_is_422(client: TestClient, tmp_path: Path) -> None:
    src = tmp_path / "x.json"
    src.write_text("{}", encoding="utf-8")
    resp = client.post(IMPORT_URL, json={"path": str(src), "node_id": "../evil"})
    assert resp.status_code == 422
