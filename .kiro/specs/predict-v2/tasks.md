# Predict V2 - 高保真业务流推演沙盒任务拆分

> Scope: 只覆盖 Predict V2 实施，包含 Predictor Service、LLM 拦截层、Mock Strategy Factory、Path Diff、Hash Engine、Trace Exporter 与 Diagnostic Export API。不覆盖 Copilot 自身实现、多进程并发预测(V3+)和副作用沙盒化；Req 1.4 明确 Predict 模式不拦截 LogicPhase 副作用，由 PM 自己暴露并修复业务代码。

## 参考输入

- `.kiro/specs/predict-v2/requirements.md` Req 1.1-6.2
- `.kiro/specs/predict-v2/research.md` 7 个研究主题、关键 Trade-off、Outline 修订建议
- `.kiro/specs/predict-v2/design.md` §1-8 架构、组件、模型、API、拦截填充、回测、可观测、风险
- `.kiro/specs/tauri-t2/tasks.md` 任务拆分模板格式
- `docs/architecture/POST_PLAN_C_FINAL_DECISIONS.md` §1 SDK 13-export ABI 锁定、§3.2 Predict 与 ABI 关系
- `docs/architecture/TASK3_SDK_API_CONTRACT_SPEC.md` 当前 SDK public/internal API 契约背景
- `packages/graph-agent/src/graph_agent/core/manifest.py:260-272` LogicPhase pure function 语义依据
- `packages/graph-agent/src/graph_agent/core/runner.py`
- `packages/graph-agent/src/graph_agent/models/gateway_chat_model.py`
- `packages/graph-agent/src/graph_agent/models/resolver.py`
- `packages/graph-agent/src/graph_agent/callbacks/tracing.py`
- `packages/graph-agent/src/graph_agent/callbacks/events.py`
- `packages/graph-agent/src/graph_agent/core/phase_nodes/llm_phase_node.py`
- `apps/studio/backend/app/routers/runs.py`
- `apps/studio/backend/app/models/runs.py`
- `apps/studio/frontend/src/components/trace/VirtualTraceList.tsx`
- `apps/studio/frontend/src/utils/trace.ts`

## 全局决策约束

- Q2 采用 design.md §8 拍板的方案 C：SDK 内部封装，Predict 私有实现落在 `graph_agent.core._predict_internal`，不新增顶层 API。
- 严格锁定 13-export ABI：不得从 `graph_agent/__init__.py` 暴露 Predictor、MockStrategy、Gateway subclass 或 Diagnostic API。
- LLM 拦截采用动态 Subclass `PredictGatewayChatModel(GatewayChatModel)`，仅当前 Predict Graph 实例生效，不做全局 Monkey-patch。
- 拦截点固定为 `GatewayChatModel._generate` / `_agenerate` / `_astream`，直接构造 LangChain `ChatResult` 或 fake streaming chunk，不能调用真实 provider。
- `mock_llm` 多态分发固定为 `None -> P2 Heuristic Stub`、`dict -> P1 临时覆盖/手动注入/Copilot 桥接`、`Path | List[GoldenCase] -> P0 Backtest`。
- Predict 不调任何 LLM：P1 高质量预测只由 Studio Backend 在 Predict Job 组装前调用 Copilot，再通过 `dict` 注入。
- P0 Golden Case 只锚定 LLM Phase 的 prompt + io.outputs schema hash，不绑定整个 Graph 拓扑；非 LLM 节点增删不直接让用例失效。
- P2 模式启用专用 `MAX_PHASE_REVISITS = 10` 死锁防护；P0 Backtest 不启用该上限。
- Predict 模式不重复 `compile_skill` 静态 lint，也不吞掉 LogicPhase 网络/文件/数据库等副作用。

## Sub-tasks

- [ ] P-T1 Internal Predictor 子模块骨架
  - 目标：创建 SDK 私有 `_predict_internal` package，建立 bind API、拦截类、策略抽象和启发式存根入口的最小骨架。
  - 估时：8h
  - 涉及文件：
    - `packages/graph-agent/src/graph_agent/core/_predict_internal/__init__.py`
    - `packages/graph-agent/src/graph_agent/core/_predict_internal/interception.py`
    - `packages/graph-agent/src/graph_agent/core/_predict_internal/strategy.py`
    - `packages/graph-agent/src/graph_agent/core/_predict_internal/stub.py`
    - `packages/graph-agent/src/graph_agent/models/resolver.py`
    - `packages/graph-agent/tests/core/test_predict_internal_imports.py`
  - 关键决策点：
    - `__init__.py` 只 export `bind_predictor` 给 SDK/Studio 内部 import；不得修改 `graph_agent/__init__.py`。
    - `PredictGatewayChatModel` 必须继承 `GatewayChatModel`，先保留 `_generate` / `_agenerate` / `_astream` skeleton。
    - `BaseMockStrategy` 先定义 phase-name 查询能力，不在骨架阶段落复杂策略逻辑。
    - `bind_predictor(skill_instance, mock_strategy)` 是 Studio Backend 接入 SDK 内部封装的唯一约定入口。
  - 验收标准：
    - `from graph_agent.core._predict_internal import bind_predictor` 可用。
    - `from graph_agent import ...` 的 13-export 清单无新增符号。
    - 非 Predict 的 `ModelResolver` 和真实 `GatewayChatModel` 路径行为不变。
  - 测试要求：
    - 单元：私有模块 import、动态 subclass 类型关系、顶层 ABI 快照无新增 export。
    - 集成：无需跑完整 graph，仅验证 bind skeleton 不影响普通 run/import。
    - e2e：不负责。
  - 依赖：无。

- [ ] P-T2 Pydantic 数据模型与 mock_llm 参数验证
  - 目标：实施 design.md §3 的全部 Pydantic 模型和 `MockLLMParam` TypeAdapter，为后续策略工厂和 Diagnostic Export 提供稳定 schema。
  - 估时：8h
  - 涉及文件：
    - `packages/graph-agent/src/graph_agent/core/_predict_internal/models.py`
    - `packages/graph-agent/src/graph_agent/core/_predict_internal/strategy.py`
    - `packages/graph-agent/tests/core/test_predict_models.py`
  - 关键决策点：
    - 模型包含 `GoldenCase`、`PhaseRecord`、`PathDiff`、`PredictResult`、`HeuristicStub` type alias。
    - `PhaseRecord.mocked_source` 枚举值固定为 `golden_case` / `copilot` / `heuristic_stub` / `manual` / `None`。
    - `MockLLMParam = TypeAdapter(Union[None, dict, Path, List[GoldenCase]])`，Path JSON 错误后续由工厂包装成用户友好错误。
    - `PredictResult.status` 只允许 `success` / `failed`，Path Diff 触发 failed 不新增第三态。
  - 验收标准：
    - 所有模型可序列化为 JSON，并能被 Studio Backend 直接消费。
    - `None`、`dict`、`Path`、`List[GoldenCase]` 四类输入验证路径清晰。
    - 非法 mocked_source、非法 status、缺失 GoldenCase 必填字段均 fail closed。
  - 测试要求：
    - 单元：模型 happy/sad path、TypeAdapter 多态解析、JSON round-trip。
    - 集成：无需。
    - e2e：不负责。
  - 依赖：P-T1。

- [ ] P-T3 HeuristicStub 生成器实施
  - 目标：按 `io.outputs` schema 动态生成结构合法且视觉可识别的 P2 启发式存根，保证 Predict 能跨越 LLM 节点继续跑下游 Logic。
  - 估时：8h
  - 涉及文件：
    - `packages/graph-agent/src/graph_agent/core/_predict_internal/stub.py`
    - `packages/graph-agent/tests/core/test_predict_stub.py`
  - 关键决策点：
    - string 生成 `"<mock_{field_name}>"` 或 `"<mock_data>"`，满足 Req 1.3 的 Trace 可识别性。
    - integer/float/bool/list/dict/object/enum 分别映射为 `0`、`0.0`、`True`、`[]`、递归对象、枚举首个值。
    - 支持嵌套 object、array item schema、required/optional 字段；未知类型使用明确 mock 占位而不是抛异常中断 Predict。
    - 生成器只做结构合法，不做语义预测，不调用任何 LLM。
  - 验收标准：
    - 常见 JSON Schema/Pydantic schema 能生成下游可解析 payload。
    - 嵌套字段递归稳定，循环/异常 schema 有保护性降级。
    - 所有字符串 mock 值都能让 PM 在 Trace 中一眼识别为假数据。
  - 测试要求：
    - 单元：string、integer、float、boolean、list、dict/object、enum 六类覆盖。
    - 单元：嵌套 object、array item、缺失 type、异常 schema 降级。
    - e2e：由 P-T10 覆盖。
  - 依赖：P-T2。

