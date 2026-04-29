"""WorkflowState and split BusinessData / FrameworkState.

T1 of MVP-1 (A1 WorkflowState 拆分): introduce two Pydantic substructures
to physically separate user business fields from framework metadata.

T1 only: model definitions + unit tests. Runtime adoption (runner, harness,
phase_executor, middleware) happens in T2-T6.
"""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, ConfigDict, Field


class BusinessData(BaseModel):
    """User business data namespace.

    Stores fields parsed from user SKILL.md schema.
    extra="allow" supports dynamic schema; framework enforces no _ prefix
    via StateManager.update_business (Pydantic 本身不直接拒 _, 由 StateManager 负责).
    """

    model_config = ConfigDict(extra="allow", frozen=False)


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
    # 工作记忆
    working_memory: dict[str, Any] = Field(default_factory=dict)
    # 次要字段
    ambiguity_reports: list[dict[str, Any]] = Field(default_factory=list)
    last_output: Any = None
    group_key: str | None = None
    md_schema: dict[str, Any] | None = None
    md_schema_path: str | None = None
    md_type_dict: dict[str, Any] | None = None


class WorkflowState(TypedDict):
    """LangGraph compatible top-level state.

    Three top-level keys:
    - data: BusinessData (user fields, dynamic schema)
    - flow: FrameworkState (framework metadata, strict)
    - messages: LangGraph standard add_messages reducer
    """

    data: BusinessData
    flow: FrameworkState
    messages: Annotated[list[AnyMessage], add_messages]


class StateManager:
    """State routing helpers + invariant checks.

    T1: skeleton with update_business / update_framework only.
    T4 will fill route_finish_task and other routing logic.
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
