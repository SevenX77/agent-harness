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


def _write_graph_inputs(skill_dir: Path, *, required: list[str], properties: dict[str, str]) -> None:
    """Rewrite the fixture skill's io.inputs so a test can pick which fields the
    graph declares vs requires (conflict scoping depends on exactly that)."""

    graph = (skill_dir / "GRAPH.md").read_text(encoding="utf-8")
    props_block = "\n".join(
        f"      {name}:\n        type: {json_type}" for name, json_type in properties.items()
    )
    new_inputs = (
        "  inputs:\n"
        "    type: object\n"
        "    properties:\n"
        f"{props_block}\n"
        f"    required: [{', '.join(required)}]\n"
        "    additionalProperties: false\n"
    )
    start = graph.index("  inputs:\n")
    end = graph.index("  outputs:\n")
    (skill_dir / "GRAPH.md").write_text(graph[:start] + new_inputs + graph[end:], encoding="utf-8")


def test_conflict_on_declared_but_optional_field_is_reported(
    studio_roots: tuple[Path, Path],
) -> None:
    # Design (03_regions/input/mvp1-alignment.md:42): a runtime import conflict is
    # "多个 candidate 能匹配同一 schema 字段" — declared in the schema, not merely
    # required. An optional declared field whose candidates conflict silently loses
    # its binding, so lint must say so instead of leaving the author guessing.
    skills_dir, _workspaces = studio_roots
    skill_dir = skills_dir / "text-segmentation"
    _write_graph_inputs(
        skill_dir,
        required=["input_text"],
        properties={"input_text": "string", "note": "string"},
    )
    import_root = skill_dir / ".workspace" / "import_files"
    import_root.mkdir(parents=True)
    (import_root / "primary.json").write_text(
        json.dumps({"input_text": "only one candidate"}), encoding="utf-8"
    )
    (import_root / "note_a.json").write_text(json.dumps({"note": "a"}), encoding="utf-8")
    (import_root / "note_b.json").write_text(json.dumps({"note": "b"}), encoding="utf-8")
    refresh_runtime_config(skill_dir)

    result = skill_service.lint_skill_on_disk("text-segmentation")

    conflict = next(
        error
        for error in result.errors
        if error.error_code == "STUDIO_RUNTIME_INPUT_CONFLICT" and error.field_path == "note"
    )
    # Optional field: the graph can still run, so this must not block.
    assert conflict.severity == "warning"
    assert result.status != "failed"


def test_conflict_on_undeclared_field_is_ignored(
    studio_roots: tuple[Path, Path],
) -> None:
    # Two import files sharing a field the graph never declares is not this
    # graph's problem — no diagnostic, and compile/lint stay clean.
    skills_dir, _workspaces = studio_roots
    skill_dir = skills_dir / "text-segmentation"
    import_root = skill_dir / ".workspace" / "import_files"
    import_root.mkdir(parents=True)
    (import_root / "primary.json").write_text(
        json.dumps({"input_text": "bound"}), encoding="utf-8"
    )
    (import_root / "extra_a.json").write_text(json.dumps({"synopsis": "a"}), encoding="utf-8")
    (import_root / "extra_b.json").write_text(json.dumps({"synopsis": "b"}), encoding="utf-8")
    refresh_runtime_config(skill_dir)

    result = skill_service.lint_skill_on_disk("text-segmentation")

    assert not [
        error
        for error in result.errors
        if error.error_code == "STUDIO_RUNTIME_INPUT_CONFLICT" and error.field_path == "synopsis"
    ]


def test_required_field_conflict_stays_fatal(
    studio_roots: tuple[Path, Path],
) -> None:
    # A required field with no binding cannot run: it must stay blocking
    # (CompileError severity "fatal" projects to LintError severity "error").
    skills_dir, _workspaces = studio_roots
    skill_dir = skills_dir / "text-segmentation"
    import_root = skill_dir / ".workspace" / "import_files"
    import_root.mkdir(parents=True)
    (import_root / "first.json").write_text(json.dumps({"input_text": "a"}), encoding="utf-8")
    (import_root / "second.json").write_text(json.dumps({"input_text": "b"}), encoding="utf-8")
    refresh_runtime_config(skill_dir)

    result = skill_service.lint_skill_on_disk("text-segmentation")

    conflict = next(
        error for error in result.errors if error.error_code == "STUDIO_RUNTIME_INPUT_CONFLICT"
    )
    assert conflict.severity == "error"
    assert result.status == "failed"