- [ ] P-T4 Hash Engine + Path Diff Engine
  - 目标：实现 Golden Case 失效预警所需的 prompt/schema hash，以及 Backtest 路径偏离诊断所需的 LCS Path Diff。
  - 估时：8h
  - 涉及文件：
    - `packages/graph-agent/src/graph_agent/core/_predict_internal/hash.py`
    - `packages/graph-agent/src/graph_agent/core/_predict_internal/path_diff.py`
    - `packages/graph-agent/src/graph_agent/core/_predict_internal/models.py`
    - `packages/graph-agent/tests/core/test_predict_hash.py`
    - `packages/graph-agent/tests/core/test_predict_path_diff.py`
  - 关键决策点：
    - `prompt_hash(text)` 必须先执行空白符 normalization：多空白归一为单空格并 strip，禁止对原始字符串直哈希。
    - `schema_hash(schema)` 必须使用 canonical JSON：`sort_keys=True`、稳定分隔符、可重复 SHA256。
    - `compute_diff(expected_path, actual_path)` 基于 `difflib.SequenceMatcher`，输出 missing、extra、order_mismatch。
    - 合法循环路径必须按列表序列处理，不能用 set diff 丢失顺序和重复访问次数。
  - 验收标准：
    - Prompt 空格/换行轻微变化不改变 hash。
    - Schema key 顺序变化不改变 hash，字段语义变化会改变 hash。
    - Path Diff 能展示缺失节点、额外节点、顺序错位和含循环路径的差异。
  - 测试要求：
    - 单元：prompt normalization edge cases、schema canonicalization edge cases。
    - 单元：LCS 缺失、额外、顺序颠倒、合法循环路径。
    - e2e：由 P-T10 覆盖 Backtest smoke。
  - 依赖：P-T2。

- [ ] P-T5 PredictGatewayChatModel + P0/P1/P2 优先级决策树
  - 目标：在 GatewayChatModel 子类中落地 LLM 调用短路、ChatResult 构造、source 标记和 streaming 适配。
  - 估时：15h
  - 涉及文件：
    - `packages/graph-agent/src/graph_agent/core/_predict_internal/interception.py`
    - `packages/graph-agent/src/graph_agent/core/_predict_internal/strategy.py`
    - `packages/graph-agent/src/graph_agent/core/_predict_internal/stub.py`
    - `packages/graph-agent/src/graph_agent/models/gateway_chat_model.py`
    - `packages/graph-agent/tests/models/test_predict_gateway_chat_model.py`
  - 关键决策点：
    - 决策树顺序固定：P0 Golden Case > P1 manual/copilot dict override > P2 Heuristic Stub。
    - `_generate` 返回标准 `ChatResult`，填充 `mock_id_xxx`、时间戳、source metadata 和 zero usage。
    - `_agenerate` 与 `_astream` 行为等价，streaming 返回 fake `AsyncIterator`，单次 yield 完整 `ChatGenerationChunk` 后结束。
    - 任何 Predict 拦截路径都不得调用真实 provider、fallback resolver 或网络请求。
    - P1 的 `copilot` vs `manual` source 由 dict override metadata 或策略配置决定，不能在拦截层主动找 Copilot。
  - 验收标准：
    - 三种优先级输入均能构造合法 LangChain chat 返回对象。
    - usage 中 input/output tokens 与 total_cost 均为 0。
    - source 标记可被 Trace Exporter 读取。
    - 非 Predict 模型实例不受影响。
  - 测试要求：
    - 单元：P0/P1/P2 决策顺序、ChatResult 元字段、zero usage、source metadata。
    - 单元：async generate 与 streaming fake iterator。
    - 集成：使用测试 phase schema 走一次 LLMPhase 模型调用短路。
  - 依赖：P-T3、P-T4。

