"""Typed CallbackEvent union for graph_agent runs.

Each of the 14 callback hook payloads is modelled as a standalone Pydantic
class with a ``Literal[event_type]`` tag, then brought together as the
discriminated union :data:`CallbackEvent`. Studio / downstream tooling can
now deserialise ``tracing.jsonl`` into a well-typed object instead of the
ad-hoc dict shape that ``base.py`` historically passed around.

Backward compatibility: ``callbacks/base.py`` emits both the new Pydantic
event and the legacy dict for a transition period (see Task 3.5).

New events introduced by this revision:

* ``prompt_captured`` — fired by the TracingClientProxy right before an
  LLM call so Studio can show the exact ``(template_source, variables,
  resolved_prompt)`` triple that reached the model.
* ``llm_fallback`` — fired by the ModelResolver when the primary provider
  fails and a peer-group fallback takes over.

Parallel-map grouping: every event optionally carries ``sub_run_id`` /
``group_key`` so the Studio timeline can fold concurrent child runs that
share a ``parallel_map`` invocation (see Task 4.3).

Note: this module intentionally does **not** use ``from __future__ import
annotations`` — Pydantic needs the ``Literal`` tag expressions to be
evaluated at class-definition time so the discriminated-union dispatch
works without explicit ``model_rebuild`` calls at import.
"""
from datetime import datetime, timezone
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "1.0"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class _EventBase(BaseModel):
    """Fields shared by every ``CallbackEvent`` variant."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    timestamp: str = Field(default_factory=_utc_now_iso)
    # Parallel-map grouping (Task 4.3). Both are set by ``parallel_map`` when it
    # propagates child-skill events to a parent callback; otherwise ``None``.
    sub_run_id: str | None = None
    group_key: str | None = None


class PhaseStartEvent(_EventBase):
    event_type: Literal["phase_start"] = "phase_start"
    phase_name: str
    context: dict[str, Any] = Field(default_factory=dict)


class PhaseEndEvent(_EventBase):
    event_type: Literal["phase_end"] = "phase_end"
    phase_name: str
    context: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)


class LLMCallEvent(_EventBase):
    event_type: Literal["llm_call"] = "llm_call"
    phase_name: str
    input_tokens: int
    output_tokens: int
    messages: list[dict[str, Any]] | None = None
    response_data: dict[str, Any] | None = None


class ToolCallEvent(_EventBase):
    event_type: Literal["tool_call"] = "tool_call"
    phase_name: str
    tool_name: str
    args: dict[str, Any] = Field(default_factory=dict)
    result: str
    duration_ms: float | None = None


class ValidationFailEvent(_EventBase):
    event_type: Literal["validation_fail"] = "validation_fail"
    phase_name: str
    errors: list[str] = Field(default_factory=list)
    retry_count: int


class RetryEvent(_EventBase):
    event_type: Literal["retry"] = "retry"
    phase_name: str
    target_phase: str
    feedback: list[str] = Field(default_factory=list)


class FinishTaskEvent(_EventBase):
    event_type: Literal["finish_task"] = "finish_task"
    phase_name: str
    reasoning: str
    evidence: list[str] = Field(default_factory=list)


class NudgeEvent(_EventBase):
    event_type: Literal["nudge"] = "nudge"
    phase_name: str
    nudge_count: int
    nudge_type: str = "standard"


class WorkingMemoryUpdateEvent(_EventBase):
    event_type: Literal["working_memory_update"] = "working_memory_update"
    phase_name: str
    content_length: int


class DeadEndPrunedEvent(_EventBase):
    event_type: Literal["dead_end_pruned"] = "dead_end_pruned"
    phase_name: str
    summary: str


class CompactionEvent(_EventBase):
    event_type: Literal["compaction"] = "compaction"
    phase_name: str
    removed_pairs: int


class AmbiguityReportEvent(_EventBase):
    event_type: Literal["ambiguity_report"] = "ambiguity_report"
    phase_name: str
    ambiguity_type: str
    question: str
    decision: str


class PromptCapturedEvent(_EventBase):
    """Fired by TracingClientProxy right before the LLM round-trip.

    ``template_source`` is the filename / id of the prompt template when
    the caller tracks one; ``variables`` is the rendered placeholder dict;
    ``resolved_prompt`` is the final message list after template expansion.
    """

    event_type: Literal["prompt_captured"] = "prompt_captured"
    phase_name: str
    llm_role: str | None = None
    resolved_model: str | None = None
    template_source: str | None = None
    variables: dict[str, Any] = Field(default_factory=dict)
    resolved_prompt: list[dict[str, Any]] = Field(default_factory=list)


class LLMFallbackEvent(_EventBase):
    """Fired by ModelResolver when a peer-group fallback swaps the provider."""

    event_type: Literal["llm_fallback"] = "llm_fallback"
    phase_name: str
    from_provider: str
    to_provider: str
    reason: str


CallbackEvent = Annotated[
    Union[
        PhaseStartEvent,
        PhaseEndEvent,
        LLMCallEvent,
        ToolCallEvent,
        ValidationFailEvent,
        RetryEvent,
        FinishTaskEvent,
        NudgeEvent,
        WorkingMemoryUpdateEvent,
        DeadEndPrunedEvent,
        CompactionEvent,
        AmbiguityReportEvent,
        PromptCapturedEvent,
        LLMFallbackEvent,
    ],
    Field(discriminator="event_type"),
]


__all__ = [
    "SCHEMA_VERSION",
    "CallbackEvent",
    "PhaseStartEvent",
    "PhaseEndEvent",
    "LLMCallEvent",
    "ToolCallEvent",
    "ValidationFailEvent",
    "RetryEvent",
    "FinishTaskEvent",
    "NudgeEvent",
    "WorkingMemoryUpdateEvent",
    "DeadEndPrunedEvent",
    "CompactionEvent",
    "AmbiguityReportEvent",
    "PromptCapturedEvent",
    "LLMFallbackEvent",
]
