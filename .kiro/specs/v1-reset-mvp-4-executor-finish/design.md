# MVP-4 Design — A3 Phase Executor 拆解 + A4 finish_task 数据通道重画

> 整合 Gemini independent design (job_82a24b78ac71 Part B-G) + 主控决策 (research.md D1-D6) + MVP-1/2/3 spec 衔接。

## §1 Node 多态接口

### §1.1 文件结构

```
src/core/graph_agent/core/nodes/
├── __init__.py        # 导出 BasePhaseNode + 3 子类
├── base.py            # BasePhaseNode (ABC)
├── llm.py             # LLMPhaseNode (~250 行内, 替代 execute_llm_phase 532 行)
├── logic.py           # LogicPhaseNode (~80 行, 替代 execute_code_only_phase)
└── validation.py      # ValidationPhaseNode (~100 行, 替代 execute_validation_phase)
```

旧 `core/phase_executor.py` 物理删除。

### §1.2 BasePhaseNode 抽象

```python
# src/core/graph_agent/core/nodes/base.py
from __future__ import annotations
from abc import ABC, abstractmethod
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from ..state import WorkflowState
from ..manifest import PhaseDef


class BasePhaseNode(ABC):
    """所有 phase 节点的统一接口。
    
    由 MVP-3 Loader 的 build_graph_nodes 阶段产出, 由 GraphBuilder 直接注入 LangGraph。
    """

    def __init__(self, phase_def: PhaseDef) -> None:
        self._phase = phase_def

    @property
    def name(self) -> str:
        return self._phase.name

    @abstractmethod
    def execute(
        self,
        state: WorkflowState,
        config: RunnableConfig,
    ) -> WorkflowState | Command:
        """执行 phase, 返回新 state 或 LangGraph Command(goto)。"""
        ...

    def _archive_finish_task_result(self, state: WorkflowState) -> WorkflowState:
        """phase 出口公共逻辑: 把 finish_task_result 封存到 history_results。"""
        ...
```

### §1.3 LLMPhaseNode (核心拆分)

```python
# src/core/graph_agent/core/nodes/llm.py
from langgraph.types import Command
from .base import BasePhaseNode
from ..state_reducers import update_business, update_framework
from ..io_manager import IOManager
from ..schema_engine import SchemaEngine


class LLMPhaseNode(BasePhaseNode):
    """LLM-driven phase. 替代 execute_llm_phase 532 行 + 内部 while True。
    
    Nudge / Compaction / 重试 全部通过 LangGraph Command(goto=<node>) 路由,
    不在本类内部 while 循环。
    """

    def __init__(
        self,
        phase_def,
        agent_factory,
        schema_engine: SchemaEngine,
        io_manager: IOManager,
    ) -> None:
        super().__init__(phase_def)
        self._agent_factory = agent_factory  # 创建 LangChain Agent (含 4 middleware)
        self._schema_engine = schema_engine
        self._io_manager = io_manager

    def execute(self, state, config) -> WorkflowState | Command:
        # 1. 清空上轮 finish_task_result (D5 跨 phase 生命周期)
        state = update_framework(state, finish_task_result=None)

        # 2. 创建 agent (含 4 middleware: ProtocolValidation / CognitiveFlow / 
        #    ExecutionControl / Logging — MVP-3 落地)
        # ⚠️ 动态 Tool Schema 绑定: 必须根据 compiled_schema 动态组装 finish_task 的
        #    args_schema, 用 SchemaEngine.get_pydantic_model 生成的强类型类包装 StructuredTool。
        #    例如: finish_tool = StructuredTool.from_function(
        #              func=finish_task,
        #              args_schema=self._schema_engine.get_pydantic_model(self._phase.compiled_schema)
        #          )
        agent = self._agent_factory(
            phase=self._phase,
            schema_engine=self._schema_engine,
            io_manager=self._io_manager,
        )

        # 3. invoke agent (LangGraph 内部处理 Nudge / interrupt / Command 路由,
        #    不再 while True; 校验 / Nudge / 防环 全在 middleware 内)
        result = agent.invoke({"messages": state["messages"]}, config=config)

        # 4. 检查 finish_task_result 是否被 CognitiveFlowMiddleware 写入
        finish_result = state["flow"].finish_task_result
        if finish_result is None:
            # 没拿到 finish_task → 走 retry / nudge 路径 (由 ExecutionControlMiddleware 决定)
            # middleware 通过 Command(goto="self") 触发重入, 不在这里判断
            return state

        # 5. (MVP-3 cognitive_flow.py 已实施 IO Hoist 拦截，MVP-4 不需要在此重新实施)
        # LLMPhaseNode 出口只需确认 finish_task_result 存在即可，不必调 resolve_hoist。

        # 6. 归档 finish_task_result 到 history_results, 清空当前态
        state = self._archive_finish_task_result(state)
        return state
```

