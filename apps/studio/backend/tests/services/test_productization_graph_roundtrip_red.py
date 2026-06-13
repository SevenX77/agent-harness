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
