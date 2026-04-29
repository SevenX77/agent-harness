# MVP-4 Requirements — A3 Phase Executor 拆解 + A4 finish_task 数据通道重画

## 背景

graph_agent v1-reset 序列 MVP-4。MVP-1 (state 拆) + MVP-2 (SchemaEngine + IOManager) + MVP-3 (Loader 三阶段 + 4 核心 middleware + Bootstrap) 已铺好类型安全底座 + 编译期 + 拦截期管线。MVP-4 进入"执行核心拆分":

- **A3**: 把 `phase_executor.py` (~532 行上帝类, 含 `execute_code_only_phase` / `execute_validation_phase` / `execute_llm_phase` 三大方法 + 硬编码 while 循环 + Nudge 逻辑 + Checkpoint compaction) 拆为基于 LangGraph 节点多态的 `nodes/*.py`
- **A4**: 把 `finish_task` 数据通道 (LLM 输出 MD → ValidationMiddleware 截获 → md_to_json 解析 → 业务 validator → ctx["_finish_task_result"]) 重画为单线路径 (Middleware Validate → Model 返回 → Node 出口 Hoist)

## 业务目标

废弃 `phase_executor.py` 整个文件, 替换为 `nodes/{base,llm,logic,validation}.py` 多态设计, 每个 Node 职责单一; 废弃 MVP-1 临时引入的 `StateManager.route_finish_task` 补丁 (它靠 `_` 前缀猜字段, MVP-2 SchemaEngine 就绪后已无必要); 让 `finish_task` 工具签名直接对接强类型 BusinessData; 保证从 `finish_task` 调用到 BusinessData 更新只有一条直线路径, 杜绝隐式 ctx 字典操作。为 MVP-5 全库工程门禁 (mypy strict / coverage 95%) 提供强类型边界。

## EARS 需求

### Req 1 — Node 多态接口

**WHEN** framework 编译 SkillManifest，**THE SYSTEM SHALL** 通过 `core/nodes/base.py:BasePhaseNode` ABC 暴露统一接口:
```python
class BasePhaseNode(ABC):
    @abstractmethod
    def execute(self, state: WorkflowState, config: RunnableConfig) -> WorkflowState | Command:
        ...
```
并提供 3 个具体子类: `LLMPhaseNode` / `LogicPhaseNode` / `ValidationPhaseNode`。

### Req 2 — phase_executor.py 物理删除

**WHEN** MVP-4 收尾，**THE SYSTEM SHALL** 满足:
- `src/core/graph_agent/core/phase_executor.py` 物理删除 (不保留, 不 deprecate)
- `class PhaseExecutor` 名字不再出现在 src/ 任何位置
- 所有 phase 执行通过 `BasePhaseNode.execute` 入口调度, GraphBuilder 把 PhaseNode 实例直接作为 LangGraph node 注入

### Req 3 — LLMPhaseNode 去 while 循环, 用 LangGraph Command

**WHEN** LLMPhaseNode.execute 处理 LLM phase，**THE SYSTEM SHALL**:
- **不**使用任何 `while True` 硬循环 (区别于旧 execute_llm_phase line 531-688)
- 用 LangGraph `Command(goto=<node_name>)` 实现 Nudge / 重试路由
- 通过 4 核心 middleware (MVP-3 已落地的 ProtocolValidation / CognitiveFlow / ExecutionControl / Logging) 处理拦截 + Nudge + 防环 + 日志
- LangChain Agent 创建时直接注入这 4 middleware, 不再手动拼装

### Req 4 — finish_task 工具签名强类型化

**WHEN** SKILL 作者声明 finish_task 工具，**THE SYSTEM SHALL** 用强类型签名:
```python
def finish_task(
    reasoning: str,
    diagnostics_md: str,
    business_data: BusinessData,  # 由 SchemaEngine 动态生成的 BusinessData 子类
) -> str:
    """语义终点。工具本身不做数据路由。"""
```
工具实现仅返回完成标志, **不**写 ctx, **不**做校验, **不**做 hoist。

### Req 5 — finish_task 校验提前到 ProtocolValidationMiddleware

**WHEN** LLM 调用 finish_task，**THE SYSTEM SHALL** 在 ProtocolValidationMiddleware (MVP-3 落地) 内拦截 payload, 调 `SchemaEngine.validate(business_data, schema)`:
- 校验失败: 返回 `Command(goto="model")` 把错信息塞回 LLM context, 触发 LLM 重新生成
- 校验通过: 把 business_data 写到 `state["flow"].finish_task_result` 后放行

ValidationMiddleware (旧名) 被 MVP-3 整合到 ProtocolValidationMiddleware, 此处只是校验时机的细化。

### Req 6 — IOManager Hoist 推到 Node 出口

