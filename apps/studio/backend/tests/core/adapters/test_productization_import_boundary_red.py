from __future__ import annotations

import ast
from pathlib import Path

BACKEND_ROOT = next(
    parent for parent in Path(__file__).resolve().parents if (parent / "app").is_dir() and (parent / "tests").is_dir()
)

SDK_PREFIXES = ("graph_agent", "graph_agent_gateway")


def test_studio_services_do_not_import_sdk_internals_directly() -> None:
    offenders: list[str] = []

    for path in sorted((BACKEND_ROOT / "app" / "services").glob("*.py")):
        for module in _imported_modules(path):
            if module in SDK_PREFIXES or module.startswith(tuple(f"{prefix}." for prefix in SDK_PREFIXES)):
                offenders.append(f"{path.relative_to(BACKEND_ROOT)} imports {module}")

    assert offenders == []


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules
