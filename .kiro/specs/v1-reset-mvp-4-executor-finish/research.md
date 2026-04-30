# MVP-4 Research — A3 Phase Executor / A4 finish_task 决策

## 来源资料

- v1-reset direction doc: `docs/superpowers/specs/2026-04-28-v1-reset-direction.md` §4 MVP-4 + §A3 / §A4 + Appendix B
- MVP-1 spec (已 commit): `.kiro/specs/v1-reset-mvp-1-state-split/{requirements,design,tasks}.md` (BusinessData / FrameworkState / StateManager / 临时 route_finish_task)
- MVP-2 spec (待主控审 commit): `.kiro/specs/v1-reset-mvp-2-schema-io/{requirements,design,tasks}.md` (SchemaEngine / IOManager / build_business_data_for_skill / SchemaObject)
- MVP-3 spec (待主控审 commit): `.kiro/specs/v1-reset-mvp-3-loader-startup-middleware/{requirements,design,tasks}.md` (Loader 三阶段 + 4 核心 middleware + ModuleSandbox + PhaseNode)
- Gemini independent design (2026-04-29): job_82a24b78ac71 (整合到本 spec design.md)
- 当前 phase_executor 散布点 (Gemini Part A 现状审计):
  - `src/core/graph_agent/core/phase_executor.py` (~532 行, 含 execute_code_only_phase / execute_validation_phase / execute_llm_phase 三大方法 + while 循环 + NudgeInjector + Compaction sidecar)
  - `src/core/graph_agent/cognitive/finish.py` (finish_task tool, 跟 MVP-2 集成后已部分外置)
  - `src/core/graph_agent/cognitive/middlewares.py` (ValidationMiddleware, MVP-3 已并入 ProtocolValidationMiddleware)

## Baseline 数据 (待 T0-prep 测)

T0-prep 子任务 (派 a3 在派 T1 前跑) 需要测:
- `phase_executor.py` 当前 SLOC + 每方法 SLOC 分布
- `execute_llm_phase` 内 while 循环逻辑提炼 (Nudge / Compaction / 退出条件)
- `NudgeInjector` 当前 API + 调用点
- `_save_compaction_sidecar` 当前签名 + 触发点
- `flow.finish_task_result` 在 MVP-1/2/3 后实际 read/write 站点
- 4 SKILL e2e smoke 当前 baseline (wall-time / token / nudge 触发次数 / compaction 触发次数)
- 4 SKILL persona 渲染 snapshot (跟 MVP-3 baseline 一样 byte-equal 比对)

## 决策记录

### D1 — phase_executor.py 删除 vs 重写