### §1.4 LogicPhaseNode

```python
# src/core/graph_agent/core/nodes/logic.py
class LogicPhaseNode(BasePhaseNode):
    """Code-only phase. 替代 execute_code_only_phase。"""

    def execute(self, state, config) -> WorkflowState:
        # 顺序调 phase.tools (纯 Python 函数), 把返回值写入 BusinessData
        for tool_fn in self._phase.tools:
            result = tool_fn(state)  # MVP-1 设计: tool 接收 state 不接收 ctx dict
            if isinstance(result, dict):
                state = update_business(state, **result)
        return state
```

### §1.5 ValidationPhaseNode

```python
# src/core/graph_agent/core/nodes/validation.py
class ValidationPhaseNode(BasePhaseNode):
    """跨 phase 业务级 validator。区别于 LLM phase 内部的 ProtocolValidationMiddleware。
    
    - ProtocolValidationMiddleware (LLM 内): 拦截 finish_task tool call 校验 schema
    - ValidationPhaseNode (workflow 维度): 跑 phase.validator(business_data) 业务校验
    """

    def execute(self, state, config) -> WorkflowState | Command:
        if self._phase.validator is None:
            return state
        passed, errors = self._phase.validator(state["data"])
        if passed:
            return state
        # 校验失败 → 路由到 retry_target
        if state["flow"].retry_counts.get(self._phase.name, 0) >= self._phase.max_retries:
            return update_framework(
                state, validation_warnings=list(state["flow"].validation_warnings) + errors
            )
        return Command(
            goto=self._phase.retry_target or self._phase.name,
            update={"flow": ...},
        )
```

## §2 finish_task 数据通道重画

### §2.1 工具签名 (强类型)

```python
# src/core/graph_agent/cognitive/finish.py (改造后)
from .schema_engine import SchemaObject  # MVP-2 抽象


def finish_task(
    reasoning: str,
    diagnostics_md: str,
    business_data: BaseModel,  # 实际类型由 LangChain 工具注册时绑定 (build_business_data_for_skill 子类)
) -> str:
    """语义终点工具。
    
    工具实现仅返回完成标志, 不做任何数据路由。
    校验与搬运已由 CognitiveFlowMiddleware (MVP-3 落地) 拦截时一次性完成。
    MVP-4 不需要在此处或 PhaseNode 出口重新实施。
    """
    return "task completed"
```

### §2.2 通道 (单线路径)

```
LLM 生成 finish_task tool call
    ↓
CognitiveFlowMiddleware 拦截 (intercept_tool_call)  # MVP-3 已落地
    ↓
SchemaEngine.validate(business_data, phase.compiled_schema)
    ↓ (失败)                   ↓ (通过)
Command(goto="model")           写 state["flow"].finish_task_result = business_data
返回 LLM 重生成                  并在 Middleware 内即刻执行 IOManager.resolve_hoist
                                ↓
                       放行 tool call (返回 "task completed")
                                ↓
                       LLMPhaseNode.execute 出口 (仅验证存在性)
                                ↓
                       _archive_finish_task_result (封存到 flow.history_results[phase_name])
                                ↓
                       清空 flow.finish_task_result
```

