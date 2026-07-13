from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.services.runtime_config import (
    read_runtime_config,
    refresh_runtime_config,
    remove_runtime_input_binding,
    runtime_config_path_for,
    runtime_input_fields_for_engine,
)
from fastapi.testclient import TestClient

SKILL_ID = "text-segmentation"


def _import_root(skill_dir: Path) -> Path:
    root = skill_dir / ".workspace" / "import_files"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _phase_import_root(skill_dir: Path, phase_id: str = "setup") -> Path:
    root = skill_dir / ".workspace" / "import_files" / ".phase" / phase_id
    root.mkdir(parents=True, exist_ok=True)
    return root


def _write_graph_inputs(skill_dir: Path, fields: list[str]) -> None:
    properties = "\n".join(f"      {field}:\n        type: string" for field in fields)
    required = ", ".join(fields)
    (skill_dir / "GRAPH.md").write_text(
        f"""---
schema_version: "v0.3.0"
name: {skill_dir.name}
description: runtime config intent test
io:
  inputs:
    type: object
    properties:
{properties}
    required: [{required}]
    additionalProperties: false
  outputs:
    type: object
    properties:
      prepared:
        type: boolean
    required: [prepared]
    additionalProperties: true
phases:
  - setup
---
<phase depends_on="input" output>setup</phase>
""",
        encoding="utf-8",
    )


def _write_phase_inputs(skill_dir: Path, fields: list[str], phase_id: str = "setup") -> None:
    properties = "\n".join(f"      {field}:\n        type: string" for field in fields)
    phase_dir = skill_dir / "phases" / phase_id
    phase_dir.mkdir(parents=True, exist_ok=True)
    (phase_dir / "LOGIC.md").write_text(
        f"""---
io:
  inputs:
    type: object
    properties:
{properties}
  outputs:
    type: object
    properties:
      prepared:
        type: boolean
actions: [prepare]
---
<action>prepare</action>
""",
        encoding="utf-8",
    )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _active_root(config: dict[str, Any]) -> dict[str, Any]:
    return config["inputs"]["active"]["root"]


def _active_phase(config: dict[str, Any], phase_id: str = "setup") -> dict[str, Any]:
    return config["inputs"]["active"]["phases"].get(phase_id, {})


def _removed_root(config: dict[str, Any]) -> list[str]:
    return config["inputs"]["removed"]["root"]


def _removed_phase(config: dict[str, Any], phase_id: str = "setup") -> list[str]:
    return config["inputs"]["removed"]["phases"].get(phase_id, [])


def test_refresh_preserves_active_binding_not_overwritten(studio_roots: tuple[Path, Path]) -> None:
    skills_dir, _ = studio_roots
    skill_dir = skills_dir / SKILL_ID
    _write_graph_inputs(skill_dir, ["input_text"])
    _write_json(_import_root(skill_dir) / "source.json", {"input_text": "first"})
    first = refresh_runtime_config(skill_dir)
    assert _active_root(first)["input_text"]["path"] == "import_files/source.json"

    config = read_runtime_config(skill_dir)
    config["inputs"]["active"]["root"]["input_text"]["user_note"] = "sticky"
    runtime_config_path_for(skill_dir).write_text(json.dumps(config), encoding="utf-8")

    refreshed = refresh_runtime_config(skill_dir)

    assert _active_root(refreshed)["input_text"]["path"] == "import_files/source.json"
    assert _active_root(refreshed)["input_text"]["user_note"] == "sticky"


def test_refresh_does_not_resurrect_removed_candidate(studio_roots: tuple[Path, Path]) -> None:
    skills_dir, _ = studio_roots
    skill_dir = skills_dir / SKILL_ID
    _write_graph_inputs(skill_dir, ["input_text"])
    _write_json(_import_root(skill_dir) / "source.json", {"input_text": "first"})
    refresh_runtime_config(skill_dir)

    removed = remove_runtime_input_binding(skill_dir, scope="root", field="input_text")
    assert "input_text" in _removed_root(removed)
    assert "input_text" not in _active_root(removed)

    refreshed = refresh_runtime_config(skill_dir)

    assert "input_text" in _removed_root(refreshed)
    assert "input_text" not in _active_root(refreshed)


