# MVP-1 Design — A1 WorkflowState 业务/框架物理拆分

> 整合 Gemini independent design (job_543e6152ff10) + 主控决策。

## §1 状态模型定义

### §1.1 三层结构（顶层 TypedDict + 内层 Pydantic）

```python
# src/core/graph_agent/core/state.py
from __future__ import annotations
from typing import Annotated, Any, TypedDict
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, ConfigDict, Field


class BusinessData(BaseModel):
    """用户业务数据空间。

    用户 SKILL.md 声明的所有业务字段（schema 解析出来的）住这里。
    extra="allow" 兼容动态 schema; 严禁任何 _ 开头的字段（框架自检 invariant）。
    """
    model_config = ConfigDict(extra="allow", frozen=False)


class FrameworkState(BaseModel):
    """框架控制空间。

    框架元数据 / 内部 hop counter / finish_task 中转 / metrics 等。
    extra="forbid" 严禁业务污染。所有字段必须显式声明。
    """
    model_config = ConfigDict(extra="forbid", frozen=False)

    # finish_task 中转（替代旧 _finish_task_result）
    finish_task_result: dict[str, Any] | None = None
    # md_to_json 内部块追踪 ID（替代旧 _md_id, 现已物理隔离到 ParsedBlock 但 state 层也清理）
    md_id: str | None = None
    # phase 执行计数 / 防环
    hop_count: int = 0
    # 验证警告/错误中转
    validation_warnings: list[str] = Field(default_factory=list)
    # io 错误中转（替代旧 _io_errors）
    io_errors: list[str] = Field(default_factory=list)
    # 启动期固定字段（thread_id / run_id / unattended / persistent_runtime_inputs / persistent_storage_config / sub_run_id 等）
    thread_id: str | None = None
    run_id: str | None = None
    unattended: bool = False
    persistent_runtime_inputs: dict[str, Any] | None = None
    persistent_storage_config: dict[str, Any] | None = None
    sub_run_id: str | None = None
    # 系统指标 + 重试计数 + current phase
    current_phase: str = ""
    retry_counts: dict[str, int] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    # 工作记忆（替代 _working_memory）
    working_memory: dict[str, Any] = Field(default_factory=dict)
    # ambiguity reports / last output / group key 等次要字段（保留为 dict 兼容性）
    ambiguity_reports: list[dict[str, Any]] = Field(default_factory=list)
    last_output: Any = None
    group_key: str | None = None
    # md_schema 系列
    md_schema: dict[str, Any] | None = None
    md_schema_path: str | None = None
    md_type_dict: dict[str, Any] | None = None


class WorkflowState(TypedDict):
    """LangGraph 兼容顶级状态."""
    data: BusinessData
    flow: FrameworkState
    messages: Annotated[list[AnyMessage], add_messages]
```

### §1.2 字段归属判定（严禁混淆）

| 旧字段（context["X"]） | 新归属 | 字段名 |
|---|---|---|
| `_md_id` | `flow.md_id` | str / None |
| `_finish_task_result` | `flow.finish_task_result` | dict / None |
| `_io_errors` | `flow.io_errors` | list[str] |
| `_validation_warnings` | `flow.validation_warnings` | list[str] |
| `_thread_id` | `flow.thread_id` | str |
| `_run_id` | `flow.run_id` | str |
| `_unattended` | `flow.unattended` | bool |
| `_persistent_runtime_inputs` | `flow.persistent_runtime_inputs` | dict |
| `_persistent_storage_config` | `flow.persistent_storage_config` | dict |
| `_sub_run_id` | `flow.sub_run_id` | str |
| `_ambiguity_reports` | `flow.ambiguity_reports` | list |
| `_last_output` | `flow.last_output` | Any |
| `_group_key` | `flow.group_key` | str |
| `_md_schema` / `_md_schema_path` / `_md_type_dict` | `flow.md_schema*` | 同名 |
| `_working_memory` | `flow.working_memory` | dict |
| `_validation_middleware_phase` | `flow.current_phase` (合并) | str |
| `_current_phase` | `flow.current_phase` | str |
| 旧 `current_phase` (state 顶层) | `flow.current_phase` | str |
| 旧 `retry_counts` (state 顶层) | `flow.retry_counts` | dict |
| 旧 `metrics` (state 顶层) | `flow.metrics` | dict |
| 用户业务字段（动态） | `state["data"]` (BusinessData) | 任意 |

