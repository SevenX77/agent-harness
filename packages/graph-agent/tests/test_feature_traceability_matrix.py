from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = REPO_ROOT / "packages/graph-agent"
MATRIX_PATH = REPO_ROOT / "docs/engine/feature-compliance-checklist.md"
FEATURES_PATH = PACKAGE_ROOT / "spec/features.yaml"
EXPECTED_FEATURE_COUNT = 36
EXPECTED_CHECKLIST_H3_COUNT = 35
EXPECTED_COVERAGE_COUNT = 35
COVERAGE_RE = re.compile(
    r"\[Covered By: (?P<path>packages/graph-agent/tests/[^:\]]+)::(?:(?P<class>[A-Za-z0-9_]+)::)?(?P<test>test_[A-Za-z0-9_]+)(?:\[[^\]]+\])?\]"
)


def _coverage_refs() -> list[tuple[str, str, str | None]]:
    text = MATRIX_PATH.read_text(encoding="utf-8")
    return [(match.group("path"), match.group("test"), match.group("class")) for match in COVERAGE_RE.finditer(text)]


def _test_functions(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
    }


def test_feature_matrix_lifecycle_items_reference_existing_collectable_tests() -> None:
    text = MATRIX_PATH.read_text(encoding="utf-8")
    features = yaml.safe_load(FEATURES_PATH.read_text(encoding="utf-8"))["features"]

    feature_count = len(re.findall(r"^### ", text, flags=re.MULTILINE))
    refs = _coverage_refs()
    assert "## Manifest Features" in text
    assert len(features) == EXPECTED_FEATURE_COUNT
    assert feature_count == EXPECTED_CHECKLIST_H3_COUNT
    assert len(refs) == EXPECTED_COVERAGE_COUNT

    nodeids: list[str] = []
    for relative_path, test_name, class_name in refs:
        test_path = REPO_ROOT / relative_path
        assert test_path.exists(), relative_path
        assert test_name in _test_functions(test_path), f"{relative_path}::{test_name}"
        class_segment = f"{class_name}::" if class_name else ""
        nodeids.append(f"{test_path}::{class_segment}{test_name}")

    assert pytest.main(["--collect-only", "-q", *nodeids]) == pytest.ExitCode.OK
