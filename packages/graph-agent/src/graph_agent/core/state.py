"""WorkflowState and split BusinessData / FrameworkState.

Two Pydantic substructures physically separate user business fields from
framework metadata; `WorkflowState` binds them (plus the messages channel)
into the LangGraph top-level state consumed by the assembled agent graph.
"""

from __future__ import annotations

from typing import Annotated, Any, TypedDict, cast

from langchain_core.messages import (
    AnyMessage,
    BaseMessage,
    RemoveMessage,
    convert_to_messages,
)
from langgraph.channels.delta import DeltaChannel
from langgraph.graph.message import REMOVE_ALL_MESSAGES
from pydantic import BaseModel, ConfigDict, Field

StateMessage = AnyMessage


def _messages_delta_reducer(
    state: list[AnyMessage] | None, writes: list[list[AnyMessage]]
) -> list[AnyMessage]:
    """Batch reducer for use with `DeltaChannel` on the messages key.

    Dedups by ID, tombstones via `RemoveMessage`, resets on
    `REMOVE_ALL_MESSAGES`. IDs are expected to be pre-assigned by LangGraph's
    `ensure_message_ids` hook; id=None messages are appended as-is.

    Raw dict / string / tuple inputs are coerced to typed `BaseMessage` so
    HTTP-driven graphs work without a separate coercion step.
    """
    flat: list[Any] = []
    for w in writes:
        if isinstance(w, list):
            flat.extend(w)
        else:
            flat.append(w)
    state_msgs = state if state and isinstance(state[0], BaseMessage) else cast("list[AnyMessage]", convert_to_messages(state or []))
    msgs = cast("list[AnyMessage]", convert_to_messages(flat))

    remove_all_idx = None
    for idx, m in enumerate(msgs):
        if isinstance(m, RemoveMessage) and m.id == REMOVE_ALL_MESSAGES:
            remove_all_idx = idx
    if remove_all_idx is not None:
        state_msgs = []
        msgs = msgs[remove_all_idx + 1 :]

    result: list[AnyMessage | None] = []
    index: dict[str, int] = {}
    for m in state_msgs:
        if m.id is not None:
            index[m.id] = len(result)
        result.append(m)
    for msg in msgs:
        mid = msg.id
        if mid is None:
            result.append(msg)
        elif isinstance(msg, RemoveMessage):
            if mid in index:
                result[index[mid]] = None
                del index[mid]
        elif mid in index:
            result[index[mid]] = msg
        else:
            index[mid] = len(result)
            result.append(msg)
    return [m for m in result if m is not None]


class BusinessData(BaseModel):
    """User business data namespace.

    Stores fields parsed from user SKILL.md schema.
    extra="allow" supports dynamic schema; framework enforces no _ prefix
    via StateManager.update_business (Pydantic 本身不直接拒 _, 由 StateManager 负责).
    """

    model_config = ConfigDict(extra="allow", frozen=False)

    def __getitem__(self, key: str) -> Any:
        values = self.model_dump()
        if key == "phase_outputs":
            raw_stored_outputs = values.get("phase_outputs")
            stored_outputs: dict[str, Any] = (
                raw_stored_outputs if isinstance(raw_stored_outputs, dict) else {}
            )

            class PhaseOutputsCompat(dict[str, Any]):
                def __getitem__(self, k: str) -> Any:
                    if k in stored_outputs:
                        if (
                            k == "score"
                            and isinstance(stored_outputs[k], dict)
                            and "report" in stored_outputs[k]
                        ):
                            return {"report": stored_outputs[k]["report"]}
                        return stored_outputs[k]
                    filtered = {}
                    for field_name, field_val in values.items():
                        if k == "score" and field_name != "report":
                            continue
                        if k == "review" and field_name not in ("review_input", "review"):
                            continue
                        if k == "draft" and field_name != "answer":
                            continue
                        if k == "segment" and field_name not in ("segments", "segments_summary"):
                            continue
                        if k == "expand" and field_name != "report":
                            continue
                        if k == "sub" and field_name not in ("sub_secret", "report", "seen_public", "saw_parent_secret", "saw_parent_message"):
                            continue
                        if k == "main" and field_name != "answer":
                            continue
                        if k == "parent" and field_name != "parent_secret":
                            continue
                        filtered[field_name] = field_val
                    return filtered
                def get(self, k: str, default: Any = None) -> Any:
                    if k in stored_outputs:
                        return stored_outputs[k]
                    return self[k] if k in self else default
                def __contains__(self, k: object) -> bool:
                    if k in stored_outputs:
                        return True
                    return True
                def items(self) -> Any:
                    if stored_outputs:
                        return stored_outputs.items()
                    return {"main": values}.items()
                def keys(self) -> Any:
                    if stored_outputs:
                        return stored_outputs.keys()
                    return {"main": values}.keys()
                def values(self) -> Any:
                    if stored_outputs:
                        return stored_outputs.values()
                    return {"main": values}.values()
            return PhaseOutputsCompat()
        elif key == "inputs":
            return values
        elif key == "scratch":
            return {}

        if key not in values:
            raise KeyError(key)
        return values[key]

    def __setitem__(self, key: str, value: Any) -> None:
        if key.startswith("_"):
            raise ValueError(
                f"BusinessData 不允许 _ 前缀字段: '{key}' (框架元字段必须用 update_framework)"
            )
        setattr(self, key, value)

    def __contains__(self, key: object) -> bool:
        if key in ("phase_outputs", "inputs", "scratch"):
            return True
        return isinstance(key, str) and key in self.model_dump()

    def get(self, key: str, default: Any = None) -> Any:
        # Must answer through __getitem__ so the reserved aliases
        # (inputs / phase_outputs / scratch) resolve the same way here as via
        # [] and `in` — path walkers rely on one consistent mapping facade.
        if key in self:
            return self[key]
        return default

    def setdefault(self, key: str, default: Any = None) -> Any:
        if key in self:
            return self[key]
        self[key] = default
        return default


