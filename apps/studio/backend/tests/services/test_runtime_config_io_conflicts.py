from __future__ import annotations

import json
from pathlib import Path

from app.services import skills as skill_service
from app.services.runtime_config import refresh_runtime_config


def test_runtime_config_accepts_utf8_bom_import_json(
    studio_roots: tuple[Path, Path],
) -> None:
    skills_dir, _workspaces = studio_roots
    skill_dir = skills_dir / "text-segmentation"
    import_root = skill_dir / ".workspace" / "import_files"
    import_root.mkdir(parents=True)
    (import_root / "windows_export.json").write_text(
        json.dumps({"chapters": [{"title": "A"}], "topic": "manual verify"}),
        encoding="utf-8-sig",
    )

    config = refresh_runtime_config(skill_dir)

    fields = config["inputs"]["manifest"]["root"][0]["fields"]
    by_name = {field["name"]: field for field in fields}
    assert by_name["chapters"]["type"] == "array"
    assert by_name["topic"]["type"] == "string"
    assert config["inputs"]["active"]["root"] == {}


def test_lint_reports_runtime_input_conflict_before_compile(
    studio_roots: tuple[Path, Path],
) -> None:
    skills_dir, _workspaces = studio_roots
    skill_dir = skills_dir / "text-segmentation"
    import_root = skill_dir / ".workspace" / "import_files"
    import_root.mkdir(parents=True)
    (import_root / "first.json").write_text(json.dumps({"input_text": "first"}), encoding="utf-8")
    (import_root / "second.json").write_text(json.dumps({"input_text": "second"}), encoding="utf-8")

    result = skill_service.lint_skill_on_disk("text-segmentation")

    assert result.status == "failed"
    conflict = next(error for error in result.errors if error.error_code == "STUDIO_RUNTIME_INPUT_CONFLICT")
    assert conflict.file == ".workspace/runtime_config.json"
    assert conflict.field_path == "input_text"
    assert "multiple runtime import candidates" in conflict.message