**WHEN** PhaseNode.execute 即将返回 (即当前 Phase 确认结束)，**THE SYSTEM SHALL** 在最后一步调用 IOManager.resolve_hoist (MVP-2 落地):
- source_data = `state["flow"].finish_task_result`
- target_data = `state["data"]` (BusinessData)
- 输出 (新 BusinessData, io_errors) 通过 state_reducers.update_business / update_framework 写回 state

Phase 结束前, **不**有任何其他模块写 `state["data"]` (单线路径)。

### Req 7 — finish_task_result 跨 Phase 生命周期

**WHEN** Phase 切换，**THE SYSTEM SHALL** 让 `flow.finish_task_result` 满足生命周期:
- **创建**: 由 ProtocolValidationMiddleware 在 LLM 调 finish_task 校验通过后写入
- **归档**: Phase 结束时, PhaseNode 把 `flow.finish_task_result` 封存到 `flow.history_results[phase_name]` 字典 (新增字段)
- **清空**: 下一个 Phase 开始 (on_phase_start 回调前) 强制清空 `flow.finish_task_result`, 确保不污染新 phase

### Req 8 — StateManager 演化为 state_reducers 纯函数

**WHEN** Node / Middleware 需要更新 state，**THE SYSTEM SHALL**:
- **废弃**: `StateManager.route_finish_task` 物理删除 (不再需要靠 `_` 前缀猜字段)
- **保留**: `StateManager.update_business` / `update_framework` 演化为 `core/state_reducers.py` 模块级纯函数 (不再是类方法), 接口签名不变
- 所有 Node / Middleware 通过这两个纯函数生成新 state (Immutable 更新)

### Req 9 — Nudge 计数器持久化

**WHEN** Nudge 触发，**THE SYSTEM SHALL** 把 nudge 计数器写入 `state["flow"].nudge_counts: dict[str, int]` (新增 FrameworkState 字段), 防止 LangGraph 路由重入时计数清零陷入死循环。

### Req 10 — Checkpoint Compaction 脱离 while 循环

**WHEN** LLM phase 内累积消息超阈值，**THE SYSTEM SHALL** 通过 LangGraph 节点 + Command(goto) 路由触发 Checkpoint compaction, 不再依赖原 `execute_llm_phase` 的 while 循环内联触发。compaction 触发条件移到 ExecutionControlMiddleware 或独立 CompactionNode (T9 实施时定)。

### Req 11 — LangGraph interrupt 集成 Clarification

**WHEN** SKILL 触发澄清请求 (attended mode)，**THE SYSTEM SHALL**:
- 用 LangGraph 原生 `interrupt()` API (而非自定义 ClarificationException)
- 由 CognitiveFlowMiddleware (MVP-3 落地, 已合并 Clarification 逻辑) 拦截 ask_clarification tool call 后调 interrupt()
- 上层 harness 收到 interrupt 后路由到人机交互
- 恢复时 LangGraph 状态重演不重复触发同一校验流程

### Req 12 — 异常体系 (跟 MVP-5 接口契约)

**WHEN** Node / Middleware 遇到不可恢复错误，**THE SYSTEM SHALL** 抛出统一异常:
- `PhaseExecutionError` (Node 内部错误, 含 phase_name / 上下文)
- `ValidationInterrupt` (LangGraph interrupt 触发后的统一封装)

供 MVP-5 在 Runner 层 try/catch 聚合, 终端用户看不到 Stacktrace。

### Req 13 — Baseline diff 验证

**WHEN** MVP-4 收尾，**THE SYSTEM SHALL** 满足下列指标:
- `phase_executor.py` 物理删除 (file 不存在)
- `nodes/*.py` 总 SLOC ≤ 600 (vs 原 phase_executor 532 行 + 散落的 NudgeInjector / Compaction 等), 但每个 nodes/*.py 单文件 ≤ 250 行
- `state["data"]` 在 finish.py / nodes / middleware 之外被赋值的位置 = 0 (single-write 路径)
- pytest 全过 (--ignore test_strict_v2)
- 4 SKILL compile 状态不变, e2e smoke 跑 1 chapter 不破裂
- 4 SKILL persona 渲染 byte-equal (跟 MVP-3 baseline 比)
- LoopDetection / Nudge 边界测试通过新 Command 路由还原 (Gemini Part G 验收 #3)

## Out of scope（MVP-4 不做）

- A10 harness.run 拆解 (.compile / .prepare_state / .invoke_graph / .persist_outputs) → MVP-5
- 全库 mypy strict / ruff strict / coverage ≥ 85% 整体收紧 → MVP-5
- 4 SKILL e2e 全部断言 → MVP-5
- 第三方 PhaseNode 注册插件协议 → V2 / MVP-6+
- LangGraph Send API 跨 SKILL 委派 (MVP-0 砍掉的 parallel_delegate / subgraph 复活) → V2
- 统一异常 (PhaseExecutionError / ValidationInterrupt) 在所有调用点全部应用 → MVP-5 收尾
