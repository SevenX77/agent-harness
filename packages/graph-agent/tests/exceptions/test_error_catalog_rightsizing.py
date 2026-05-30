"""Red tests for the public exception catalog rightsizing cutover."""

from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

import graph_agent
from graph_agent.core import exceptions as core_exceptions
from graph_agent.core.error_registry import ERROR_REGISTRY
from graph_agent.core.exceptions import ErrorPayload
from graph_agent.core.result import WorkflowResult
from graph_agent.core.skill_resolver_protocol import SkillResolutionError
from graph_agent_gateway import exceptions as gateway_exceptions


PUBLIC_ERROR_EXPORTS = {
    "GraphAgentError",
    "GraphCompileError",
    "GraphExecutionError",
    "ModelProviderError",
    "ResourceNotFoundError",
}

PUBLIC_FAMILY_EXPORTS = PUBLIC_ERROR_EXPORTS - {"GraphAgentError"}

DE_EXPORTED_LEAF_ERRORS = {
    "SkillLoadError",
    "SkillCompilationError",
}

LEAF_TO_FAMILY = [
    ("LoaderError", "GraphCompileError"),
    ("SkillParseError", "GraphCompileError"),
    ("SkillModuleLoadError", "GraphCompileError"),
    ("PhaseBuildError", "GraphCompileError"),
    ("SkillCompileError", "GraphCompileError"),
    ("ValidationError", "GraphCompileError"),
    ("SchemaValidationError", "GraphCompileError"),
    ("ContractValidationError", "GraphCompileError"),
    ("SkillLoadError", "GraphCompileError"),
    ("SkillCompilationError", "GraphCompileError"),
    ("TemplateRenderError", "GraphCompileError"),
    ("ExecutionError", "GraphExecutionError"),
    ("PhaseExecutionError", "GraphExecutionError"),
    ("StateTransformError", "GraphExecutionError"),
    ("ToolExecutionError", "GraphExecutionError"),
    ("PersistenceError", "GraphExecutionError"),
    ("CheckpointError", "GraphExecutionError"),
    ("TraceWriteError", "GraphExecutionError"),
    ("ArtifactError", "GraphExecutionError"),
    ("MaxRetriesExceededError", "GraphExecutionError"),
    ("GraphAgentFatalError", "GraphExecutionError"),
    ("SkillResolutionError", "ResourceNotFoundError"),
]

GATEWAY_LEAF_TO_FAMILY = [
    "GatewayError",
    "AllProvidersFailedError",
    "GatewayResolverMissingError",
    "GatewayRoleNotConfiguredError",
]

GRAPH_AGENT_LEAF_ERROR_IMPORTS = {
    leaf_name for leaf_name, _family_name in LEAF_TO_FAMILY
} | set(GATEWAY_LEAF_TO_FAMILY)

REPO_ROOT = Path(__file__).resolve().parents[4]


def _public_family(name: str) -> type[Any] | None:
    value = getattr(graph_agent, name, None)
    return value if isinstance(value, type) else None


def test_public_error_catalog_exports_only_five_family_classes() -> None:
    actual_error_exports = {name for name in graph_agent.__all__ if name.endswith("Error")}

    assert actual_error_exports == PUBLIC_ERROR_EXPORTS
    assert graph_agent.GraphAgentError is core_exceptions.GraphAgentError
    for name in DE_EXPORTED_LEAF_ERRORS:
        assert name not in graph_agent.__all__
        assert not hasattr(graph_agent, name)
    for name in PUBLIC_ERROR_EXPORTS - {"GraphAgentError"}:
        assert _public_family(name) is not None, f"{name} must be a public exception class"


@pytest.mark.parametrize("family_name", sorted(PUBLIC_FAMILY_EXPORTS))
def test_public_family_errors_directly_inherit_from_graph_agent_error(family_name: str) -> None:
    family = _public_family(family_name)

    assert family is not None, f"{family_name} must be exported from graph_agent"
    assert issubclass(family, graph_agent.GraphAgentError)


@pytest.mark.parametrize(("leaf_name", "family_name"), LEAF_TO_FAMILY)
def test_leaf_errors_inherit_from_their_public_family(
    leaf_name: str,
    family_name: str,
) -> None:
    leaf = SkillResolutionError if leaf_name == "SkillResolutionError" else getattr(
        core_exceptions,
        leaf_name,
    )
    family = _public_family(family_name)

    assert family is not None, f"{family_name} must be exported from graph_agent"
    assert issubclass(leaf, family)
    other_families = PUBLIC_FAMILY_EXPORTS - {family_name}
    unexpected_families = [
        other_family_name
        for other_family_name in sorted(other_families)
        if (other_family := _public_family(other_family_name)) is not None
        and issubclass(leaf, other_family)
    ]
    assert unexpected_families == []


def test_family_error_preserves_payload_granularity() -> None:
    family = _public_family("GraphCompileError")
    assert family is not None, "GraphCompileError must be exported from graph_agent"
    code = "[F-v3-graph-schema-unknown-field]"
    metadata = ERROR_REGISTRY[code]
    payload = ErrorPayload(
        code=code,
        message="GRAPH.md has an unknown field",
        field_path="metadata.unexpected",
    )

    exc = family("compile failed", payload=payload)

    assert exc.payload is payload
    assert exc.payload.code == code
    assert exc.payload.level == metadata.level
    assert exc.payload.stage == metadata.stage
    assert exc.payload.field_path == "metadata.unexpected"
    assert exc.payload.doc_link == metadata.doc_link


def test_workflow_result_error_accepts_structured_payload() -> None:
    code = "[F-v3-runtime-phase-failed]"
    metadata = ERROR_REGISTRY[code]
    payload = ErrorPayload(
        code=code,
        message="phase failed",
        phase_id="draft",
        field_path="context.input",
    )
    now = datetime(2026, 5, 30, tzinfo=UTC)

    result = WorkflowResult(
        success=False,
        run_id="run-1",
        skill_id="skill-1",
        error=payload,
        started_at=now,
        finished_at=now,
    )

    dumped = result.model_dump(mode="json")
    assert dumped["error"]["code"] == code
    assert dumped["error"]["level"] == metadata.level
    assert dumped["error"]["stage"] == list(metadata.stage)
    assert dumped["error"]["field_path"] == "context.input"
    assert dumped["error"]["doc_link"] == metadata.doc_link


@pytest.mark.parametrize("leaf_name", GATEWAY_LEAF_TO_FAMILY)
def test_gateway_errors_inherit_from_model_provider_family(leaf_name: str) -> None:
    family = _public_family("ModelProviderError")
    leaf = getattr(gateway_exceptions, leaf_name)

    assert family is not None, "ModelProviderError must be exported from graph_agent"
    assert issubclass(leaf, family)


def _graph_agent_leaf_imports_under(root: Path) -> list[str]:
    violations: list[str] = []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            module = node.module or ""
            if module != "graph_agent" and not module.startswith("graph_agent."):
                continue
            for alias in node.names:
                if alias.name in GRAPH_AGENT_LEAF_ERROR_IMPORTS:
                    relative_path = path.relative_to(REPO_ROOT)
                    violations.append(f"{relative_path}:{node.lineno} imports {alias.name}")
    return violations


def test_studio_backend_imports_public_error_families_not_graph_agent_leaf_errors() -> None:
    violations = _graph_agent_leaf_imports_under(REPO_ROOT / "apps/studio/backend/app")

    assert not violations, "Studio backend imports graph_agent leaf errors:\n" + "\n".join(
        violations
    )