### §2.3 跨 Phase 生命周期 (research D5)

| 阶段 | 谁负责 | 动作 |
|---|---|---|
| 创建 | CognitiveFlowMiddleware | 校验通过后写 `flow.finish_task_result` 并执行 Hoist |
| 归档 | PhaseNode._archive_finish_task_result | 封存到 `flow.history_results[phase_name]` |
| 清空 | LLMPhaseNode.execute 入口 | 进入下一 phase 前 `update_framework(state, finish_task_result=None)` |

## §3 StateManager 演化为 state_reducers.py

### §3.1 文件结构变化

```
src/core/graph_agent/core/
├── state.py             # BusinessData / FrameworkState / WorkflowState (MVP-1)
├── state_reducers.py    # NEW: update_business / update_framework 纯函数
└── state_manager.py     # DELETE (StateManager 类废弃)
```

### §3.2 state_reducers.py 接口

```python
# src/core/graph_agent/core/state_reducers.py
from __future__ import annotations
from typing import Any
from .state import BusinessData, FrameworkState, WorkflowState


def update_business(state: WorkflowState, **fields: Any) -> WorkflowState:
    """生成新 BusinessData 实例后写回 state。Immutable 更新。"""
    for k in fields:
        if k.startswith("_"):
            raise ValueError(
                f"BusinessData 字段名不允许以 _ 开头: '{k}' "
                "(框架元字段必须走 update_framework)"
            )
    new_data = state["data"].model_copy(update=fields)
    return {**state, "data": new_data}


def update_framework(state: WorkflowState, **fields: Any) -> WorkflowState:
    """生成新 FrameworkState 实例后写回 state。Pydantic 自动 forbid 校验。"""
    new_flow = state["flow"].model_copy(update=fields)
    return {**state, "flow": new_flow}
```

### §3.3 废弃路径

- `StateManager` 类 → 删除 (`state_manager.py` 文件物理删除)
- `StateManager.route_finish_task` → 删除 (强类型签名后不再需要)
- `StateManager.update_business / update_framework` → 演化为 state_reducers.py 同名纯函数 (签名不变)

调用方迁移:
```python
# 旧 (MVP-1)
from .state_manager import StateManager
state = StateManager.update_business(state, foo=bar)

# 新 (MVP-4)
from .state_reducers import update_business
state = update_business(state, foo=bar)
```

## §4 FrameworkState 新增字段

```python
# core/state.py 扩展 (基于 MVP-1 design.md §1.1)
class FrameworkState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=False)

    # MVP-1 已声明字段 (省略)
    # ...

    # MVP-4 新增 (research D5):
    nudge_counts: dict[str, int] = Field(default_factory=dict)
    """每 phase 累计 nudge 次数, 跨 LangGraph 节点重入持久存活, 防止死循环。"""

    history_results: dict[str, dict[str, Any]] = Field(default_factory=dict)
    """已完成 phase 的 finish_task_result 归档, key=phase_name。供下游 phase 引用历史输出。"""
```

## §5 LangGraph interrupt + Checkpoint 不兼容声明

### §5.1 interrupt 触发

```python
# src/core/graph_agent/middleware/cognitive_flow.py (MVP-3 落地, MVP-4 扩展)
from langgraph.types import interrupt

class CognitiveFlowMiddleware(AgentMiddleware):
    def intercept_tool_call(self, tool_name, args, state):
        if tool_name == "finish_task":
            # 调 SchemaEngine.validate (MVP-3 已落地)
            ...
        elif tool_name == "ask_clarification":
            if self._unattended:
                return self._auto_resolve_clarification(args)
            # attended mode → 触发 LangGraph 原生 interrupt
            user_response = interrupt({"question": args["question"]})
            return ("human_response", user_response)
        return None
```