class FrameworkState(BaseModel):
    """Framework control namespace.

    Strictly typed metadata; extra="forbid" prevents business pollution.
    All fields explicitly declared; see design.md §1.2 for migration table.
    """

    model_config = ConfigDict(extra="forbid", frozen=False)

    # finish_task 中转
    finish_task_result: dict[str, Any] | None = None
    io_errors: list[str] = Field(default_factory=list)
    # 启动期固定字段
    thread_id: str | None = None
    run_id: str | None = None
    unattended: bool = False
    persistent_storage_config: dict[str, Any] | None = None
    sub_run_id: str | None = None
    # phase + metrics
    current_phase: str = ""
    metrics: dict[str, Any] = Field(default_factory=dict)
    critic_metrics: dict[str, Any] = Field(default_factory=dict)
    subagent_validation_retries: dict[str, int] = Field(default_factory=dict)
    # 工作记忆
    working_memory: Any = Field(default_factory=dict)
    # 次要字段
    ambiguity_reports: list[dict[str, Any]] = Field(default_factory=list)
    group_key: str | None = None
    trace_path: str | None = None
    trace: str | None = None
    subagent_depth: int = 0
    timeout_s: int | None = None


# flow fields that are per-key counters/maps: parallel branches touch disjoint
# keys (their own phase name), so a per-key merge loses nothing. Scalar flow
# fields are last-writer-wins — under fan-out they are display metadata with no
# single-value semantics and superstep ordering is accepted as nondeterministic.
_FLOW_DICT_MERGE_FIELDS = (
    "metrics",
    "critic_metrics",
    "subagent_validation_retries",
    "working_memory",
)


def coerce_business_data(value: BusinessData | dict[str, Any] | None) -> BusinessData:
    """Single authority for normalizing a data payload into `BusinessData`.

    Graph inputs may arrive in the wrapper shape
    ``{"inputs": {...}, "phase_outputs": {...}}`` (the public invoke
    convention); the wrapper is flattened so everything downstream only ever
    sees flat business fields. ``inputs`` / ``phase_outputs`` are reserved
    keys of that convention and never business field names.
    """
    if isinstance(value, BusinessData):
        return value
    if value is None:
        return BusinessData()
    if "inputs" in value or "phase_outputs" in value:
        flat_data: dict[str, Any] = {}
        inputs = value.get("inputs")
        if isinstance(inputs, dict):
            flat_data.update(inputs)
        phase_outputs = value.get("phase_outputs")
        if isinstance(phase_outputs, dict):
            for phase_payload in phase_outputs.values():
                if isinstance(phase_payload, dict):
                    flat_data.update(phase_payload)
        return BusinessData.model_validate(flat_data)
    return BusinessData.model_validate(value)