def test_manifest_rederived_each_refresh(studio_roots: tuple[Path, Path]) -> None:
    skills_dir, _ = studio_roots
    skill_dir = skills_dir / SKILL_ID
    root = _import_root(skill_dir)
    (root / "brief.md").write_text("hello", encoding="utf-8")

    first = refresh_runtime_config(skill_dir)
    assert [entry["name"] for entry in first["inputs"]["manifest"]["root"]] == ["brief.md"]

    (root / "brief.md").unlink()
    (root / "replacement.md").write_text("hello", encoding="utf-8")
    second = refresh_runtime_config(skill_dir)

    assert [entry["name"] for entry in second["inputs"]["manifest"]["root"]] == ["replacement.md"]


def test_three_states_mutually_exclusive(studio_roots: tuple[Path, Path]) -> None:
    skills_dir, _ = studio_roots
    skill_dir = skills_dir / SKILL_ID
    _write_graph_inputs(skill_dir, ["input_text"])
    root = _import_root(skill_dir)
    _write_json(root / "input_text.json", {"input_text": "first"})
    _write_json(root / "candidate_only.json", {"candidate_only": "second"})
    refresh_runtime_config(skill_dir)
    config = remove_runtime_input_binding(skill_dir, scope="root", field="input_text")

    active = set(_active_root(config))
    removed = set(_removed_root(config))
    candidates = {
        field["name"]
        for entry in config["inputs"]["manifest"]["root"]
        for field in entry.get("fields", [])
        if isinstance(field, dict) and isinstance(field.get("name"), str)
    } - active - removed

    assert active.isdisjoint(removed)
    assert active.isdisjoint(candidates)
    assert removed.isdisjoint(candidates)
    assert removed == {"input_text"}
    assert candidates == {"candidate_only"}


def test_auto_match_activates_new_matching_candidate(studio_roots: tuple[Path, Path]) -> None:
    skills_dir, _ = studio_roots
    skill_dir = skills_dir / SKILL_ID
    _write_graph_inputs(skill_dir, ["input_text"])
    _write_json(_import_root(skill_dir) / "input-text.json", {"input-text": "first"})

    config = refresh_runtime_config(skill_dir)

    assert _active_root(config)["input_text"]["path"] == "import_files/input-text.json"


def test_auto_match_suppressed_for_removed_field(studio_roots: tuple[Path, Path]) -> None:
    skills_dir, _ = studio_roots
    skill_dir = skills_dir / SKILL_ID
    _write_graph_inputs(skill_dir, ["input_text"])
    _write_json(_import_root(skill_dir) / "input-text.json", {"input-text": "first"})
    refresh_runtime_config(skill_dir)
    remove_runtime_input_binding(skill_dir, scope="root", field="input_text")

    config = refresh_runtime_config(skill_dir)

    assert "input_text" in _removed_root(config)
    assert "input_text" not in _active_root(config)


def test_active_binding_descriptor_refreshed_from_current_file(studio_roots: tuple[Path, Path]) -> None:
    skills_dir, _ = studio_roots
    skill_dir = skills_dir / SKILL_ID
    _write_graph_inputs(skill_dir, ["input_text"])
    root = _import_root(skill_dir)
    _write_json(root / "input_text.json", {"input_text": "first"})
    refresh_runtime_config(skill_dir)

    (root / "input_text.json").unlink()
    _write_json(root / "input-text.json", {"input-text": "second"})
    config = refresh_runtime_config(skill_dir)

    assert _active_root(config)["input_text"]["path"] == "import_files/input-text.json"
    assert "status" not in _active_root(config)["input_text"]