### §5.2 恢复时不重复触发校验 (已废弃)

`interrupt()` 挂起的 tool 由 LangGraph 原生在 resume 时直接返回人类输入给 LLM, 不会重新跑 `finish_task` 拦截, 因此本节无 anti-double-check 设计。

### §5.3 旧 Checkpoint 强制清空声明 (无 backward-compat)

Checkpoint **不向后兼容**。MVP-4 改变图节点拓扑 (删 `phase_executor` 内联 while + 拆出 `LLMPhaseNode`/`LogicPhaseNode`/`ValidationPhaseNode`), LangGraph Checkpoint 强绑定 Node 名 + 执行步数。旧 Checkpoint 在新图必硬 crash。

**Migration 指南**: 测试 / 启动脚本必须先清除本地持久化 checkpoint state (例: SQLite 文件) 再跑, 否则会因拓扑破裂出现报错和假阴性。(注: 此内容也应在 RELEASE_NOTES 的 Known Limitations 段落做相应声明)。

## §6 NudgeInjector 重画为 LangGraph 路由

### §6.1 当前 (MVP-3 后) 仍然是 while 内联

`execute_llm_phase` 现有 NudgeInjector (line 522) 在 while 循环内手动调 try_planning / try_selfcheck / try_standard 决定下一轮 messages。

### §6.2 改造后

把 NudgeInjector 内的 3 个分支 (planning / selfcheck / standard) 拆为独立 LangGraph 节点:

```
LLMPhaseNode (主) ──invoke agent──→ Agent finishes
                                       ↓
                     Check: finish_task_result?
                          ↓ no                    ↓ yes
            Check: working_memory updated?    LLMPhaseNode 出口 (hoist)
                ↓ yes              ↓ no
        nudge_planning        Check: latest content empty?
                                  ↓ no              ↓ yes
                          nudge_standard      nudge_emergency
                                  ↓
                          Command(goto="LLMPhaseNode")  # 重入
```

每个 nudge_* 节点是 LangGraph 子节点, 通过 Command(goto) 路由到 LLMPhaseNode 重新 invoke agent (带新 messages)。Nudge 计数累积在 `flow.nudge_counts`, ExecutionControlMiddleware 判定 max_nudges 超阈值时 Command(goto="phase_end") 强制退出。

## §7 Checkpoint Compaction 脱离 while 循环

当前 (MVP-3 后) compaction 在 while 循环内: working_memory 更新触发 → save_compaction_sidecar → _compact_messages → continue。

改造后:
- 由 ExecutionControlMiddleware 监控 messages 累积长度 + working_memory 变化
- 触发条件满足时由 ExecutionControlMiddleware 直接调 `_compact_messages` + `save_compaction_sidecar` (作为 middleware 副作用, 不需要单独 LangGraph 节点)
- LLMPhaseNode 不感知 compaction (透明)

## §8 验收 baseline diff 标准