注: `phase` / `skill_base_dir` 在 grep 里出现是普通 dict key 不是 state 字段，不在拆分范围。

## §2 Reducer 行为

### §2.1 messages
- LangGraph 标准 `add_messages` reducer (Annotated 标注)。
- 行为: append-only，phase 切换不重置（middleware 决定 reset 边界）。

### §2.2 data (BusinessData)
- **Replace 模式**: 每次 phase 完成后，新的完整 BusinessData 实例覆盖旧的。
- 实施: `data` 字段不加 reducer Annotated，LangGraph 默认 last-write-wins。
- 框架统一 merge: phase_executor 在 finish_task 后用 `state["data"].model_copy(update=new_fields)` 构造新 BusinessData，统一 set。

### §2.3 flow (FrameworkState)
- **字段级更新**: 部分字段累积，部分覆盖。
- 实施: 由于 Pydantic 子结构在 TypedDict 顶层是单一 obj，LangGraph 默认 last-write-wins 也是替换整个 FrameworkState 对象。**因此每次写 flow 必须 model_copy(update={...})** 保持其他字段不变。
- 工具函数: `core/state.py` 提供 `update_flow(state, **fields) -> WorkflowState` helper。

## §3 StateManager 辅助类（finish_task 路由 + 业务/框架隔离 enforcer）

```python
# src/core/graph_agent/core/state_manager.py
from __future__ import annotations
from typing import Any
from .state import BusinessData, FrameworkState, WorkflowState


class StateManager:
    """状态读写路由 + invariant 检查."""

    @staticmethod
    def update_business(state: WorkflowState, **fields: Any) -> WorkflowState:
        """更新业务数据。检查无 _ 前缀字段。"""
        for k in fields:
            if k.startswith("_"):
                raise ValueError(
                    f"BusinessData 字段名不允许以 _ 开头: '{k}' "
                    "(框架元字段必须走 update_framework)"
                )
        new_data = state["data"].model_copy(update=fields)
        return {**state, "data": new_data}

    @staticmethod
    def update_framework(state: WorkflowState, **fields: Any) -> WorkflowState:
        """更新框架元数据。Pydantic 自动 forbid 校验未声明字段。"""
        new_flow = state["flow"].model_copy(update=fields)
        return {**state, "flow": new_flow}

    @staticmethod
    def route_finish_task(state: WorkflowState, llm_output: dict[str, Any]) -> WorkflowState:
        """finish_task 工具调用后, 把 LLM 输出按业务/框架路由。

        - 业务字段（无 _ 前缀） -> data
        - finish_task 元数据本身 -> flow.finish_task_result
        """
        business_fields = {k: v for k, v in llm_output.items() if not k.startswith("_")}
        framework_meta = {k: v for k, v in llm_output.items() if k.startswith("_")}
        s = state
        if business_fields:
            s = StateManager.update_business(s, **business_fields)
        s = StateManager.update_framework(
            s, finish_task_result={"meta": framework_meta, "raw": llm_output}
        )
        return s
```

## §4 finish_task / md_to_json 改造

### §4.1 cognitive/finish.py
**当前**: `ctx["_finish_task_result"] = result` (line 87)
**改后**: 取消直接写 ctx，改返回结构 `{"finish_task_result": result}`，由 phase_executor 路由到 `flow.finish_task_result`。

