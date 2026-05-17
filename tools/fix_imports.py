"""LibCST-based one-shot rewriter: relative -> absolute imports.

Usage:
    uv run python tools/fix_imports.py

Run from repo root. Scans packages/graph-agent/src/**/*.py and converts
all `from .x import y` and `from ..y import z` to absolute paths
rooted at `graph_agent`.
"""

from __future__ import annotations

from pathlib import Path

import libcst as cst


class RelativeToAbsoluteTransformer(cst.CSTTransformer):
    """Convert relative imports in a single Python file."""

    def __init__(self, package_parts: list[str]):
        """package_parts = dotted path to containing package of the current file.

        Examples:
        - file = graph_agent/core/runner.py    -> package_parts = ['graph_agent', 'core']
        - file = graph_agent/__init__.py        -> package_parts = ['graph_agent']
        - file = graph_agent/core/__init__.py   -> package_parts = ['graph_agent', 'core']
        """
        self.package_parts = package_parts

    def leave_ImportFrom(
        self, original_node: cst.ImportFrom, updated_node: cst.ImportFrom
    ) -> cst.ImportFrom:
        level = len(updated_node.relative)  # LibCST: relative is Sequence[Dot]
        if level == 0:
            return updated_node  # already absolute

        # `from . import x` (level=1)  -> stays in containing package
        # `from .. import x` (level=2) -> parent of containing package
        # base_parts = package_parts[: len - (level-1)]
        if level - 1 > len(self.package_parts):
            return updated_node  # cannot resolve, leave unchanged
        base_parts = self.package_parts[: len(self.package_parts) - (level - 1)]

        # Append the dotted module name after the dots, if any
        suffix_parts: list[str] = []
        if updated_node.module is not None:
            suffix_parts = _flatten_attr(updated_node.module)

        new_module_parts = base_parts + suffix_parts
        if not new_module_parts:
            return updated_node  # invalid (nothing to import from)
        new_module_node = _build_module_node(new_module_parts)

        return updated_node.with_changes(relative=[], module=new_module_node)


def _flatten_attr(node: cst.BaseExpression) -> list[str]:
    if isinstance(node, cst.Name):
        return [node.value]
    if isinstance(node, cst.Attribute):
        return _flatten_attr(node.value) + [node.attr.value]
    return []


def _build_module_node(parts: list[str]) -> cst.BaseExpression:
    node: cst.BaseExpression = cst.Name(parts[0])
    for part in parts[1:]:
        node = cst.Attribute(value=node, attr=cst.Name(part))
    return node


def process_file(file_path: Path, src_root: Path) -> bool:
    """Returns True if file was modified."""
    rel = file_path.relative_to(src_root)
    package_parts = list(rel.parent.parts)  # works for __init__.py and regular files

    code = file_path.read_text(encoding="utf-8")
    tree = cst.parse_module(code)
    transformer = RelativeToAbsoluteTransformer(package_parts)
    new_tree = tree.visit(transformer)

    if new_tree.code != code:
        file_path.write_text(new_tree.code, encoding="utf-8")
        return True
    return False


if __name__ == "__main__":
    src_root = Path("packages/graph-agent/src")
    if not src_root.is_dir():
        raise SystemExit(f"Expected src root not found: {src_root}")

    scanned = 0
    modified = 0
    for py_file in src_root.rglob("*.py"):
        scanned += 1
        if process_file(py_file, src_root):
            print(f"Modified: {py_file}")
            modified += 1
    print(f"\nScanned {scanned} files, modified {modified}.")
