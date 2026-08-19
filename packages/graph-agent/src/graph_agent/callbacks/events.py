"""Typed CallbackEvent union for graph_agent runs.

Every observable runtime event is modelled as a standalone Pydantic class
with a ``Literal[event_type]`` tag, then brought together as the
discriminated union :data:`CallbackEvent`. Studio / downstream tooling
deserialise ``trace.jsonl`` into well-typed objects through this union;
every variant listed here has at least one live emission point in the
engine or gateway.

Parallel-map grouping: every event optionally carries ``sub_run_id`` /
``group_key`` so the Studio timeline can fold concurrent child runs that
share a ``parallel_map`` invocation.

Note: this module intentionally does **not** use ``from __future__ import
annotations`` — Pydantic needs the ``Literal`` tag expressions to be
evaluated at class-definition time so the discriminated-union dispatch
works without explicit ``model_rebuild`` calls at import.
"""

from datetime import UTC, datetime
from typing import Annotated, Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION: Literal["1.0"] = "1.0"


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class _EventBase(BaseModel):
    """Fields shared by every ``CallbackEvent`` variant."""

    model_config = ConfigDict(extra="forbid")

    # Whether this kind of frame belongs in the permanent record. A step frame
    # does: it is what `report.md`, evidence queries, canvas node state and the
    # token totals are all read back out of. A delta frame does not: it may be
    # merged with its neighbours or dropped under backpressure, and a record
    # that keeps some of a droppable stream describes a run nobody had.
    #
    # It is a ClassVar, not a field: the answer is decided by the kind of frame,
    # so an instance carrying its own copy could contradict its own type.
    persisted: ClassVar[bool] = True

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    timestamp: str = Field(default_factory=_utc_now_iso)
    # Parallel-map grouping (Task 4.3). Both are set by ``parallel_map`` when it
    # propagates child-skill events to a parent callback; otherwise ``None``.
    sub_run_id: str | None = None
    group_key: str | None = None
    #: Dot-joined chain of enclosing SUBGRAPH phase ids, root first (e.g.
    #: ``"event_timeline.extrac"``); ``None`` for events emitted at root level.
    #: Two subgraphs may both own a phase named ``review``, so ``phase_name``
    #: alone cannot tell their events apart — run 2026-08-19T01-56-15_d0733362
    #: folded 13 llm_calls from two different ``review`` nodes into one report
    #: row and lost a ``setup`` node entirely. Stamped centrally in
    #: ``_safe_emit_event`` from the scope ``_build_subgraph_node`` maintains.
    subgraph_path: str | None = None


class PhaseStartEvent(_EventBase):
    event_type: Literal["phase_start"] = "phase_start"
    phase_name: str
    #: Which execution of this phase — an outer iterate/batch loop runs the
    #: same phase several times, and each run is its own segment. Distinct
    #: from ``AgentLoopIterationEvent.iteration``, which counts model turns
    #: INSIDE one execution (decision 2026-08-15 edge-as-run-segment, D2).
    phase_execution_id: str
    context: dict[str, Any] = Field(default_factory=dict)


class PredictChainStartEvent(_EventBase):
    event_type: Literal["predict_chain_start"] = "predict_chain_start"
    metadata: dict[str, Any] = Field(default_factory=dict)


class PhaseEndEvent(_EventBase):
    event_type: Literal["phase_end"] = "phase_end"
    phase_name: str
    phase_execution_id: str
    context: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)


class LLMCallEvent(_EventBase):
    """What one LLM round-trip cost and what it produced.

    ``response_data`` is required, and that is the whole reason the deltas
    streaming the same text are allowed to be dropped: the answer is written
    down once, in full, here. An optional field would make "the answer exists
    somewhere" depend on nothing, and the delta stream — which is explicitly
    droppable — would silently become the only copy.

    The prompt is deliberately absent. It travelled on the opening frame, and a
    second copy would be both the largest payload of a run written twice and a
    second truth that can drift from the first.
    """

    event_type: Literal["llm_call"] = "llm_call"
    phase_name: str
    # Repeats the identity minted on the opening frame — see PromptCapturedEvent.
    step_id: str
    input_tokens: int
    output_tokens: int
    # The model that actually answered this call, as the provider reported it on
    # the response. A fallback chain means the role does not decide it up front,
    # so per-call is the only place it is true.
    resolved_model: str | None = None
    response_data: dict[str, Any]
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