### §4.2 tools/md_to_json.py
**当前**: 注入 `_md_id` 到 parsed dict（已有 ParsedBlock 隔离，但底层仍混）
**改后**: 不再向 returned dict 注入 `_md_id`；md_id 由 ParsedBlock.meta 持有，由调用方（phase_executor）路由到 `flow.md_id`。

### §4.3 cognitive/middlewares.py
**当前**: `self.ctx["_finish_task_result"] = result` (ValidationMiddleware:438)
**改后**: middleware 接收 state 而非 ctx，调用 `StateManager.route_finish_task` 或 `update_framework`。

## §5 Loader / Manifest 适配

### §5.1 ContextBridge 演化（ T10 已收敛到 Pydantic 版的延续）
- 输入: SKILL.md 的 context 字段定义（list of field specs）
- 输出: BusinessData 的字段 schema（喂给 BusinessData 动态字段定义机制）
- 实施: `core/manifest.py` 现存 ContextBridge 类增加 `to_business_data_schema()` 方法

### §5.2 loader.py 状态初始化
**当前**: `initial_state = {"context": {...}, "messages": [], ...}`
**改后**:
```python
initial_state: WorkflowState = {
    "data": BusinessData(**user_inputs),
    "flow": FrameworkState(thread_id=tid, run_id=rid, ...),
    "messages": [],
}
```

## §6 隐藏耦合排查

### §6.1 `**state` 解包模式
```bash
grep -rn "\*\*state" src/core/graph_agent/ --include="*.py"
```
**预期**: 0-3 处。每处按拆分后 schema 改写或砍掉。

### §6.2 callbacks/* 读 state
- 检查 callbacks 目录里所有读 state 的位置，按新 schema 改写
- 旧路径 `state["context"]["_X"]` → 新路径 `state["flow"].X` 或 `state["data"].X`

## §7 验证 / Baseline diff 标准

| 指标 | Baseline | After | 验证命令 |
|---|---|---|---|
| `state["data"]` 含 `_` 前缀字段数 | 17 | 0 | grep + runtime assert |
| `state["flow"]` 通过 `model_validate(strict=True)` | N/A | pass | pytest |
| dict-mutation `context["_X"] = ...` 站点数 | 26 | ≤ 5 | grep |
| `**state` 解包模式数 | (待 grep) | 0 | grep |
| pytest 全过 (--ignore=tests/graph_agent/core/validators/test_strict_v2.py) | 599 | ≥ 599 | pytest |
| 4 SKILL compile 状态 | WARN-only / 1 PASS | unchanged | scripts/compile_all.py |
| LangGraph checkpointer 序列化 round-trip | N/A | pass | 新单测 |

## §8 不变性 invariants（运行时检查）

framework 启动时（runner.py / harness.py 入口）跑一次 self-test:
```python
def _verify_state_invariants(state: WorkflowState) -> None:
    """启动期检查 state 满足契约."""
    bad = [k for k in state["data"].model_dump().keys() if k.startswith("_")]
    if bad:
        raise StateContractError(
            f"BusinessData 含禁止的 _ 前缀字段: {bad}"
        )
    state["flow"]  # Pydantic forbid 校验自动跑
```

## §9 未来 MVP 影响

### §9.1 MVP-2 SchemaEngine
- BusinessData 的字段 schema 由 SchemaEngine 提供
- ContextBridge 的部分职责移到 SchemaEngine

### §9.2 MVP-4 finish_task 完整重画
- StateManager.route_finish_task 在 MVP-4 重画 finish_task 数据通道时被吸收/替换
- 当前 StateManager 是 MVP-1→MVP-4 间的过渡形态

### §9.3 MVP-5 全库工程门禁
- BusinessData / FrameworkState / StateManager 是新文件，按 MVP-0 工程门禁 strict 起步（mypy strict + ruff strict + 95% coverage 目标）
- ci.yml 把这 3 文件加到 strict scope（跟 exceptions.py / manifest.py / checkpointer.py 同等待遇）
