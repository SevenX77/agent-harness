"""ProtocolValidationMiddleware — single owner of state-contract checks.

MVP-3 T7 (B3 middleware simplification): the canonical site where the
framework verifies its three state invariants on every LLM step
boundary. Replaces the contract-validation slice that previously sat
inside the legacy ``cognitive/middlewares.py`` parallel pipeline (which
mixed contract validation with finish_task interception, schema
hoisting, and rejection-message authoring). Phase 3 M7 retired the
legacy pipeline; this middleware now owns contract checks exclusively.

Three contracts pinned here:

1. ``state['data']`` (BusinessData, ``extra='allow'``) must not contain
   any ``_``-prefixed keys. The MVP-1 namespace split puts framework
   metadata in ``state['flow']``; a stray ``_x`` in BusinessData means
   either a tool wrote to the wrong namespace or a regression sneaked
   in via SKILL.md authoring.
2. ``state['flow']`` (FrameworkState, ``extra='forbid'``) must round
   trip through ``FrameworkState.model_validate``. The Pydantic forbid
   check is enforced on construction, but a tool that mutates the
   in-memory dataclass via ``__dict__`` (an old hack) bypasses it.
   Re-validating at every LLM step boundary catches the divergence.
3. ``schema_engine.validate(state['data'].model_dump(),
   current_phase_schema)`` must succeed when the phase has a compiled
   schema. The schema describes what the LLM is about to produce; an
   inconsistent BusinessData here means the previous turn drifted
   (e.g., a tool returned dict keys that don't match output_schema).

Each ``before_model`` / ``after_model`` call returns ``None`` (a no-op
LangGraph state update) when invariants hold. A failure raises
:class:`ProtocolValidationError`; the surrounding agent loop converts
that into a tool rejection or run-level crash, depending on context.
The middleware deliberately does *not* attempt to recover the state —
the framework's contract is binary, and silent recovery would mask
authoring bugs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langgraph.runtime import Runtime
from pydantic import BaseModel, ValidationError

from graph_agent.core.exceptions import GraphAgentError
from graph_agent.core.schema_engine import SchemaObject
from graph_agent.core.state import FrameworkState

if TYPE_CHECKING:
    from graph_agent.core.schema_engine import SchemaEngine


class ProtocolValidationError(GraphAgentError):
    """Raised when a WorkflowState violates one of the three contracts.

    Carries a structured ``violations`` list (label + detail per failure)
    so callers can surface a precise error message to the LLM or the
    user without re-deriving which contract failed.
    """

    def __init__(self, message: str, *, violations: list[tuple[str, str]]) -> None:
        super().__init__(message, context={"violations": violations})
        self.violations = list(violations)


class ProtocolValidationMiddleware(AgentMiddleware[AgentState[Any]]):
    """Single owner of state-contract validation around the LLM step.

    Invariants enforced (see module docstring for rationale):

    1. ``state['data']`` carries no ``_``-prefixed keys.
    2. ``state['flow']`` round-trips through ``FrameworkState.model_validate``.
    3. (Optional, when ``current_phase_schema`` is supplied)
       ``schema_engine.validate(state['data'].model_dump(), schema)``
       returns ``ok=True``.
    """

    def __init__(
        self,
        schema_engine: SchemaEngine | None = None,
        current_phase_schema: type[BaseModel] | SchemaObject | None = None,
        *,
        phase_name: str = "unknown",
    ) -> None:
        # Phase 2 A2 v3 (design v4 §3.4 step 1): the schema parameter union
        # was extended from ``SchemaObject | None`` to also accept a Pydantic
        # ``type[BaseModel]`` so dotted-path SKILLs (e.g. text-segmentation
        # pointing to ``script.models.Segment``) can mount this middleware
        # without requiring a SchemaObject bridge. The schema-engine
        # validation in ``_validate`` only fires for the SchemaObject form
        # because that form historically described the BusinessData root;
        # a Pydantic ``type[BaseModel]`` here describes a per-item shape
        # (one ``## block``) and so cannot be validated against the whole
        # BusinessData dump — see the ``_should_run_schema_check`` guard.
        super().__init__()
        self._schema_engine = schema_engine
        self._current_phase_schema = current_phase_schema
        self._phase_name = phase_name

    def before_model(
        self,
        state: AgentState[Any],
        runtime: Runtime[Any],
    ) -> dict[str, Any] | None:
        """Validate state contracts before the LLM produces a response.

        ``runtime`` is unused at this layer — kept in the signature so
        LangGraph's middleware bus can wire the middleware without a
        sentinel adapter. The return value is always ``None`` (no
        state update) on success; a failure raises and breaks the loop.
        """
        del runtime
        self._validate(state, "before_model")
        return None

    def after_model(
        self,
        state: AgentState[Any],
        runtime: Runtime[Any],
    ) -> dict[str, Any] | None:
        """Validate state contracts after the LLM produces a response.

        Same set of checks as ``before_model`` plus the optional
        schema-engine validation against the phase's compiled schema —
        if the LLM emitted business data that diverges from the
        declared output schema, this is where we catch it.
        """
        del runtime
        self._validate(state, "after_model", schema_check=True)
        return None

    def _validate(
        self,
        state: AgentState[Any],
        boundary: str,
        *,
        schema_check: bool = False,
    ) -> None:
        violations: list[tuple[str, str]] = []

        # The middleware is only meaningful for ``WorkflowState`` (the
        # MVP-1 split state); when the agent runs against a default
        # AgentState there is nothing to validate. Tolerating that
        # avoids breaking older callers that haven't migrated yet.
        raw_data: object = state.get("data") if isinstance(state, dict) else None
        raw_flow: object = state.get("flow") if isinstance(state, dict) else None

        data_dump: dict[str, Any] | None = None
        if raw_data is not None:
            if isinstance(raw_data, BaseModel):
                data_dump = raw_data.model_dump()
                bad_keys = [k for k in data_dump if str(k).startswith("_")]
                if bad_keys:
                    violations.append(
                        (
                            "business_data_underscore_prefix",
                            f"BusinessData carries forbidden _-prefixed keys: {bad_keys!r}",
                        )
                    )
            else:
                violations.append(
                    (
                        "business_data_not_pydantic",
                        f"expected pydantic.BaseModel, got {type(raw_data).__name__}",
                    )
                )

        if raw_flow is not None:
            if isinstance(raw_flow, BaseModel):
                flow_dump = raw_flow.model_dump()
                try:
                    FrameworkState.model_validate(flow_dump)
                except ValidationError as exc:
                    violations.append(("framework_state_extra_forbidden", str(exc)))
            else:
                violations.append(
                    (
                        "framework_state_not_pydantic",
                        f"expected pydantic.BaseModel, got {type(raw_flow).__name__}",
                    )
                )

        if (
            schema_check
            and self._schema_engine is not None
            and self._current_phase_schema is not None
            and data_dump is not None
            and isinstance(self._current_phase_schema, SchemaObject)
        ):
            # Phase 2 A2 v3: only run schema-engine validation against the
            # BusinessData dump when the schema is a SchemaObject — that
            # form historically describes the data root. A Pydantic
            # ``type[BaseModel]`` here describes a per-item ``## block``
            # shape (e.g. one ``Segment``) and cannot be validated against
            # the aggregated BusinessData dump; the per-item check happens
            # in CognitiveFlowMiddleware._validate_finish_args at
            # finish_task time, where the markdown is parsed and each
            # block is validated individually.
            result = self._schema_engine.validate(data_dump, self._current_phase_schema)
            if not result.ok:
                violations.append(("schema_engine_validate", "; ".join(result.errors)))

        if violations:
            raise ProtocolValidationError(
                f"ProtocolValidation failed at {boundary} for phase "
                f"'{self._phase_name}': {len(violations)} violation(s)",
                violations=violations,
            )


__all__ = ["ProtocolValidationError", "ProtocolValidationMiddleware"]