| 指标 | Baseline (T0-prep) | After MVP-4 | 验证命令 |
|---|---|---|---|
| `phase_executor.py` 文件存在 | yes | no | `ls src/core/graph_agent/core/phase_executor.py` (应 ENOENT) |
| `nodes/*.py` 总 SLOC | 0 | ≤ 600 (单文件 ≤ 250) | cloc |
| `state_manager.py` 文件存在 | yes | no | ls (应 ENOENT) |
| `state_reducers.py` 文件存在 | no | yes | ls |
| `state["data"][.] = ...` 在 finish.py / nodes / middleware 之外的赋值 | T0-prep 测 | 0 | grep |
| `while True:` 在 nodes/*.py 内 | N/A | 0 | grep |
| pytest 全过 (--ignore=tests/graph_agent/core/validators/test_strict_v2.py) | MVP-3 baseline | ≥ MVP-3 baseline | pytest |
| 4 SKILL compile 状态 | WARN-only / 1 PASS | unchanged | scripts/compile_all.py |
| 4 SKILL e2e smoke (1 chapter) | pass | pass | smoke 脚本 |
| 4 SKILL persona 渲染 byte-equal | T0-prep 存 | byte-equal | snapshot 比对 |
| LoopDetection / Nudge 边界测试 | MVP-3 baseline | 通过新 Command 路由还原 | pytest |
| nodes/*.py + middleware/*.py 单测覆盖率 | N/A | ≥ 95% | coverage |

## §9 Invariants (运行时检查)

```python
def _verify_mvp4_invariants(state: WorkflowState) -> None:
    """MVP-4 启动期 + phase 收尾期不变量。"""
    # 1. flow.finish_task_result 在 phase 入口为 None (清空)
    # 2. flow.nudge_counts dict 跨 phase 重入仍累积 (不清零)
    # 3. flow.history_results[phase_name] 含已完成 phase 的封存数据
    # 4. state["data"] 不被 finish.py / middleware / nodes 之外的代码赋值
    # 5. PhaseNode.execute 返回值是 WorkflowState 或 LangGraph Command
    # 6. while True 在 src/core/graph_agent/core/nodes/ 0 hits
```

## §10 风险点 + 回滚路径

### §10.1 风险

- **R1: LangGraph interrupt + Checkpoint 阻抗 (Gemini Risk 1)**
  - 缓解: research D5 给的双管齐下 (finish_task_result checkpoint + 恢复时跳过校验)
  - 触发: 恢复跑 4 SKILL e2e 时校验重复触发 = 回滚 ProtocolValidationMiddleware 的 checkpoint 跳过逻辑, 改为单独 resume 标记
- **R2: Nudge 计数清零导致死循环 (Gemini Risk 2)**
  - 缓解: research D5 把 nudge_counts 下沉到 FrameworkState
  - 触发: 4 SKILL smoke 跑出无限 nudge = 检查 ExecutionControlMiddleware 的 max_nudges 判定逻辑, 必要时回滚 T8 (NudgeInjector 重画)
- **R3: Persona 渲染细微变化 (跟 MVP-3 R1 同源)**
  - 缓解: T0-prep 存 4 SKILL persona snapshot, 验收 byte-equal
  - 触发: snapshot 不一致 = 回滚 LLMPhaseNode 的 prompt 拼装顺序改动
- **R4: finish_task 强类型工具签名跟 LangChain 工具机制不兼容**
  - 缓解: T2 实施时先用 1 SKILL 跑通强类型 + LangChain 自动校验, 再扩到 4 SKILL
  - 触发: LangChain 报 `business_data` 参数无法注入 = 回退到 MD-string 签名 + 内部 md_to_json 解析 (MVP-3 路径)
- **R5: ValidationPhaseNode 跟 ProtocolValidationMiddleware 职责重叠**
  - 缓解: research D2 已区分 (workflow 维度 vs LLM 内维度)
  - 触发: 测试发现两者校验同一字段两次 = 在 ValidationPhaseNode 加 "skip if already validated" 标记

### §10.2 回滚

MVP-4 拆 ~6 commit (按子任务粒度):
1. T1 (BasePhaseNode + 子类骨架)
2. T2+T7 (finish_task 工具签名 + ProtocolValidationMiddleware 拦截 + 废弃 route_finish_task)
3. T3+T8 (LLMPhaseNode + NudgeInjector 重画)
4. T4+T5 (LogicPhaseNode + ValidationPhaseNode + interrupt 集成)
5. T6+T9 (Hoist 推到 Node 出口 + Compaction 脱 while)
6. T10+T11+T12 (GraphBuilder 对接 + 测试更新 + e2e smoke)

任一 commit 后 4 SKILL e2e + pytest 退步, 回滚该 commit, 不影响前序。