**选项**:
- A. 重写 phase_executor.py 内部方法, 保留 PhaseExecutor 类
- B. **物理删除 phase_executor.py, 替换为 nodes/*.py 多态设计 (Gemini 推荐)**
- C. 保留 phase_executor.py 作为 thin orchestrator, 内部委托给 nodes

**决策: B (物理删除)**

**理由**:
- Gemini Part B 明确"废弃庞大的 PhaseExecutor 类, 转而采用面向对象的节点多态设计"
- direction doc §4 MVP-4 描述"execute_llm_phase 532 行拆为 PromptRenderer / AgentLoopDriver / LifecycleEmitter / StateTransformer", 这些子组件归 LLMPhaseNode 内部, PhaseExecutor 类没有存在意义
- C 把 PhaseExecutor 留为 orchestrator 是补丁思维 — Node 实例本身就能直接作为 LangGraph node 注入 GraphBuilder, 不需要中间层
- A 重写不彻底, 上帝类的"职责膨胀"问题不解决

### D2 — Node 子类设计: 3 类 (LLM / Logic / Validation)

**Gemini Part B**: `LLMPhaseNode / LogicPhaseNode / ValidationPhaseNode`

**主控复核**:
- LLMPhaseNode: 替代 execute_llm_phase, 持有 LangChain Agent + 4 middleware
- LogicPhaseNode: 替代 execute_code_only_phase, 顺序调用 phase.tools (纯 Python 函数)
- ValidationPhaseNode: 替代 execute_validation_phase, 调 phase.validator (业务校验函数)

**潜在冲突**: MVP-3 ProtocolValidationMiddleware 已经在 LLM phase 内部做契约校验 + finish_task 校验。ValidationPhaseNode 还有存在意义吗?

**决策: ValidationPhaseNode 保留, 但职责区分清楚**:
- ProtocolValidationMiddleware (MVP-3): LLM phase **内部**, 在 finish_task tool call 拦截时校验 — 校验失败触发 Command(goto="model") 让 LLM 重生成
- ValidationPhaseNode (MVP-4): 独立 phase 类型 (SKILL.md 中 `mode: validation`), 跑业务 validator 函数, 用于跨 phase 的业务级校验, 校验失败触发 retry_target 路由

**理由**:
- 两者作用不同范围: middleware 在 phase 内部 (LLM 维度), Node 在 phase 之间 (workflow 维度)
- direction doc §4 MVP-4 没显式说删 ValidationPhaseNode, 保留兼容 4 SKILL 现有 validation phase 用法

### D3 — finish_task 接口对接 SchemaEngine + IOManager

**当前 (MVP-1/2/3 后)**: finish_task 工具签名是 `finish_task(reasoning, diagnostics_md, business_data_md: str)` (str MD 文本), 内部调 md_to_json 解析。

**MVP-4 改为**: `finish_task(reasoning, diagnostics_md, business_data: BusinessData)` (强类型), 工具实现仅返回完成标志, **不**写 ctx, **不**做校验, **不**做 hoist。

**职责解耦** (Gemini Part C):
- **SchemaEngine.validate**: 由 ProtocolValidationMiddleware 在 finish_task tool call 拦截时调用 (MVP-3 已落地的 middleware)
- **IOManager.resolve_hoist**: 由 PhaseNode.execute 出口调用 (本 MVP T6 实施)
- **finish_task tool 自身**: 仅返回完成标志, 不做任何状态变更

**理由**:
- 强类型签名让 LangChain 工具调用时 Pydantic 自动校验 business_data 字段 (省去内部 md → dict 解析)
- md_to_json 在 MVP-2 已经用 SchemaEngine.get_pydantic_model 生成强类型类, MVP-4 把这个类直接作为工具参数
- 老的 ctx["_finish_task_result"] 字典 hack 完全消失

### D4 — StateManager 命运: 演化为 state_reducers.py 纯函数

**MVP-1 引入**: StateManager 类含 `route_finish_task` (按 _ 前缀路由) + `update_business` + `update_framework` (Pydantic immutable 更新)

**MVP-4 处理**:
- **废弃**: `StateManager.route_finish_task` 物理删除 (Gemini Part D 明说"坚决废弃") — finish_task 工具签名已分离 reasoning + business_data, 不再需要靠 `_` 前缀猜
- **保留**: `update_business` + `update_framework` 演化为 `core/state_reducers.py` 模块级纯函数 (不再是类方法)
- StateManager 类本身物理删除, 类名不再出现

**理由**:
- route_finish_task 是 MVP-1 时代的过渡补丁 (research D4), MVP-4 应清掉
- update_business / update_framework 是 Pydantic immutable 更新 helper, 非常通用, 用纯函数比类方法更轻
- "类方法 → 模块级函数" 减少 import 噪音, mypy 友好

### D5 — LangGraph interrupt + Checkpoint 兼容性

**Gemini Risk 1**: 原生 interrupt() 在恢复时需要状态重演, 如果在 CognitiveFlowMiddleware 中抛出中断, 需确保恢复时不会重复触发相同的验证流程。

**Gemini Risk 2**: 去除 while True 后, Nudge 计数器必须下沉到 FrameworkState 中持久化, 否则每次 LangGraph 路由重入都会导致计数清零 (陷入无限 Nudge 死循环)。

**决策: 双管齐下**
1. **interrupt + Checkpoint 兼容**: ProtocolValidationMiddleware 校验通过后**立刻**写 `state["flow"].finish_task_result` 到 checkpoint, interrupt 恢复时检测此字段已存在则跳过校验直接走 Hoist 路径
2. **Nudge 计数持久化**: FrameworkState 新增字段 `nudge_counts: dict[str, int] = Field(default_factory=dict)`, 由 ExecutionControlMiddleware 维护 (跨 LangGraph 节点调用持久存活)

**理由**:
- LangGraph 原生 checkpoint 是状态级持久化, 把 nudge 计数 + finish_task_result 都写到 FrameworkState 里就自动获得 checkpoint 存活
- 不引入 LangGraph 之外的 SQLite 等持久化, 简化

### D6 — 跟 MVP-5 接口约定: 异常体系 + 强类型边界

**MVP-5 范围** (direction doc §4): 全库工程门禁 (mypy strict / ruff / coverage ≥ 85%) + 4 SKILL CI 全绿 + harness.run 拆解。

**MVP-4 给 MVP-5 的契约**:
1. **强类型入口/出口**: `harness.run(initial_state: WorkflowState) -> WorkflowState` 内部彻底杜绝 `Any` 类型自由流动 (Gemini Part F)
2. **统一异常**: `PhaseExecutionError` (Node 内部错误) + `ValidationInterrupt` (interrupt 封装), 在 `core/exceptions.py` 已有 base 上扩展。MVP-5 在 Runner 层做 try/catch 聚合
3. **Node 接口稳定**: `BasePhaseNode.execute` 签名 (state, config) → state | Command 是 MVP-4 的契约, MVP-5 不能动
4. **state_reducers 纯函数稳定**: update_business / update_framework 接口稳定, MVP-5 内部 mypy strict 时不需重画

## 不在 MVP-4 处理的相关问题（明确 defer）

- harness.run 拆为 .compile / .prepare_state / .invoke_graph / .persist_outputs → MVP-5
- 全库 mypy strict / ruff / coverage 整体收紧 → MVP-5
- 4 SKILL e2e 全部断言 → MVP-5
- LangGraph Send API 跨 SKILL 委派 → V2
- 第三方 PhaseNode 注册插件协议 → V2
- finish_task 改为 LLM `response_format` (而非 LangChain Tool) 的彻底替代 → V2 (MVP-4 已经把 finish_task 退化为语义终点 tool, 进一步替换不在范围)
