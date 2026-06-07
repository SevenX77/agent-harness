"""WorkflowState and split BusinessData / FrameworkState.

T1 of MVP-1 (A1 WorkflowState 拆分): introduce two Pydantic substructures
to physically separate user business fields from framework metadata.

T1 only: model definitions + unit tests. Runtime adoption (runner, harness,
phase_executor, middleware) happens in T2-T6.
"""

from __future__ import annotations

import copy
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
            class PhaseOutputsCompat(dict[str, Any]):
                def __getitem__(self, k: str) -> Any:
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
                    return self[k]
                def __contains__(self, k: object) -> bool:
                    return True
                def items(self) -> Any:
                    return {"main": values}.items()
                def keys(self) -> Any:
                    return {"main": values}.keys()
                def values(self) -> Any:
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
        return self.model_dump().get(key, default)

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
    md_id: str | None = None
    hop_count: int = 0
    validation_warnings: list[str] = Field(default_factory=list)
    io_errors: list[str] = Field(default_factory=list)
    # 启动期固定字段
    thread_id: str | None = None
    run_id: str | None = None
    unattended: bool = False
    persistent_runtime_inputs: dict[str, Any] | None = None
    persistent_storage_config: dict[str, Any] | None = None
    sub_run_id: str | None = None
    # phase + retry + metrics
    current_phase: str = ""
    retry_counts: dict[str, int] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    critic_metrics: dict[str, Any] = Field(default_factory=dict)
    subagent_validation_retries: dict[str, int] = Field(default_factory=dict)
    # retry 跨 phase 通信
    retry_feedback: list[str] | None = None
    # 工作记忆
    working_memory: Any = Field(default_factory=dict)
    # 次要字段
    ambiguity_reports: list[dict[str, Any]] = Field(default_factory=list)
    last_output: Any = None
    group_key: str | None = None
    trace_path: str | None = None
    trace: str | None = None
    subagent_depth: int = 0
    # validation middleware 内部 phase 标记，语义不同于 current_phase
    validation_middleware_phase: str | None = None
    md_schema: dict[str, Any] | None = None
    md_schema_path: str | None = None
    md_type_dict: dict[str, Any] | None = None
    timeout_s: int | None = None


class WorkflowState(TypedDict):
    """LangGraph compatible top-level state.

    Three top-level keys:
    - data: BusinessData (user fields, dynamic schema)
    - flow: FrameworkState (framework metadata, strict)
    - messages: DeltaChannel增量快照通道
    """

    data: BusinessData
    flow: FrameworkState
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


def legacy_context_from_state(state: WorkflowState) -> dict[str, Any]:
    """Return a T2 compatibility context dict for legacy runtime code."""
    ctx = state["data"].model_dump()
    flow = state["flow"]
    _add_not_none_framework_values(ctx, flow)
    _add_non_empty_framework_values(ctx, flow)
    _add_copied_framework_values(ctx, flow)
    ctx["_unattended"] = flow.unattended
    return ctx


def _add_not_none_framework_values(ctx: dict[str, Any], flow: FrameworkState) -> None:
    for ctx_key, value in _not_none_framework_pairs(flow):
        if value is not None:
            ctx[ctx_key] = value


def _not_none_framework_pairs(flow: FrameworkState) -> tuple[tuple[str, Any], ...]:
    return (
        ("_finish_task_result", flow.finish_task_result),
        ("_md_id", flow.md_id),
        ("_thread_id", flow.thread_id),
        ("_run_id", flow.run_id),
        ("_sub_run_id", flow.sub_run_id),
        ("_last_output", flow.last_output),
        ("_group_key", flow.group_key),
        ("_trace_path", flow.trace_path),
        ("_validation_middleware_phase", flow.validation_middleware_phase),
        ("_md_schema_path", flow.md_schema_path),
    )


def _add_non_empty_framework_values(ctx: dict[str, Any], flow: FrameworkState) -> None:
    if flow.io_errors:
        ctx["_io_errors"] = list(flow.io_errors)
    if flow.validation_warnings:
        ctx["_validation_warnings"] = list(flow.validation_warnings)
    if flow.working_memory:
        ctx["_working_memory"] = flow.working_memory
    if flow.ambiguity_reports:
        ctx["_ambiguity_reports"] = list(flow.ambiguity_reports)
    if flow.current_phase:
        ctx["_current_phase"] = flow.current_phase


def _add_copied_framework_values(ctx: dict[str, Any], flow: FrameworkState) -> None:
    if flow.persistent_runtime_inputs is not None:
        ctx["_persistent_runtime_inputs"] = dict(flow.persistent_runtime_inputs)
    if flow.persistent_storage_config is not None:
        ctx["_persistent_storage_config"] = dict(flow.persistent_storage_config)
    if flow.retry_feedback is not None:
        ctx["_retry_feedback"] = list(flow.retry_feedback)
    if flow.md_schema is not None:
        ctx["_md_schema"] = dict(flow.md_schema)
    if flow.md_type_dict is not None:
        ctx["_md_type_dict"] = dict(flow.md_type_dict)


def workflow_state_from_legacy_context(
    state: WorkflowState,
    ctx: dict[str, Any],
    *,
    messages: list[AnyMessage] | None = None,
    current_phase: str | None = None,
    retry_counts: dict[str, int] | None = None,
    metrics: dict[str, Any] | None = None,
) -> WorkflowState:
    """Build new WorkflowState from a T2 compatibility context dict."""
    business_fields = {k: v for k, v in ctx.items() if not k.startswith("_")}
    flow_updates: dict[str, Any] = {
        "finish_task_result": ctx.get("_finish_task_result"),
        "md_id": ctx.get("_md_id"),
        "io_errors": list(ctx.get("_io_errors") or []),
        "validation_warnings": list(ctx.get("_validation_warnings") or []),
        "thread_id": ctx.get("_thread_id"),
        "run_id": ctx.get("_run_id"),
        "unattended": bool(ctx.get("_unattended", state["flow"].unattended)),
        "persistent_runtime_inputs": ctx.get("_persistent_runtime_inputs"),
        "persistent_storage_config": ctx.get("_persistent_storage_config"),
        "sub_run_id": ctx.get("_sub_run_id"),
        "retry_feedback": ctx.get("_retry_feedback"),
        "working_memory": ctx.get("_working_memory") or {},
        "ambiguity_reports": list(ctx.get("_ambiguity_reports") or []),
        "last_output": ctx.get("_last_output"),
        "group_key": ctx.get("_group_key"),
        "trace_path": ctx.get("_trace_path"),
        "validation_middleware_phase": ctx.get("_validation_middleware_phase"),
        "md_schema": ctx.get("_md_schema"),
        "md_schema_path": ctx.get("_md_schema_path"),
        "md_type_dict": ctx.get("_md_type_dict"),
        "current_phase": current_phase
        if current_phase is not None
        else str(ctx.get("_current_phase") or state["flow"].current_phase),
        "retry_counts": retry_counts
        if retry_counts is not None
        else dict(state["flow"].retry_counts),
        "metrics": metrics if metrics is not None else dict(state["flow"].metrics),
    }
    new_flow = FrameworkState.model_validate({**state["flow"].model_dump(), **flow_updates})
    return WorkflowState(
        data=BusinessData.model_validate(business_fields),
        flow=new_flow,
        messages=messages if messages is not None else state["messages"],
    )


def _clone_state(state: WorkflowState) -> WorkflowState:
    """Clone WorkflowState using deepcopy to prevent cross-phase mutation."""
    return copy.deepcopy(state)