class NudgeEvent(_EventBase):
    event_type: Literal["nudge"] = "nudge"
    phase_name: str
    nudge_count: int
    nudge_type: str = "standard"
    #: Full sentence saying what was injected and why (machinery-speaks D4).
    message: str = ""


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
    """History compaction occurred — messages were summarized out of context.

    External-link scheme (T-A2 Gemini Q3): the event itself carries a short
    ``removed_summary`` (human-readable, a few hundred chars) and a
    ``content_ref`` pointing at a sidecar JSON file holding the removed
    messages in full. The sidecar lives under the run directory, so it is
    covered by whatever retention applies to the run itself.
    """

    event_type: Literal["compaction"] = "compaction"
    phase_name: str
    #: How many messages left the context window in this compaction.
    removed_message_count: int
    removed_summary: str | None = None  # short readable summary
    content_ref: str | None = None  # path to the sidecar JSON file


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
    # The identity of the call this frame opens. Its closing frame and every
    # delta in between repeat it, because a reader watching several concurrent
    # calls has no other way to tell which one a piece belongs to.
    step_id: str
    llm_role: str | None = None
    resolved_model: str | None = None
    template_source: str | None = None
    variables: dict[str, Any] = Field(default_factory=dict)
    resolved_prompt: list[dict[str, Any]] = Field(default_factory=list)
    loop_index: int = Field(default=1, ge=1)


class LLMRouteDecisionEvent(_EventBase):
    """One decision the gateway made while getting an answer for a role.

    Skipping a circuit-broken route, failing a probe, retrying the same route,
    doubling a budget, falling back, and finally answering are the same kind of
    fact with different outcomes, so ``decision`` is a closed set rather than
    this being several event types.

    ``voided_streamed_answer`` says the decision also discarded content that had
    already been streamed to whoever is watching — escalating and falling back
    both replace the answer rather than continuing it, and a surface showing the
    abandoned text has no other way to learn it is stale.

    The gateway defines its own copy of this shape (it does not depend on this
    package); the two are kept in step by hand.
    """

    event_type: Literal["llm_route_decision"] = "llm_route_decision"
    phase_name: str
    decision: Literal[
        "skipped_circuit_open",
        "probe_failed",
        "retried_same_route",
        "dropped_rejected_settings",
        "escalated_budget",
        "fell_back",
        "failed_terminal",
        "answered",
        "exhausted",
    ]
    route_id: str | None = None
    endpoint_id: str | None = None
    provider_model_id: str | None = None
    protocol: str | None = None
    reason: str | None = None
    provider_status_code: int | None = None
    next_route_id: str | None = None
    voided_streamed_answer: bool = False
    code: str | None = None


class LLMCallSettingsEvent(_EventBase):
    """What one call asked its route to do, and what became of each of it.

    Separate from :class:`LLMRouteDecisionEvent` because they answer different
    questions: that one says which route produced the answer and why it
    changed, this one says what parameters the answer was produced under.

    ``settings`` carries one entry per setting the user actually chose —
    defaults nobody picked are left out, or the entries that matter would be
    buried under the ones that do not. Each entry says what was requested and
    one verdict from a closed set: ``applied`` when the answer itself shows it
    took effect, ``sent`` when nothing can confirm either way, ``adjusted``
    when the value had to be moved to fit the route, ``unsupported`` when the
    protocol had nowhere to put it, ``rejected`` when the provider refused it,
    and ``ignored`` when it was accepted and the answer contradicts it.

    The gateway defines its own copy of this shape (it does not depend on this
    package); the two are kept in step by hand.
    """

    event_type: Literal["llm_call_settings"] = "llm_call_settings"
    phase_name: str
    settings: list[dict[str, Any]] = Field(default_factory=list)
    route_id: str | None = None
    provider_model_id: str | None = None
    protocol: str | None = None
    code: str | None = None


class LLMDeltaEvent(_EventBase):
    """A piece of an answer that is still arriving.

    One event with a ``channel``, not one event type per channel: the model
    producing reasoning and the model producing its answer are the same fact —
    a step emitted a bit more output — differing only in which output. A third
    channel is a new member of that set, not a new contract.

    ``restarts_step`` says the pieces delivered so far belong to an attempt that
    was abandoned. Truncation is only knowable once a response ends, so a retry
    necessarily happens after text has already been shown; whoever is displaying
    it has to hear that it no longer counts.

    Not persisted (see ``_EventBase.persisted``): the text spelled out here is
    written whole on the closing ``llm_call`` frame, which is what makes losing
    a delta harmless.
    """

    persisted: ClassVar[bool] = False

    event_type: Literal["llm_delta"] = "llm_delta"
    phase_name: str
    step_id: str
    channel: Literal["text", "thinking"]
    text: str = ""
    restarts_step: bool = False