- [ ] P-T6 Mock Strategy Factory + bind_predictor 接入
  - 目标：把 `mock_llm` 多态参数解析为具体策略，并通过 `bind_predictor` 注入当前 Predict Graph 的模型构造路径。
  - 估时：10h
  - 涉及文件：
    - `packages/graph-agent/src/graph_agent/core/_predict_internal/strategy.py`
    - `packages/graph-agent/src/graph_agent/core/_predict_internal/__init__.py`
    - `packages/graph-agent/src/graph_agent/models/resolver.py`
    - `packages/graph-agent/src/graph_agent/core/runner.py`
    - `packages/graph-agent/tests/core/test_predict_strategy_factory.py`
    - `packages/graph-agent/tests/models/test_resolver.py`
  - 关键决策点：
    - `MockStrategy.from_param()` 使用 Pydantic TypeAdapter 做第一层验证，再用工厂方法返回 `HeuristicStubStrategy`、`OverrideStrategy`、`GoldenCaseStrategy` 或批量 Backtest 策略。
    - `Path` 输入负责加载 `.golden.json`，损坏 JSON、缺字段、hash metadata 缺失要包装为用户友好错误。
    - `bind_predictor` 只影响当前 skill/harness/model resolver 实例，不能污染进程全局 resolver。
    - `run_skill(mock_llm=...)` 参数扩展必须向后兼容既有调用；默认 None 在 Predict Service 路径触发 P2，普通 Run 语义需由入口模式区分清楚。
  - 验收标准：
    - 四类 mock_llm 输入均映射到正确策略。
    - 同进程内真实 Run 与 Predict Run 可交替执行，互不污染。
    - 顶层 13-export 仍无新增类/函数。
  - 测试要求：
    - 单元：策略工厂类型分发、Path 加载错误包装、dict override source。
    - 集成：resolver 返回 PredictGatewayChatModel 的实例边界，普通 resolver 不变。
    - e2e：由 P-T10 覆盖。
  - 依赖：P-T2、P-T5。

- [ ] P-T7 Predictor Service 主流程
  - 目标：实现 Studio Backend 内部 Predictor Service 编排层，负责 dispatch、策略解析、SDK 绑定运行、Golden Case 校验、Path Diff 和结果汇总。
  - 估时：12h
  - 涉及文件：
    - `apps/studio/backend/app/services/predictor.py`
    - `apps/studio/backend/app/models/runs.py`
    - `apps/studio/backend/app/routers/runs.py`
    - `packages/graph-agent/src/graph_agent/core/_predict_internal/models.py`
    - `packages/graph-agent/src/graph_agent/core/_predict_internal/hash.py`
    - `packages/graph-agent/src/graph_agent/core/_predict_internal/path_diff.py`
    - `apps/studio/backend/tests/test_predictor_service.py`
  - 关键决策点：
    - 核心方法按 design.md §2：`dispatch_predict_job`、`resolve_fill_strategy`、`assemble_trace`。
    - Predictor Service 不直接调用 Copilot；只接收已经由上层注入的 dict 预测结果。
    - Golden Case hash 不匹配只 Warning/UI 标记，不默认 abort，尽量完成本次运行。
    - Path Diff 出现 missing、extra 或 order_mismatch 时，`PredictResult.status` 置为 `failed`。
    - P2 模式监控单 phase revisit，超过 `MAX_PHASE_REVISITS = 10` 抛 `PredictDeadlockError` 并返回当前 actual_path。
  - 验收标准：
    - `mock_llm=None` 可走 P2 生成 PredictResult。
    - `mock_llm=Path` 可加载 Golden Case、输出 hash stale warning、执行 Path Diff。
    - 死锁防护只在 P2 生效，P0 Backtest 不受 `MAX_PHASE_REVISITS` 限制。
    - LogicPhase 异常和副作用错误不被 Predict Service 静默吞掉。
  - 测试要求：
    - 单元：dispatch/resolve/assemble 三方法、hash warning、Path Diff failed、deadlock error。
    - 集成：Backend service 调 SDK 内部 bind 并返回 PredictResult。
    - e2e：由 P-T10 覆盖。
  - 依赖：P-T4、P-T6。

