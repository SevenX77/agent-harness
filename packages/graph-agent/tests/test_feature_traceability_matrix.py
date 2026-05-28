from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
MATRIX_PATH = REPO_ROOT / "docs/engine/feature-compliance-checklist.md"
COVERAGE_RE = re.compile(r"\[Covered By: (?P<path>packages/graph-agent/tests/[^:\]]+)::(?P<test>test_[A-Za-z0-9_]+)\]")
LIFECYCLE_HEADINGS = {
    "Loading & Parsing",
    "Compilation & Validation",
    "Execution & Routing",
    "State & Blackboard",
    "Observability & Errors",
}


def _coverage_refs() -> list[tuple[str, str]]:
    text = MATRIX_PATH.read_text(encoding="utf-8")
    return [(match.group("path"), match.group("test")) for match in COVERAGE_RE.finditer(text)]


def _test_functions(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
    }


def test_feature_matrix_lifecycle_items_reference_existing_collectable_tests() -> None:
    text = MATRIX_PATH.read_text(encoding="utf-8")
    for heading in LIFECYCLE_HEADINGS:
        assert f"## {heading}" in text

    feature_count = len(re.findall(r"^### ", text, flags=re.MULTILINE))
    refs = _coverage_refs()
    assert feature_count >= 25
    assert len(refs) == feature_count
    assert len(refs) >= 25

    nodeids: list[str] = []
    for relative_path, test_name in refs:
        test_path = REPO_ROOT / relative_path
        assert test_path.exists(), relative_path
        assert test_name in _test_functions(test_path), f"{relative_path}::{test_name}"
        nodeids.append(f"{relative_path}::{test_name}")

    assert pytest.main(["--collect-only", "-q", *nodeids]) == pytest.ExitCode.OK
