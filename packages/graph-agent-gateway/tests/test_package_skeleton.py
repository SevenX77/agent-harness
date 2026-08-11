"""
Test: test_package_skeleton.py
Covers: design.md §1.1 (Gateway independent package layout) +
tasks.md α1 (package extraction) + requirements.md §3 R[NEW]-Gateway-01.
"""

from __future__ import annotations

import importlib
import tomllib
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def test_gateway_package_layout_exists() -> None:
    """The package is a tree of domains, each answering for itself through its
    own ``__init__``. Decision:
    docs/design/2026-08-10-gateway-module-tree-and-probing-decision.md
    """
    source_root = PACKAGE_ROOT / "src" / "graph_agent_gateway"

    assert (PACKAGE_ROOT / "pyproject.toml").is_file()
    assert (source_root / "__init__.py").is_file()
    assert (source_root / "errors.py").is_file()
    assert (source_root / "events.py").is_file()
    for domain in ("registry", "resolve", "role", "call"):
        assert (source_root / domain / "__init__.py").is_file(), domain


def test_gateway_public_modules_are_importable_without_graph_agent_cycle() -> None:
    modules = [
        "graph_agent_gateway",
        "graph_agent_gateway.registry",
        "graph_agent_gateway.resolve",
        "graph_agent_gateway.role",
        "graph_agent_gateway.call",
        "graph_agent_gateway.errors",
        "graph_agent_gateway.events",
    ]

    imported = {name: importlib.import_module(name) for name in modules}

    assert imported["graph_agent_gateway.call"].ModelResolverProtocol is not None
    assert imported["graph_agent_gateway.call"].ModelResolver is not None
    assert imported["graph_agent_gateway.call"].GatewayChatModel is not None
    assert imported["graph_agent_gateway.errors"].AllProvidersFailedError is not None
    assert imported["graph_agent_gateway.role"].materialize_role is not None


def test_graph_agent_does_not_import_concrete_gateway_package() -> None:
    graph_agent = importlib.import_module("graph_agent")

    assert not hasattr(graph_agent, "ModelResolver")
    assert not hasattr(graph_agent, "GatewayChatModel")


def test_gateway_package_owns_provider_dependency_boundary() -> None:
    pyproject = tomllib.loads((PACKAGE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    gateway_deps = pyproject["project"]["dependencies"]
    gateway_extras = pyproject["project"]["optional-dependencies"]
    google_extra = gateway_extras["google"]

    assert any(dep.startswith("langchain-openai") for dep in gateway_deps)
    assert any(dep.startswith("langchain-anthropic") for dep in gateway_deps)
    assert any(dep.startswith("langchain-google-genai") for dep in google_extra)
    assert any(dep.startswith("google-genai") for dep in google_extra)

    graph_agent_pyproject = tomllib.loads(
        (PACKAGE_ROOT.parent / "graph-agent" / "pyproject.toml").read_text(encoding="utf-8")
    )
    graph_agent_deps = graph_agent_pyproject["project"]["dependencies"]
    graph_agent_extras = graph_agent_pyproject["project"]["optional-dependencies"]
    graph_agent_dep_text = "\n".join(
        [*graph_agent_deps, *[dep for deps in graph_agent_extras.values() for dep in deps]]
    )
    assert "langchain-openai" not in graph_agent_dep_text
    assert "langchain-anthropic" not in graph_agent_dep_text
    assert "langchain-google-genai" not in graph_agent_dep_text
    assert "google-genai" not in graph_agent_dep_text
    assert "edge-tts" not in graph_agent_dep_text
    assert "google" not in graph_agent_extras
    assert "tts" not in graph_agent_extras
    assert "all" not in graph_agent_extras