- [ ] P-T8 PredictTracingCallback + Trace Exporter
  - 目标：把 Predict 运行的原始 callback/trace 事件转成高保真业务诊断切片，并强制标记 Predict 模式和 mock 来源。
  - 估时：8h
  - 涉及文件：
    - `packages/graph-agent/src/graph_agent/core/_predict_internal/tracing.py`
    - `packages/graph-agent/src/graph_agent/core/_predict_internal/exporter.py`
    - `packages/graph-agent/src/graph_agent/callbacks/tracing.py`
    - `packages/graph-agent/src/graph_agent/callbacks/events.py`
    - `packages/graph-agent/tests/callbacks/test_predict_tracing.py`
    - `packages/graph-agent/tests/core/test_predict_trace_exporter.py`
  - 关键决策点：
    - `PredictTracingCallback.on_chain_start` 在 root metadata 写入 `is_predict: true`。
    - `on_phase_end` 从拦截层暂存 source 中回填 `mocked_source`，取值覆盖 golden_case/copilot/heuristic_stub/manual。
    - Trace Exporter 的 `assemble_phase_record` 只输出业务字段：phase_name、type、inputs、outputs、mocked_source。
    - Predict 下 usage/token/cost 统一为 0；Trace/metrics 面板不得出现真实计费。
    - 大字段截断作为 exporter 内部能力，保留 `truncated` 标记但不扩大 PredictResult 的核心模型复杂度。
  - 验收标准：
    - Predict trace root 含 `is_predict: true`。
    - 每个被跨越 LLM 节点都有正确 `mocked_source`。
    - LogicPhase 记录无 mocked_source，但 inputs/outputs 保留。
    - 超大 inputs/outputs 不会导致 Diagnostic Export 失控膨胀。
  - 测试要求：
    - 单元：callback root 标记、phase source 回填、zero usage、truncation。
    - 集成：从 raw events assemble 出 `List[PhaseRecord]`。
    - e2e：由 P-T10 覆盖。
  - 依赖：P-T2、P-T5。

- [ ] P-T9 Diagnostic Export API(in-process) 与 Studio 契约
  - 目标：为 Copilot 和前端 trace 视图提供 in-process Diagnostic Export API，不新建 HTTP endpoint，明确 PredictResult 消费契约。
  - 估时：7h
  - 涉及文件：
    - `apps/studio/backend/app/services/predictor.py`
    - `apps/studio/backend/app/services/diagnostic_export.py`
    - `apps/studio/backend/app/models/runs.py`
    - `apps/studio/frontend/src/utils/trace.ts`
    - `apps/studio/frontend/src/components/trace/VirtualTraceList.tsx`
    - `apps/studio/backend/tests/test_diagnostic_export.py`
  - 关键决策点：
    - Diagnostic Export API 采用 Python in-process 函数调用，返回 `PredictResult` 或等价 JSON，不架独立 HTTP endpoint。
    - Copilot 只消费 Predict 输出；Predict 模块不主动 import 或调用 Copilot Service。
    - Backend/Frontend 字段命名沿用 `PhaseRecord`，避免为 UI 单独发明第二套 trace schema。
    - Predict 模式产出的 trace 不能被固定为 Golden Case；Golden Case 源头只能是真实 Run + PM 修正。
  - 验收标准：
    - Backend 能把单次 PredictResult 导出给内部消费者。
    - UI trace 工具能识别 `is_predict` 与 `mocked_source` 字段。
    - 没有新增公开 HTTP 路由或 SDK 顶层 API。
  - 测试要求：
    - 单元：Diagnostic Export 函数输入输出、字段稳定性、禁止 Predict trace 固定为 Golden Case 的 guard。
    - 集成：Backend service 产物被 trace utility 消费的契约测试。
    - e2e：由 P-T10 覆盖。
  - 依赖：P-T7、P-T8。

