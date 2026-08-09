"""Typed CallbackEvent union for graph_agent runs.

Each of the 14 callback hook payloads is modelled as a standalone Pydantic
class with a ``Literal[event_type]`` tag, then brought together as the
discriminated union :data:`CallbackEvent`. Studio / downstream tooling can
now deserialise ``trace.jsonl`` into a well-typed object instead of the
ad-hoc dict shape that ``base.py`` historically passed around.

Backward compatibility: ``callbacks/base.py`` emits both the new Pydantic
event and the legacy dict for a transition period (see Task 3.5).

New events introduced by this revision:

* ``prompt_captured`` — fired by the chat model right before an
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

from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION: Literal["1.0"] = "1.0"


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


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


class PredictChainStartEvent(_EventBase):
    event_type: Literal["predict_chain_start"] = "predict_chain_start"
    metadata: dict[str, Any] = Field(default_factory=dict)


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
    # The model that actually answered this call, as the provider reported it on
    # the response. A fallback chain means the role does not decide it up front,
    # so per-call is the only place it is true.
    resolved_model: str | None = None
    messages: list[dict[str, Any]] | None = None
    response_data: dict[str, Any] | None = None
    parent_node_id: str | None = None
    node_type: str | None = None


class ToolCallStartedEvent(_EventBase):
    """Fired the moment a tool call is handed to the tool, before it runs.

    ``ToolCallEvent`` reports a finished call, so a consumer that only sees it
    cannot show work in progress. This is the other half: same
    ``tool_call_id``, no result yet.

    ``args`` is repeated on both halves on purpose. ``ToolCallEvent`` has to
    stay independently readable — it is persisted, replayed, and consumed by
    readers that never pair events at all (metrics, golden eval) — and forcing
    every one of them to join two events to learn what a call was for would be
    the wrong trade.
    """

    event_type: Literal["tool_call_started"] = "tool_call_started"
    tool_call_id: str
    phase_name: str
    tool_name: str
    args: dict[str, Any] = Field(default_factory=dict)
    parent_node_id: str | None = None
    node_type: str | None = None


class ToolCallEvent(_EventBase):
    # ``tool_call_id`` is the identity of the call, shared with the matching
    # ToolCallStartedEvent. One agent turn can have several calls in flight, so
    # (phase_name, tool_name) does not identify one — hence required, not
    # defaulted.
    event_type: Literal["tool_call"] = "tool_call"
    tool_call_id: str
    phase_name: str
    tool_name: str
    args: dict[str, Any] = Field(default_factory=dict)
    result: str
    duration_ms: float | None = None
    parent_node_id: str | None = None
    node_type: str | None = None


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
    """Fired when a phase writes ``_working_memory`` in the context.

    Tier 1 Commit B (T-A1) — carries the full text content in addition to
    the length, because Studio needs to replay exactly what the agent
    planned. Older readers that only look at ``content_length`` keep
    working; the ``content`` field is additive.
    """

    event_type: Literal["working_memory_update"] = "working_memory_update"
    phase_name: str
    content_length: int
    content: str | None = None  # T-A1: full working memory text


class DeadEndPrunedEvent(_EventBase):
    event_type: Literal["dead_end_pruned"] = "dead_end_pruned"
    phase_name: str
    summary: str


class CompactionEvent(_EventBase):
    """History compaction occurred — some message pairs were dropped.

    Tier 1 Commit B (T-A2) — Gemini Q3 external-link scheme: the event
    itself carries a short ``removed_summary`` (human-readable, a few
    hundred chars) and a ``content_ref`` pointing at a sidecar JSON file
    holding the full dropped messages. The sidecar path is written by
    StorageManager so it lives under the normal run-retention policy.
    """

    event_type: Literal["compaction"] = "compaction"
    phase_name: str
    removed_pairs: int
    removed_summary: str | None = None  # T-A2: short readable summary
    content_ref: str | None = None  # T-A2: relative path to sidecar JSON


class AmbiguityReportEvent(_EventBase):
    event_type: Literal["ambiguity_report"] = "ambiguity_report"
    phase_name: str
    ambiguity_type: str
    question: str
    decision: str


class AmbiguityLoggedEvent(_EventBase):
    """V0.3.0 event emitted after log_ambiguity records a decision."""

    event_type: Literal["ambiguity_logged"] = "ambiguity_logged"
    phase_name: str | None = None
    ambiguity_type: str
    question: str
    decision: str
    reason: str = ""
    related_refs: list[str] = Field(default_factory=list)
    related_protocols: list[str] = Field(default_factory=list)


class BuiltinSubagentEnterEvent(_EventBase):
    """V0.3.0 builtin subagent invocation start."""

    event_type: Literal["builtin_subagent_enter"] = "builtin_subagent_enter"
    run_id: str | None = None
    phase_name: str
    builtin_name: str
    payload: dict[str, Any] = Field(default_factory=dict)


class BuiltinSubagentExitEvent(_EventBase):
    """V0.3.0 builtin subagent invocation success."""

    event_type: Literal["builtin_subagent_exit"] = "builtin_subagent_exit"
    run_id: str | None = None
    phase_name: str
    builtin_name: str
    payload: dict[str, Any] = Field(default_factory=dict)


class BuiltinSubagentFallbackEvent(_EventBase):
    """V0.3.0 builtin subagent fallback path."""

    event_type: Literal["builtin_subagent_fallback"] = "builtin_subagent_fallback"
    run_id: str | None = None
    phase_name: str
    builtin_name: str
    fallback_reason: Literal[
        "remote_timeout",
        "remote_error",
        "config_missing",
        "invalid_output",
        "local_io_error",
    ]
    fallback_strategy: str
    excerpt_token_limit: int | None = None
    warning: str = ""


class PromptCapturedEvent(_EventBase):
    """Fired by the chat model right before the LLM round-trip.

    ``template_source`` is the filename / id of the prompt template when
    the caller tracks one; ``variables`` is the rendered placeholder dict;
    ``resolved_prompt`` is the final message list after template expansion.
    ``loop_index`` is the 1-based count of this LLM call within the
    phase's ReAct loop: the first call inside a phase emits
    ``loop_index=1``, the second emits ``2``, and so on. The counter
    naturally restarts at 1 in each phase because the model that counts is
    built per phase.
    """

    event_type: Literal["prompt_captured"] = "prompt_captured"
    phase_name: str
    llm_role: str | None = None
    resolved_model: str | None = None
    template_source: str | None = None
    variables: dict[str, Any] = Field(default_factory=dict)
    resolved_prompt: list[dict[str, Any]] = Field(default_factory=list)
    loop_index: int = Field(default=1, ge=1)


class LLMFallbackEvent(_EventBase):
    """Fired by ModelResolver when a peer-group fallback swaps the provider."""

    event_type: Literal["llm_fallback"] = "llm_fallback"
    phase_name: str
    from_provider: str
    to_provider: str
    reason: str
    code: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class BlackboardReduceEvent(_EventBase):
    event_type: Literal["blackboard_reduce"] = "blackboard_reduce"
    from_phase: str | None
    to_phase: str
    changed_keys: list[str]
    blackboard_snapshot: dict[str, Any]
    reducer: str


class InputDispatchEvent(_EventBase):
    event_type: Literal["input_dispatch"] = "input_dispatch"
    from_phase: str | None
    to_phase: str
    changed_keys: list[str]
    blackboard_snapshot: dict[str, Any]
    dispatched_keys: list[str]
    branch_index: int | None


class InputFileInjectedEvent(_EventBase):
    event_type: Literal["input_file_injected"] = "input_file_injected"
    from_phase: str | None
    to_phase: str
    changed_keys: list[str]
    blackboard_snapshot: dict[str, Any]
    file_ref: str
    target_field: str


# ---------------------------------------------------------------------------
# Tier 1 Commit A — core lifecycle events (T-B1 / T-B5 / T-B12 / T-B14)
# ---------------------------------------------------------------------------


class RunStartedEvent(_EventBase):
    """Fired once at harness.run() entry, after RunContext is constructed."""

    event_type: Literal["run_started"] = "run_started"
    run_id: str
    thread_id: str
    is_resume: bool = False
    checkpoint_id: str | None = None
    checkpoint_ns: str | None = None
    # Gemini Q5: full initial_context; goes through to_jsonable_dict once
    # Commit B lands that helper. Until then callers pass already-JSONable dicts.
    initial_context: dict[str, Any] = Field(default_factory=dict)


class RunEndedEvent(_EventBase):
    """Fired once at harness.run() exit (success or handled error)."""

    event_type: Literal["run_ended"] = "run_ended"
    run_id: str
    thread_id: str
    status: Literal["completed", "crashed", "interrupted"] = "completed"
    final_context: dict[str, Any] = Field(default_factory=dict)
    wall_time_seconds: float


class ValidationPassEvent(_EventBase):
    """Fired when a phase validator returns (True, []). Complements ValidationFail."""

    event_type: Literal["validation_pass"] = "validation_pass"
    phase_name: str
    retry_count: int  # how many retries were consumed before the pass (0 = first-try)


class RetryExhaustedEvent(_EventBase):
    """Fired when `current_retries >= max_retries` and the phase is force-degraded."""

    event_type: Literal["retry_exhausted"] = "retry_exhausted"
    phase_name: str
    max_retries: int
    final_errors: list[str] = Field(default_factory=list)


class ModelResolvedEvent(_EventBase):
    """Fired by the harness after resolver.resolve() picks a model.

    Tier 1 Commit B (T-B2). Lets Studio show *why* a phase ended up on a
    specific model/provider (which tier, whether model_override was used,
    which call chain the resolver actually picked).
    """

    event_type: Literal["model_resolved"] = "model_resolved"
    phase_name: str
    tier: str  # phase.tier
    role_name: str  # tier or synthetic "_model_override::..."
    resolved_model: str | None = None  # model code from llm_roles.yaml
    thinking_enabled: bool | None = None
    model_override: str | None = None
    call_chain: list[str] = Field(default_factory=list)  # ["OC_CL/claude-sonnet-4-6", ...]


class ArtifactSavedEvent(_EventBase):
    """Fired by StorageManager after persisting an artifact to disk.

    Tier 1 Commit B (T-B10). Lets Studio's artifact panel render directly
    from the event stream without polling the filesystem.
    """

    event_type: Literal["artifact_saved"] = "artifact_saved"
    phase_name: str | None = None  # None when the save happens outside a phase
    name: str
    path: str  # absolute or run-relative path
    size_bytes: int


# Tier 1 Commit C — Subgraph boundary marker events (SubgraphEnterEvent /
# SubgraphExitEvent) were removed in MVP-0 B1 (2026-04-28) along with the
# subgraph runtime that emitted them. The ParallelMapGroup events below
# stay because they belong to ``builtin.parallel_map``, an unrelated tool
# that survives MVP-0.


class ParallelMapGroupStartedEvent(_EventBase):
    """Fired by builtin.parallel_map right before ThreadPoolExecutor fan-out.

    Carries the group_key that every child sub-run stamps on its own
    prompt_captured events so Studio can visually fold them.
    """

    event_type: Literal["parallel_map_group_started"] = "parallel_map_group_started"
    group_key: str  # uuid shared across all siblings in this fan-out
    skill_path: str  # child skill being fanned out
    item_count: int
    max_concurrent: int
    item_as: str  # parameter name the children receive


class ParallelMapGroupEndedEvent(_EventBase):
    event_type: Literal["parallel_map_group_ended"] = "parallel_map_group_ended"
    group_key: str
    succeeded: int
    failed: int
    wall_time_seconds: float


class AgentLoopIterationEvent(_EventBase):
    """Fired by a middleware at the top of each DeerFlow agent-loop iteration.

    Tier 2 (T-B4). Gives Studio a per-iteration anchor so subsequent
    LLMCall / ToolCall events emitted during that iteration can be
    grouped, rather than just relying on timestamp order (which breaks
    once parallel_map sub-runs interleave events).
    """

    event_type: Literal["agent_loop_iteration"] = "agent_loop_iteration"
    phase_name: str
    iteration: int  # 1-based; incremented for every before_model hook


class InterruptedEvent(_EventBase):
    """Fired when an agent middleware suspends execution awaiting HITL input.

    Tier 2 (T-B11). Complements :func:`GraphAgentHarness.get_thread_status`:
    the query surface lets Studio *ask* "is this thread paused?"; this
    event tells Studio *when* the pause happened and why, so the UI can
    highlight the exact timeline moment a pipeline went idle waiting on
    a human.
    """

    event_type: Literal["interrupted"] = "interrupted"
    phase_name: str
    thread_id: str
    checkpoint_id: str | None = None
    checkpoint_ns: str | None = None
    namespace: str | None = None
    ns: str | None = None
    # Mirrors the clarification payload shape returned by get_thread_status
    # so the front-end can reuse the same rendering code path.
    question: str | None = None
    clarification_type: str | None = None
    options: list[str] = Field(default_factory=list)


class ResumedEvent(_EventBase):
    """Fired by :meth:`GraphAgentHarness.resume` when a human-in-the-loop run restarts.

    Tier 2 (T-B11).
    """

    event_type: Literal["resumed"] = "resumed"
    thread_id: str
    # Human-provided input that unblocked the interrupt. Kept verbatim so
    # the replay is fully reproducible — no truncation beyond what the
    # LLM prompt itself would already enforce downstream.
    human_input: str
    resumed_from_phase: str | None = None
    checkpoint_id: str | None = None
    checkpoint_ns: str | None = None
    namespace: str | None = None
    ns: str | None = None


class HeartbeatEvent(_EventBase):
    """Periodic pulse during a long-running phase.

    Tier 1 Commit D (T-B13). Gemini-approved purpose: keep Studio's
    frontend WebSocket alive + surface memory-pressure symptoms on
    tasks where 30+ seconds between "real" events is common (video
    generation, multi-chapter long-form analysis, DeepSeek high-
    reasoning turns). 30-second cadence, sourced from a threading-
    based timer inside harness.run so it keeps ticking even while the
    main loop is blocked in a synchronous tool call.
    """

    event_type: Literal["heartbeat"] = "heartbeat"
    current_phase: str | None = None  # None when between phases / during startup
    elapsed_seconds: float
    memory_usage_mb: float | None = None  # None when psutil / resource reading fails


class ThreadCleanedUpEvent(_EventBase):
    """Fired after runner.run_skill deletes successful-run checkpoints."""

    event_type: Literal["thread_cleaned_up"] = "thread_cleaned_up"
    thread_id: str
    checkpoint_count_at_cleanup: int | None = None


class InternalErrorEvent(_EventBase):
    """Non-business Python exception (OOM / NetworkTimeout / unexpected).

    Distinguishes engine-layer crashes from ValidationFail / RetryExhausted
    which are business-domain failures. Emitted at the three harness entry
    points Gemini flagged (Q2): ``harness.run`` / ``harness.resume`` /
    ``subgraph.run``, right before the exception is re-raised.
    """

    event_type: Literal["internal_error"] = "internal_error"
    entry_point: Literal["run", "resume", "subgraph"]
    error_type: str  # exception class name (e.g. "RuntimeError")
    error_message: str  # str(exc)
    traceback: str  # traceback.format_exc()


CallbackEvent = Annotated[
    PhaseStartEvent
    | PredictChainStartEvent
    | PhaseEndEvent
    | LLMCallEvent
    | ToolCallStartedEvent
    | ToolCallEvent
    | ValidationFailEvent
    | RetryEvent
    | FinishTaskEvent
    | NudgeEvent
    | WorkingMemoryUpdateEvent
    | DeadEndPrunedEvent
    | CompactionEvent
    | AmbiguityReportEvent
    | AmbiguityLoggedEvent
    | BuiltinSubagentEnterEvent
    | BuiltinSubagentExitEvent
    | BuiltinSubagentFallbackEvent
    | PromptCapturedEvent
    | LLMFallbackEvent
    | RunStartedEvent
    | RunEndedEvent
    | ValidationPassEvent
    | RetryExhaustedEvent
    | InternalErrorEvent
    | ModelResolvedEvent
    | ArtifactSavedEvent
    | ParallelMapGroupStartedEvent
    | ParallelMapGroupEndedEvent
    | HeartbeatEvent
    | ThreadCleanedUpEvent
    | InterruptedEvent
    | ResumedEvent
    | AgentLoopIterationEvent
    | BlackboardReduceEvent
    | InputDispatchEvent
    | InputFileInjectedEvent,
    Field(discriminator="event_type"),
]


__all__ = [
    "SCHEMA_VERSION",
    "CallbackEvent",
    "PhaseStartEvent",
    "PredictChainStartEvent",
    "PhaseEndEvent",
    "LLMCallEvent",
    "ToolCallStartedEvent",
    "ToolCallEvent",
    "ValidationFailEvent",
    "RetryEvent",
    "FinishTaskEvent",
    "NudgeEvent",
    "WorkingMemoryUpdateEvent",
    "DeadEndPrunedEvent",
    "CompactionEvent",
    "AmbiguityReportEvent",
    "AmbiguityLoggedEvent",
    "BuiltinSubagentEnterEvent",
    "BuiltinSubagentExitEvent",
    "BuiltinSubagentFallbackEvent",
    "PromptCapturedEvent",
    "LLMFallbackEvent",
    "RunStartedEvent",
    "RunEndedEvent",
    "ValidationPassEvent",
    "RetryExhaustedEvent",
    "InternalErrorEvent",
    "ModelResolvedEvent",
    "ArtifactSavedEvent",
    "ParallelMapGroupStartedEvent",
    "ParallelMapGroupEndedEvent",
    "HeartbeatEvent",
    "ThreadCleanedUpEvent",
    "InterruptedEvent",
    "ResumedEvent",
    "AgentLoopIterationEvent",
    "BlackboardReduceEvent",
    "InputDispatchEvent",
    "InputFileInjectedEvent",
]