def test_active_source_missing_surfaced_not_deleted(studio_roots: tuple[Path, Path]) -> None:
    skills_dir, _ = studio_roots
    skill_dir = skills_dir / SKILL_ID
    _write_graph_inputs(skill_dir, ["input_text"])
    source = _import_root(skill_dir) / "input_text.json"
    _write_json(source, {"input_text": "first"})
    refresh_runtime_config(skill_dir)

    source.unlink()
    config = refresh_runtime_config(skill_dir)

    assert "input_text" in _active_root(config)
    assert _active_root(config)["input_text"]["status"] == "source-missing"


def test_remove_binding_persists_tombstone_survives_refresh(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    skills_dir, _ = studio_roots
    skill_dir = skills_dir / SKILL_ID
    _write_phase_inputs(skill_dir, ["input_text"])
    _write_json(_phase_import_root(skill_dir) / "input_text.json", {"input_text": "first"})
    refresh_runtime_config(skill_dir)

    response = client.post(
        f"/api/skills/{SKILL_ID}/runtime-config/inputs/remove",
        json={"scope": "phase:setup", "field": "input_text"},
    )
    assert response.status_code == 200, response.text
    removed = response.json()
    assert "input_text" in _removed_phase(removed)
    assert "input_text" not in _active_phase(removed)

    refreshed = refresh_runtime_config(skill_dir)
    assert "input_text" in _removed_phase(refreshed)
    assert "input_text" not in _active_phase(refreshed)


def test_restore_removed_candidate_reactivatable(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    skills_dir, _ = studio_roots
    skill_dir = skills_dir / SKILL_ID
    _write_graph_inputs(skill_dir, ["input_text"])
    _write_json(_import_root(skill_dir) / "input_text.json", {"input_text": "first"})
    refresh_runtime_config(skill_dir)
    remove_runtime_input_binding(skill_dir, scope="root", field="input_text")

    response = client.post(
        f"/api/skills/{SKILL_ID}/runtime-config/inputs/restore",
        json={"scope": "root", "field": "input_text"},
    )
    assert response.status_code == 200, response.text
    restored = response.json()

    assert "input_text" not in _removed_root(restored)
    assert _active_root(restored)["input_text"]["path"] == "import_files/input_text.json"


def test_engine_runtime_input_fields_reads_active_only() -> None:
    config: dict[str, Any] = {
        "inputs": {
            "active": {
                "root": {"root_active": {"path": "import_files/root_active.md"}},
                "phases": {"setup": {"phase_active": {"path": "import_files/.phase/setup/phase_active.md"}}},
            },
            "removed": {"root": ["root_removed"], "phases": {"setup": ["phase_removed"]}},
            "manifest": {
                "root": [{"fields": [{"name": "candidate_only"}]}],
                "phases": {"setup": [{"fields": [{"name": "phase_candidate_only"}]}]},
            },
        }
    }

    assert runtime_input_fields_for_engine(config) == {"setup": {"phase_active"}}


def test_v1_config_regenerated_not_translated(studio_roots: tuple[Path, Path]) -> None:
    skills_dir, _ = studio_roots
    skill_dir = skills_dir / SKILL_ID
    _write_graph_inputs(skill_dir, ["input_text"])
    _write_json(_import_root(skill_dir) / "input_text.json", {"input_text": "fresh"})
    runtime_config_path_for(skill_dir).parent.mkdir(parents=True, exist_ok=True)
    runtime_config_path_for(skill_dir).write_text(
        json.dumps(
            {
                "schema_version": "studio.runtime_config.v1",
                "inputs": {
                    "import_root": "import_files",
                    "manifest": {"root": [], "phases": {}},
                    "root": {"legacy": {"path": "import_files/legacy.md"}},
                    "phases": {"setup": {"legacy_phase": {"path": "import_files/.phase/setup/legacy.md"}}},
                    "conflicts": {"root": [], "phases": {}},
                },
            }
        ),
        encoding="utf-8",
    )

    config = refresh_runtime_config(skill_dir)

    assert config["schema_version"] == "studio.runtime_config.v2"
    assert "root" not in config["inputs"]
    assert "phases" not in config["inputs"]
    assert "legacy" not in _active_root(config)
    assert _active_root(config)["input_text"]["path"] == "import_files/input_text.json"
    assert config["inputs"]["manifest"]["root"][0]["name"] == "input_text.json"


def test_migration_has_no_dual_format_branch(studio_roots: tuple[Path, Path]) -> None:
    skills_dir, _ = studio_roots
    skill_dir = skills_dir / SKILL_ID
    _write_graph_inputs(skill_dir, ["input_text"])
    _write_json(_import_root(skill_dir) / "input_text.json", {"input_text": "fresh"})
    runtime_config_path_for(skill_dir).parent.mkdir(parents=True, exist_ok=True)
    runtime_config_path_for(skill_dir).write_text(
        json.dumps(
            {
                "schema_version": "studio.runtime_config.v1",
                "inputs": {
                    "root": {"input_text": {"path": "import_files/stale.json", "user_note": "must-not-survive"}},
                    "phases": {},
                },
            }
        ),
        encoding="utf-8",
    )

    config = refresh_runtime_config(skill_dir)

    assert _active_root(config)["input_text"]["path"] == "import_files/input_text.json"
    assert "user_note" not in _active_root(config)["input_text"]


def test_non_import_slots_survive_migration(studio_roots: tuple[Path, Path]) -> None:
    skills_dir, _ = studio_roots
    skill_dir = skills_dir / SKILL_ID
    runtime_config_path_for(skill_dir).parent.mkdir(parents=True, exist_ok=True)
    runtime_config_path_for(skill_dir).write_text(
        json.dumps(
            {
                "schema_version": "studio.runtime_config.v1",
                "inputs": {"root": {"legacy": {"path": "import_files/legacy.md"}}, "phases": {}},
                "llm": {
                    "node_params": {"nodes": {"setup": {"temperature": 0.2}}},
                    "compare_candidates": {"nodes": {"setup": [{"candidate_id": "fast"}]}},
                },
                "artifacts": [{"stem": "summary", "mode": "single", "format": "json", "fields": ["prepared"]}],
            }
        ),
        encoding="utf-8",
    )

    config = refresh_runtime_config(skill_dir)

    assert config["llm"]["node_params"]["nodes"]["setup"]["temperature"] == 0.2
    assert config["llm"]["compare_candidates"]["nodes"]["setup"][0]["candidate_id"] == "fast"
    assert config["artifacts"][0]["stem"] == "summary"
    assert "legacy" not in _active_root(config)


def test_conflict_detection_unchanged(studio_roots: tuple[Path, Path]) -> None:
    skills_dir, _ = studio_roots
    skill_dir = skills_dir / SKILL_ID
    _write_graph_inputs(skill_dir, ["input_text"])
    root = _import_root(skill_dir)
    _write_json(root / "first.json", {"input_text": "first"})
    _write_json(root / "second.json", {"input_text": "second"})

    config = refresh_runtime_config(skill_dir)

    assert "input_text" not in _active_root(config)
    assert config["inputs"]["conflicts"]["root"][0]["field"] == "input_text"


def test_import_into_workspace_still_surfaces_candidates(client: TestClient, tmp_path: Path) -> None:
    source = tmp_path / "quality_report.json"
    source.write_text(json.dumps({"input_text": "first"}), encoding="utf-8")

    response = client.post(
        f"/api/skills/{SKILL_ID}/io/import",
        json={"path": str(source), "name": "material"},
    )

    assert response.status_code == 200, response.text
    config_response = client.get(f"/api/skills/{SKILL_ID}/runtime-config")
    assert config_response.status_code == 200, config_response.text
    body = config_response.json()
    assert body["inputs"]["manifest"]["root"][0]["name"] == "material"
    assert body["inputs"]["active"]["root"]["input_text"]["path"] == (
        "import_files/material/quality_report.json"
    )