class EdgeStartEvent(_EventBase):
    """One transition between phases began.

    A transition is the run segment between an upstream phase execution
    ending and the downstream phase execution starting — everything the
    machinery does on the way (blackboard reduction, input dispatch, input
    file injection) happens inside it. It is a segment in its own right,
    peer to a phase segment, so an empty transition still opens and closes:
    "nothing happened between these two nodes" is an observation, not a gap
    in the record (decision 2026-08-15 edge-as-run-segment, D1).

    ``from_phase_execution_ids`` is plural because a fan-in transition
    genuinely joins several upstream executions; a single upstream is a list
    of one, not a special case (D3).
    """

    event_type: Literal["edge_start"] = "edge_start"
    edge_transition_id: str
    from_phases: list[str]
    from_phase_execution_ids: list[str]
    to_phase: str
    to_phase_execution_id: str
    branch_index: int | None = None


class EdgeEndEvent(_EventBase):
    """The same transition closed, with what it handed the downstream phase."""

    event_type: Literal["edge_end"] = "edge_end"
    edge_transition_id: str
    from_phases: list[str]
    from_phase_execution_ids: list[str]
    to_phase: str
    to_phase_execution_id: str
    branch_index: int | None = None
    changed_keys: list[str] = Field(default_factory=list)
    blackboard_snapshot: dict[str, Any] = Field(default_factory=dict)
    #: How many edge operations ran inside this transition. Zero is a valid
    #: and meaningful answer.
    operation_count: int = 0


class BlackboardReduceEvent(_EventBase):
    event_type: Literal["blackboard_reduce"] = "blackboard_reduce"
    edge_transition_id: str
    from_phases: list[str]
    to_phase: str
    changed_keys: list[str]
    blackboard_snapshot: dict[str, Any]
    reducer: str


class InputDispatchEvent(_EventBase):
    event_type: Literal["input_dispatch"] = "input_dispatch"
    edge_transition_id: str
    from_phases: list[str]
    to_phase: str
    changed_keys: list[str]
    blackboard_snapshot: dict[str, Any]
    dispatched_keys: list[str]
    branch_index: int | None


class InputFileInjectedEvent(_EventBase):
    event_type: Literal["input_file_injected"] = "input_file_injected"
    edge_transition_id: str
    from_phases: list[str]
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


class FinishTaskVerdictEvent(_EventBase):
    """What became of one finish_task submission: taken, refused, or repeated.

    The verdict is a decision that steers the run — a refusal goes back to the
    model as retry feedback, an acceptance writes the phase's result — and a
    decision that steers the run must say so itself (glass-box decision D4:
    report decisions, not passages). ``message`` is the machine speaking in a
    whole sentence; a reader should not have to assemble the story from fields.
    """

    event_type: Literal["finish_task_verdict"] = "finish_task_verdict"
    phase_name: str
    verdict: Literal["accepted", "rejected", "duplicate"]
    message: str
    #: Why a rejected submission was rejected; empty for the other verdicts.
    errors: list[str] = Field(default_factory=list)
    #: How many parsed items an accepted submission carried; None otherwise.
    item_count: int | None = None
    #: Pipeline narration, one full sentence per stage that actually ran:
    #: md2json parse result, per-block schema check, business-validator
    #: conclusion. Answers "which machinery touched this submission" without
    #: the reader reverse-engineering the middleware.
    details: list[str] = Field(default_factory=list)


class LoopDetectedEvent(_EventBase):
    """LoopDetectionMiddleware found a no-progress tool loop and injected a
    corrective diagnostic into the conversation. That injection changes what
    the model sees next, so it must be visible in the trace."""

    event_type: Literal["loop_detected"] = "loop_detected"
    phase_name: str
    tool_name: str
    #: How many identical (tool, result) pairs sat inside the sliding window.
    count: int
    message: str


class ProtocolViolationEvent(_EventBase):
    """ProtocolValidationMiddleware found the WorkflowState violating a
    framework contract and is about to break the agent loop. Emitted before
    the raise so the trace names the violations even when the run dies."""

    event_type: Literal["protocol_violation"] = "protocol_violation"
    phase_name: str
    #: Which LLM-step boundary the check ran at: before_model / after_model.
    boundary: str
    #: One "label: detail" line per violated contract.
    violations: list[str] = Field(default_factory=list)
    message: str


