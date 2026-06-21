from __future__ import annotations

import ast
from pathlib import Path

BACKEND_ROOT = next(
    parent for parent in Path(__file__).resolve().parents if (parent / "app").is_dir() and (parent / "tests").is_dir()
)


def test_studio_backend_does_not_define_execution_fingerprint_algorithm() -> None:
    production_paths = [
        *(BACKEND_ROOT / "app" / "services").glob("*.py"),
        *(BACKEND_ROOT / "app" / "routers").glob("*.py"),
    ]
    violations: list[str] = []
    for path in production_paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name == "execution_fingerprint" or (
                path.name == "graph_roundtrip.py" and "fingerprint" in node.name
            ):
                violations.append(f"{path.relative_to(BACKEND_ROOT)}:{node.lineno} defines {node.name}()")

    assert violations == []


def test_studio_backend_does_not_own_graph_parser_or_subgraph_topology_resolver() -> None:
    source = (BACKEND_ROOT / "app" / "services" / "skills.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_functions = {
        "_parse_broken_graph_topology_and_phases",
        "_markdown_frontmatter",
        "_subgraph_path_for_phase",
        "_child_graph_boundary_roots",
        "resolve_child_graph_topology",
        "_graph_frontmatter_from_md",
        "_io_schema_from_frontmatter",
        "_validate_canvas_topology",
        "_validate_canvas_acyclic",
    }
    violations = [
        f"skills.py:{node.lineno} defines {node.name}()"
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in forbidden_functions
    ]

    assert violations == []


def test_graph_serialize_uses_shared_roundtrip_boundary_not_sdk_serializer() -> None:
    source = (BACKEND_ROOT / "app" / "services" / "skills.py").read_text(encoding="utf-8")

    assert "graph_agent.core.graph_serializer" not in source
    assert "graph_roundtrip" in source


def test_graph_serialize_does_not_keep_local_markdown_preservation_owner() -> None:
    skills_source = (BACKEND_ROOT / "app" / "services" / "skills.py").read_text(encoding="utf-8")
    roundtrip_source = (BACKEND_ROOT / "app" / "services" / "graph_roundtrip.py").read_text(
        encoding="utf-8"
    )

    assert "_preserve_graph_markdown_unknowns" not in skills_source
    assert "original_md" in roundtrip_source
