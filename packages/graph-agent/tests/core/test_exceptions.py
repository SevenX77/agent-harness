from __future__ import annotations

import pytest
from graph_agent.core.exceptions import (
    ArtifactError,
    CheckpointError,
    ContractValidationError,
    ExecutionError,
    GraphAgentError,
    LoaderError,
    PersistenceError,
    PhaseBuildError,
    PhaseExecutionError,
    SchemaValidationError,
    SkillModuleLoadError,
    SkillParseError,
    StateTransformError,
    ToolExecutionError,
    TraceWriteError,
    ValidationError,
)

DESIGN_EXCEPTIONS = (
    GraphAgentError,
    LoaderError,
    SkillParseError,
    SkillModuleLoadError,
    PhaseBuildError,
    ValidationError,
    SchemaValidationError,
    ContractValidationError,
    ExecutionError,
    PhaseExecutionError,
    StateTransformError,
    ToolExecutionError,
    PersistenceError,
    CheckpointError,
    TraceWriteError,
    ArtifactError,
)


@pytest.mark.parametrize("exception_class", DESIGN_EXCEPTIONS)
def test_exception_can_be_instantiated(
    exception_class: type[GraphAgentError],
) -> None:
    exc = exception_class("failure")

    assert str(exc) == "failure"
    assert exc.context == {}


@pytest.mark.parametrize(
    ("exception_class", "parent_class", "category_class"),
    (
        (LoaderError, GraphAgentError, GraphAgentError),
        (SkillParseError, LoaderError, GraphAgentError),
        (SkillModuleLoadError, LoaderError, GraphAgentError),
        (PhaseBuildError, LoaderError, GraphAgentError),
        (ValidationError, GraphAgentError, GraphAgentError),
        (SchemaValidationError, ValidationError, GraphAgentError),
        (ContractValidationError, ValidationError, GraphAgentError),
        (ExecutionError, GraphAgentError, GraphAgentError),
        (PhaseExecutionError, ExecutionError, GraphAgentError),
        (StateTransformError, ExecutionError, GraphAgentError),
        (ToolExecutionError, GraphAgentError, GraphAgentError),
        (PersistenceError, GraphAgentError, GraphAgentError),
        (CheckpointError, PersistenceError, GraphAgentError),
        (TraceWriteError, PersistenceError, GraphAgentError),
        (ArtifactError, PersistenceError, GraphAgentError),
    ),
)
def test_exception_inheritance_chain(
    exception_class: type[GraphAgentError],
    parent_class: type[GraphAgentError],
    category_class: type[GraphAgentError],
) -> None:
    assert issubclass(exception_class, parent_class)
    assert issubclass(parent_class, category_class)
    assert issubclass(category_class, GraphAgentError)


def test_context_dict_is_preserved() -> None:
    context = {"phase": "draft", "attempt": 2}

    exc = PhaseExecutionError("phase failed", context=context)

    assert exc.context == context


def test_raise_from_preserves_cause() -> None:
    cause = ValueError("bad input")

    with pytest.raises(SkillParseError) as exc_info:
        try:
            raise cause
        except ValueError as exc:
            raise SkillParseError("parse failed") from exc

    assert exc_info.value.__cause__ is cause