class ToolErrorHandledEvent(_EventBase):
    """ToolErrorHandlingMiddleware swallowed a tool exception and turned it
    into an error ToolMessage the model reads as feedback. Swallowing an error
    changes the run's course, so it must be visible in the trace."""

    event_type: Literal["tool_error_handled"] = "tool_error_handled"
    phase_name: str
    tool_name: str
    #: "ExceptionType: str(exc)" — what actually blew up.
    error: str
    message: str


class ToolHistoryRepairedEvent(_EventBase):
    """ToolHistoryIntegrityMiddleware rewrote the outgoing message history to
    satisfy the provider contract (each AI tool_calls immediately answered).
    Emitted only when something actually changed — a legal history is 路过."""

    event_type: Literal["tool_history_repaired"] = "tool_history_repaired"
    phase_name: str
    #: Orphaned tool_calls given a synthetic ToolMessage.
    synthesized_count: int
    #: Stray ToolMessages (answering nothing in this history) dropped.
    dropped_count: int
    message: str


class RuntimeInputInjectedEvent(_EventBase):
    """RuntimeInputMiddleware handed a model call the phase's declared inputs.

    Delivery happens per model call (the block is given to the model, never
    written back to state), so one event marks each turn the model actually
    received the inputs. A call that already carries the identical block is a
    no-op and stays silent."""

    event_type: Literal["runtime_input_injected"] = "runtime_input_injected"
    phase_name: str
    keys: list[str] = Field(default_factory=list)
    message: str


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


CallbackEvent = Annotated[
    PhaseStartEvent
    | PredictChainStartEvent
    | PhaseEndEvent
    | LLMCallEvent
    | LLMDeltaEvent
    | ToolCallStartedEvent
    | ToolCallEvent
    | NudgeEvent
    | WorkingMemoryUpdateEvent
    | DeadEndPrunedEvent
    | CompactionEvent
    | AmbiguityLoggedEvent
    | BuiltinSubagentEnterEvent
    | BuiltinSubagentExitEvent
    | BuiltinSubagentFallbackEvent
    | PromptCapturedEvent
    | LLMRouteDecisionEvent
    | LLMCallSettingsEvent
    | RunStartedEvent
    | RunEndedEvent
    | FinishTaskVerdictEvent
    | LoopDetectedEvent
    | ProtocolViolationEvent
    | ToolErrorHandledEvent
    | ToolHistoryRepairedEvent
    | RuntimeInputInjectedEvent
    | ArtifactSavedEvent
    | ParallelMapGroupStartedEvent
    | ParallelMapGroupEndedEvent
    | InterruptedEvent
    | ResumedEvent
    | AgentLoopIterationEvent
    | EdgeStartEvent
    | EdgeEndEvent
    | BlackboardReduceEvent
    | InputDispatchEvent
    | InputFileInjectedEvent,
    Field(discriminator="event_type"),
]


__all__ = [
    "SCHEMA_VERSION",
    "CallbackEvent",
    "EdgeStartEvent",
    "EdgeEndEvent",
    "PhaseStartEvent",
    "PredictChainStartEvent",
    "PhaseEndEvent",
    "LLMCallEvent",
    "LLMDeltaEvent",
    "ToolCallStartedEvent",
    "ToolCallEvent",
    "NudgeEvent",
    "WorkingMemoryUpdateEvent",
    "DeadEndPrunedEvent",
    "CompactionEvent",
    "AmbiguityLoggedEvent",
    "BuiltinSubagentEnterEvent",
    "BuiltinSubagentExitEvent",
    "BuiltinSubagentFallbackEvent",
    "PromptCapturedEvent",
    "LLMCallSettingsEvent",
    "LLMRouteDecisionEvent",
    "RunStartedEvent",
    "RunEndedEvent",
    "FinishTaskVerdictEvent",
    "LoopDetectedEvent",
    "ProtocolViolationEvent",
    "ToolErrorHandledEvent",
    "ToolHistoryRepairedEvent",
    "RuntimeInputInjectedEvent",
    "ArtifactSavedEvent",
    "ParallelMapGroupStartedEvent",
    "ParallelMapGroupEndedEvent",
    "InterruptedEvent",
    "ResumedEvent",
    "AgentLoopIterationEvent",
    "BlackboardReduceEvent",
    "InputDispatchEvent",
    "InputFileInjectedEvent",
]
