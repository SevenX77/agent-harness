"""Exception hierarchy for graph_agent framework.

All graph_agent errors inherit from GraphAgentError. Catch the most
specific class possible at boundaries; let unexpected errors bubble.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


class GraphAgentError(Exception):
    """Base for all graph_agent framework errors.

    Raise this only through a concrete subclass. Boundary code should catch a
    specific lifecycle category or leaf exception, while lower layers wrap
    native exceptions with ``raise ... from`` and include structured context.
    """

    def __init__(self, message: str, *, context: dict[str, Any] | None = None) -> None:
        """Store the surfaced error message and optional structured context."""
        super().__init__(message)
        self.context = context or {}


class GraphAgentFatalError(GraphAgentError):
    """Fail-fast graph_agent error for violated hard invariants."""


# === Loader-time errors (SKILL load / parse / module / phase build) ===


class LoaderError(GraphAgentError):
    """SKILL loading failed before any execution.

    Raise this from parser, loader, compiler, and phase-construction code when
    a SKILL cannot become a runnable graph. Callers that own loading boundaries
    should catch this category and present the failure as a load-time error.
    """


class SkillParseError(LoaderError):
    """SKILL.md text could not be parsed.

    Raise this for frontmatter, YAML, XML-like block, or document structure
    failures. Loader entry points should catch or wrap it as a load-time failure
    without starting graph execution.
    """


class SkillModuleLoadError(LoaderError):
    """A SKILL script or Python module failed to import.

    Raise this when resolving Python hooks, tools, or module-backed phases.
    Module-loading boundaries should wrap ImportError, AttributeError, and
    related import failures with this exception.
    """


class PhaseBuildError(LoaderError):
    """A phase definition could not be built into runtime form.

    Raise this while converting parsed manifest data into executable phase
    objects. The loader/compiler layer should wrap lower-level validation or
    construction errors with this class.
    """


class SkillCompileError(LoaderError):
    """A SKILL.md violates a v1.1+ compile-time contract.

    Raise this when a manifest is syntactically valid but breaks one of the
    Phase 2 architectural contracts that must hold before the SKILL can become
    a runnable graph — for example, an ``LLMPhase`` that mounts a
    ``validator`` without declaring an ``output_schema``/``output_example``.
    Distinct from :class:`SkillCompilationError` (the older catch-all) so new
    contract checks surface with a dedicated, fail-loud type.
    """


# === Validation errors (schema / contract / pre-flight) ===


class ValidationError(GraphAgentError):
    """Validation failed before or around execution.

    Raise this when data is syntactically loaded but violates a schema,
    contract, or pre-flight invariant. Boundary code may catch this category to
    report user-fixable validation failures.
    """


class SchemaValidationError(ValidationError):
    """Pydantic or business schema rejected the data.

    Raise this for typed model, manifest, or domain schema failures. Schema
    validation helpers should wrap native validation exceptions with this class
    when crossing graph_agent boundaries.
    """


class ContractValidationError(ValidationError):
    """A cross-module contract rejected the workflow definition.

    Raise this for IO references, pipeline alignment, context bridge, or
    pre-flight compatibility failures. Contract validators should wrap their
    internal errors with this class before returning to orchestration code.
    """


# === Execution errors (phase execution / state transformation) ===


class ExecutionError(GraphAgentError):
    """Runtime graph execution failed.

    Raise this after a graph has started running. Orchestration boundaries
    should catch this category when they need to distinguish runtime failures
    from load-time and validation failures.
    """


class PhaseExecutionError(ExecutionError):
    """A specific phase failed during a run.

    Raise this around phase body execution, provider calls, or phase-local
    workflow logic. Phase runners should wrap the original exception with this
    class and include phase identifiers in context.
    """


class StateTransformError(ExecutionError):
    """State transformation failed during execution.

    Raise this for deepcopy, merge, hoist, projection, or state-normalization
    failures. Harness state-management code should wrap native errors with this
    class before they leave the orchestration layer.
    """


# === Tool execution errors ===


class ToolExecutionError(GraphAgentError):
    """A registered tool raised during execution.

    Raise this at tool execution boundaries when a tool failure must be surfaced
    through graph_agent's exception family. Tool wrapper code should catch this
    specifically when preserving tool failure semantics, while higher layers
    may let it bubble as a framework error.
    """


# === Persistence errors (file / artifact / checkpoint / trace) ===


class PersistenceError(GraphAgentError):
    """Persistence layer failed.

    Raise this for file, artifact, checkpoint, or trace persistence failures.
    Persistence boundaries should catch native OSError-like failures and wrap
    them here; the name intentionally avoids shadowing Python's IOError.
    """


class CheckpointError(PersistenceError):
    """Checkpoint save or load failed.

    Raise this from checkpointer setup, checkpoint writes, checkpoint reads, or
    cleanup paths. Runner and harness persistence code should wrap the original
    storage exception with this class.
    """


class TraceWriteError(PersistenceError):
    """Trace persistence failed.

    Raise this when trace serialization or trace file writes cannot complete.
    Tracing boundaries should catch native encoding and filesystem failures and
    wrap them with this class.
    """


class ArtifactError(PersistenceError):
    """Artifact save or load failed.

    Raise this for artifact materialization, lookup, read, or write failures.
    Artifact IO code should wrap backend-specific exceptions with this class so
    callers can catch persistence failures uniformly.
    """


# Backward-compatible names kept here so existing public imports continue to
# resolve while the MVP-0 hierarchy lands in the scoped file set.
class SkillLoadError(LoaderError):
    """Compatibility loader error for existing load-time call sites."""


class SkillCompilationError(GraphAgentError):
    """SKILL.md compile failure with detailed context."""

    def __init__(
        self,
        message: str,
        compile_result: object = None,
        *,
        skill_path: Path | None = None,
        line: int | None = None,
        field_path: str | None = None,
        suggestion: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Store compiler output and structured diagnostic context."""
        self.compile_result = compile_result
        self.skill_path = skill_path
        self.line = line
        self.field_path = field_path
        self.suggestion = suggestion
        super().__init__(self._format(message), context=context)

    def _format(self, message: str) -> str:
        parts = [message]
        if self.skill_path:
            loc = f"  at {self.skill_path}"
            if self.line:
                loc += f":{self.line}"
            parts.append(loc)
        if self.field_path:
            parts.append(f"  field: {self.field_path}")
        if self.suggestion:
            parts.append(f"  suggestion: {self.suggestion}")
        return "\n".join(parts)


class TemplateRenderError(ValidationError):
    """Compatibility template validation error for strict render paths."""

    def __init__(
        self,
        missing_key: str,
        available_keys: list[str],
        *,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Capture the missing placeholder and available context keys."""
        self.missing_key = missing_key
        self.available_keys = available_keys
        super().__init__(
            f"Template references key '{missing_key}' which is not in context. "
            f"Available keys: {available_keys}",
            context=context,
        )


class MaxRetriesExceededError(ExecutionError):
    """Compatibility execution error for retry exhaustion notifications."""

    def __init__(
        self,
        phase_name: str,
        max_retries: int,
        *,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Capture the phase name and configured retry ceiling."""
        self.phase_name = phase_name
        self.max_retries = max_retries
        super().__init__(
            f"Phase '{phase_name}' exceeded max retries ({max_retries}). "
            f"Continuing with validation warnings.",
            context=context,
        )