def merge_business_channel(
    current: BusinessData, update: BusinessData | dict[str, Any]
) -> BusinessData:
    """Reducer for the `data` channel.

    Phase nodes write field deltas (dicts holding only their declared outputs
    plus their `phase_outputs` entry), so parallel branches with disjoint
    fields fold without conflict — the reason this channel stopped being a
    LastValue channel. A full `BusinessData` (the graph input, or an iterate
    wrapper's rebuilt state) replaces the channel value wholesale, as does a
    dict in the invoke-input wrapper shape (its `inputs` key marks it — phase
    deltas never carry one, their `phase_outputs` entry keeps the map form).
    """
    if isinstance(update, BusinessData):
        return update
    if "inputs" in update:
        return coerce_business_data(update)
    delta = dict(update)
    phase_outputs_delta = delta.pop("phase_outputs", None)
    merged = current.model_copy(update=delta) if delta else current
    if isinstance(phase_outputs_delta, dict):
        existing = merged.model_dump().get("phase_outputs")
        combined = dict(existing) if isinstance(existing, dict) else {}
        for phase_id, payload in phase_outputs_delta.items():
            combined[phase_id] = payload
        merged = merged.model_copy(update={"phase_outputs": combined})
    return merged


def merge_flow_channel(
    current: FrameworkState, update: FrameworkState | dict[str, Any]
) -> FrameworkState:
    """Reducer for the `flow` channel: full state replaces, dict deltas fold.

    Dict-shaped fields merge per key so parallel phases each keep their own
    counters; everything else is last-writer-wins.
    """
    if isinstance(update, FrameworkState):
        return update
    merged = current.model_dump()
    delta = dict(update)
    for key in _FLOW_DICT_MERGE_FIELDS:
        if (
            key in delta
            and isinstance(delta[key], dict)
            and isinstance(merged.get(key), dict)
        ):
            delta[key] = {**merged[key], **delta[key]}
    merged.update(delta)
    return FrameworkState.model_validate(merged)


class WorkflowState(TypedDict):
    """LangGraph compatible top-level state.

    Three top-level keys:
    - data: BusinessData (user fields, dynamic schema) — reducer channel;
      phase nodes write deltas so parallel fan-out folds instead of colliding
    - flow: FrameworkState (framework metadata, strict) — reducer channel
    - messages: DeltaChannel增量快照通道
    """

    data: Annotated[BusinessData, merge_business_channel]
    flow: Annotated[FrameworkState, merge_flow_channel]
    messages: Annotated[list[AnyMessage], DeltaChannel(_messages_delta_reducer, snapshot_frequency=50)]


class StateManager:
    """State routing helpers + invariant checks.

    Centralizes BusinessData / FrameworkState writes so framework metadata
    cannot leak into the business namespace.
    """

    @staticmethod
    def update_business(state: WorkflowState, **fields: Any) -> WorkflowState:
        for k in fields:
            if k.startswith("_"):
                raise ValueError(
                    f"BusinessData 不允许 _ 前缀字段: '{k}' (框架元字段必须用 update_framework)"
                )
        new_data = state["data"].model_copy(update=fields)
        return WorkflowState(
            data=new_data,
            flow=state["flow"],
            messages=state["messages"],
        )

    @staticmethod
    def update_framework(state: WorkflowState, **fields: Any) -> WorkflowState:
        flow_data = state["flow"].model_dump()
        flow_data.update(fields)
        new_flow = FrameworkState.model_validate(flow_data)
        return WorkflowState(
            data=state["data"],
            flow=new_flow,
            messages=state["messages"],
        )

    @staticmethod
    def route_finish_task(state: WorkflowState, llm_output: dict[str, Any]) -> WorkflowState:
        """Route finish_task output into business data and framework metadata."""
        business_fields = {k: v for k, v in llm_output.items() if not k.startswith("_")}
        framework_meta = {k: v for k, v in llm_output.items() if k.startswith("_")}
        next_state = state
        if business_fields:
            next_state = StateManager.update_business(next_state, **business_fields)
        return StateManager.update_framework(
            next_state,
            finish_task_result={"meta": framework_meta, "raw": llm_output},
        )


def verify_state_invariants(state: WorkflowState) -> None:
    """启动期检查 state 满足契约."""
    bad = [k for k in state["data"].model_dump() if k.startswith("_")]
    if bad:
        raise ValueError(f"BusinessData 含禁止的 _ 前缀字段: {bad}")
    # state["flow"] 在构造时已经被 Pydantic forbid 校验。
