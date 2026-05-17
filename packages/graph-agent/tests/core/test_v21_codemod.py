from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from graph_agent.codemod.v21_migrator import migrate_skill_md
from graph_agent.core.loader import SkillLoader
from graph_agent.core.manifest import PhaseAST, SkillNodeAST
from pydantic import TypeAdapter

_TESTS_DIR = Path(__file__).parents[1]
_PACKAGE_ROOT = Path(__file__).parents[2]
_REPO_ROOT = Path(__file__).parents[4]
_FIXTURE_ROOT = _TESTS_DIR / "fixtures" / "codemod_v20"
_GOLDEN_ROOT = _TESTS_DIR / "golden" / "codemod"
_SCANNER = _REPO_ROOT / "scripts" / "ci_scan_codemod_review.py"


def _relative_files(root: Path) -> list[str]:
    return sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file())


def _assert_tree_matches(actual: Path, expected: Path) -> None:
    assert _relative_files(actual) == _relative_files(expected)
    for rel_path in _relative_files(expected):
        assert (actual / rel_path).read_text(encoding="utf-8") == (expected / rel_path).read_text(
            encoding="utf-8"
        )


@pytest.mark.parametrize("case", ["simple", "complex", "multi_phase"])
def test_codemod_outputs_match_golden_and_compile(case: str, tmp_path: Path) -> None:
    out_dir = tmp_path / case

    report = migrate_skill_md(_FIXTURE_ROOT / case, out_dir)

    _assert_tree_matches(out_dir, _GOLDEN_ROOT / case)
    compiled = SkillLoader().compile_skill(out_dir)
    assert len(compiled.nodes) > 0
    assert len(report.written_files) == len(_relative_files(out_dir))

    phase_adapter = TypeAdapter(PhaseAST)
    assert SkillNodeAST.model_json_schema()["properties"]["mode"]["const"] == "skill"
    for node in compiled.nodes:
        phase_adapter.validate_python(node.ast.model_dump())


def test_complex_fixture_injects_review_markers(tmp_path: Path) -> None:
    out_dir = tmp_path / "complex"

    report = migrate_skill_md(_FIXTURE_ROOT / "complex", out_dir)

    marker_lines = [
        line
        for path in (out_dir / "phases").glob("**/*.md")
        for line in path.read_text(encoding="utf-8").splitlines()
        if "<!--TODO: CODEMOD_REVIEW" in line
    ]
    assert len(marker_lines) == 11
    assert len(report.review_markers) == 11


def test_codemod_refuses_existing_output_without_force(tmp_path: Path) -> None:
    out_dir = tmp_path / "candidate"
    migrate_skill_md(_FIXTURE_ROOT / "simple", out_dir)

    with pytest.raises(FileExistsError):
        migrate_skill_md(_FIXTURE_ROOT / "simple", out_dir)


def test_codemod_force_replaces_existing_output(tmp_path: Path) -> None:
    out_dir = tmp_path / "candidate"
    migrate_skill_md(_FIXTURE_ROOT / "simple", out_dir)
    extra = out_dir / "stale.txt"
    extra.write_text("stale\n", encoding="utf-8")

    migrate_skill_md(_FIXTURE_ROOT / "simple", out_dir, force=True)

    assert not extra.exists()
    _assert_tree_matches(out_dir, _GOLDEN_ROOT / "simple")


def test_ci_scan_codemod_review_exits_one_on_marker() -> None:
    result = subprocess.run(
        [sys.executable, str(_SCANNER), str(_GOLDEN_ROOT / "complex")],
        cwd=_PACKAGE_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "CODEMOD_REVIEW" not in result.stdout
    assert "phases/segment/SKILL.md" in result.stdout


def test_ci_scan_codemod_review_exits_zero_without_marker(tmp_path: Path) -> None:
    clean_root = tmp_path / "clean"
    shutil.copytree(_GOLDEN_ROOT / "simple", clean_root)
    for path in (clean_root / "phases").glob("**/*.md"):
        text = "\n".join(
            line
            for line in path.read_text(encoding="utf-8").splitlines()
            if "<!--TODO: CODEMOD_REVIEW" not in line
        )
        path.write_text(text + "\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(_SCANNER), str(clean_root)],
        cwd=_PACKAGE_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout == ""