- [ ] P-T10 Predict V2 e2e + 集成测试收敛
  - 目标：建立 Predict V2 完成标准，覆盖 P2、P1、P0 三模式、死锁防护、Path Diff 失败和真实 Run 共存。
  - 估时：12h
  - 涉及文件：
    - `packages/graph-agent/tests/e2e/test_predict_v2.py`
    - `apps/studio/backend/tests/test_predict_e2e.py`
    - `apps/studio/frontend/src/components/trace/VirtualTraceList.tsx`
    - `.kiro/specs/predict-v2/tasks.md`
  - 关键决策点：
    - P2 smoke：`mock_llm=None` 跑完一个含 LogicPhase + LLMPhase 的 skill graph，返回 `PredictResult.status=success` 与 heuristic_stub source。
    - P1 smoke：`mock_llm=dict` 注入单 phase override，验证 source 为 manual 或 copilot，且 Predict 不调用 Copilot。
    - P0 smoke：`mock_llm=Path` 加载 Golden Case，验证 hash warning、Path Diff、expected_output 注入。
    - 死锁测试必须证明 P2 超过 `MAX_PHASE_REVISITS` 会停止，P0 同样路径不被该上限阻断。
    - 真实 e2e 仍是最终质量红线；Predict e2e 不替代 4 个核心 Skill 的真 LLM e2e。
  - 验收标准：
    - SDK 单元/集成测试覆盖 P-T1 到 P-T8 的核心分支。
    - Backend service e2e 能完成一次 Predict Job 并输出 Diagnostic Export。
    - P0 路径偏离时结果为 failed 且包含可展示 diff。
    - 同进程 Predict Run 后再执行普通 Run，不残留 mock strategy 或 PredictGatewayChatModel。
  - 测试要求：
    - 单元：补齐各模块边界测试。
    - 集成：SDK + Backend Predictor Service 链路。
    - e2e：P2 full graph、P1 dict、P0 Backtest、P2 deadlock、P0 no revisit limit。
  - 依赖：P-T7、P-T8、P-T9。

## 总估时

96h

## Risk / Blocker Flags

- P0：13-export ABI 锁定必须作为 P-T1/P-T6/P-T9 验收项；任何新增顶层 Predictor API 都会违背 POST_PLAN_C 最终决策。
- P0：Predict 严禁调用 LLM；P1 只能通过 Studio Backend 预先拿到 Copilot 输出后走 dict 注入，拦截层和 Predictor Service 都不能主动请求模型。
- P0：P2 启发式存根可能触发路由死循环，`MAX_PHASE_REVISITS=10` 必须只在 P2 生效，P0 Backtest 不限制。
- P1：LangChain `ChatResult` / streaming chunk 元字段兼容风险高，P-T5 需要覆盖 sync、async、stream 三条路径。
- P1：Hash normalization 会忽略部分空白语义变化；按 design.md 先接受该 trade-off，以 stale warning 而非 hard fail 降低误伤。
- P1：Diagnostic Export JSON 可能膨胀，Trace Exporter 需要截断大字段并保留可诊断标记。
- P2：Predict 不沙盒化 LogicPhase 副作用，真实网络/文件/数据库写入会暴露给 PM；这是 Req 1.4 的设计选择，不在本 spec 内补防护。

## 建议执行顺序

先做 P-T1 建立 `_predict_internal` 边界，再做 P-T2/P-T3/P-T4 三个基础模块。P-T5 与 P-T6 收敛 SDK 拦截和策略注入后，P-T7 才接 Studio Backend 主流程。P-T8 可在 P-T5 source metadata 稳定后并行推进。最后用 P-T9 固化 in-process 诊断契约，并由 P-T10 做 P2/P1/P0 全链路收敛。
