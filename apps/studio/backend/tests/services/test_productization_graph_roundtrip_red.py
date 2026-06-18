from __future__ import annotations

import importlib
from pathlib import Path

import pytest

BACKEND_ROOT = next(
    parent for parent in Path(__file__).resolve().parents if (parent / "app").is_dir() and (parent / "tests").is_dir()
)


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


def test_ui_metadata_does_not_enter_execution_fingerprint() -> None:
    try:
        graph_roundtrip = importlib.import_module("app.services.graph_roundtrip")
    except ModuleNotFoundError as exc:
        pytest.fail(f"app.services.graph_roundtrip is missing: {exc}")

    graph = {
        "schema_version": "v0.3.0",
        "name": "text-segmentation",
        "phases": [
            {
                "id": "setup",
                "depends_on": ["input"],
                "actions": [{"id": "prepare", "uses": "prepare.py"}],
            }
        ],
    }
    graph_with_ui_metadata = {
        **graph,
        "ui": {
            "nodes": [{"id": "setup", "x": 100, "y": 200}],
            "viewport": {"zoom": 0.85},
        },
    }

    assert graph_roundtrip.execution_fingerprint(graph_with_ui_metadata) == graph_roundtrip.execution_fingerprint(graph)


def test_phase_ui_metadata_does_not_enter_execution_fingerprint() -> None:
    graph_roundtrip = importlib.import_module("app.services.graph_roundtrip")
    graph = {
        "schema_version": "v0.3.0",
        "name": "text-segmentation",
        "io": {
            "inputs": {"type": "object", "properties": {"input_text": {"type": "string"}}},
            "outputs": {"type": "object", "properties": {"summary": {"type": "string"}}},
        },
        "phases": [
            {
                "id": "setup",
                "depends_on": ["input"],
                "actions": [{"id": "prepare", "uses": "prepare.py"}],
                "metadata": {"canvas": {"x": 100, "y": 200}},
                "comments": ["shown only in Studio"],
            }
        ],
    }
    graph_without_phase_ui = {
        **graph,
        "phases": [
            {
                "id": "setup",
                "depends_on": ["input"],
                "actions": [{"id": "prepare", "uses": "prepare.py"}],
            }
        ],
    }

    assert graph_roundtrip.execution_fingerprint(graph) == graph_roundtrip.execution_fingerprint(graph_without_phase_ui)


def test_execution_fingerprint_changes_for_execution_semantics() -> None:
    graph_roundtrip = importlib.import_module("app.services.graph_roundtrip")
    graph = {
        "schema_version": "v0.3.0",
        "name": "text-segmentation",
        "io": {
            "inputs": {"type": "object", "properties": {"input_text": {"type": "string"}}},
            "outputs": {"type": "object", "properties": {"summary": {"type": "string"}}},
        },
        "phases": [
            {
                "id": "setup",
                "depends_on": ["input"],
                "actions": [{"id": "prepare", "uses": "prepare.py"}],
            }
        ],
    }
    changed_dependency = {
        **graph,
        "phases": [{**graph["phases"][0], "depends_on": ["other"]}],
    }
    changed_action = {
        **graph,
        "phases": [{**graph["phases"][0], "actions": [{"id": "prepare", "uses": "other.py"}]}],
    }
    changed_io_schema = {
        **graph,
        "io": {
            **graph["io"],
            "outputs": {"type": "object", "properties": {"summary": {"type": "number"}}},
        },
    }

    fingerprint = graph_roundtrip.execution_fingerprint(graph)
    assert graph_roundtrip.execution_fingerprint(changed_dependency) != fingerprint
    assert graph_roundtrip.execution_fingerprint(changed_action) != fingerprint
    assert graph_roundtrip.execution_fingerprint(changed_io_schema) != fingerprint
