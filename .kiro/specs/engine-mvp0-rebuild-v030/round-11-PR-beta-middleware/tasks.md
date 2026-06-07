---
spec: engine-mvp0-rebuild-v030/round-11-PR-beta-middleware
phase: PR β (Middleware Runtime Refactor)
owner: a1 主笔 tasks.md / a2 audit / a3 PM-proxy audit / 主控复核
工程量: 41h (实施 β1-β7=32.5h + audit/docs/ship buffer β8-β11=8.5h)
依赖: PR γ0 (Contract Patch) 已 ship
后续: γ1 (compile-schema 50h) → γ1.5 (preflight 38h) → γ2 (state-io 40h) → γ3 (cleanup 44h)
---

# PR β: Middleware Runtime Refactor Tasks

## §0 Scope, Reconcile 结论和继承边界

### §0.1 工程判断: responsibility extraction, 不是 full replacement

本 tasks.md 对 `requirements.md §2 R-β-01` 的“替代掉 `graph_assembler.py` 里的旧私有 ReAct loop”作如下工程解释:

**PR β 采用 responsibility extraction。**

含义:

- `graph_assembler.py` 可以继续保留 LangGraph node shell, 负责把 phase AST、prompt、tools、model、middleware chain 装配成可运行节点。
- `graph_assembler.py` 不再直接拥有 Agent path 的 `finish_task` 成败判断、SchemaEngine output 校验、business validator 调用、`ask_clarification` 拦截、middleware order 决策。
- 这些运行时职责必须迁到 middleware/factory, 尤其是 `CognitiveFlowMiddleware` 和新 middleware chain factory。

为什么不做 full replacement:

- `design.md §3` 明确允许在 `graph_assembler.py` 或独立 factory 装配 middleware, 说明 graph assembler shell 仍可作为装配边界存在。
- `design.md §4` 禁止 PR β 触碰 `manifest.py` / `loader.py` 等 compile 入口; full replacement 通常会牵连更大运行时和编译装配边界。
- full replacement 会把“引入 middleware runtime”扩大成“重写 LangGraph node 执行模型”, 工程量和回归风险明显超过 34h。
- requirements 里的“替代”应按职责替代理解: 替代旧私有 ReAct loop 内部的控制职责, 不等于删除所有 graph assembler node shell。

主控无需再裁决 full replacement vs responsibility extraction; 本 PR β 后续实现按 responsibility extraction 执行。

### §0.2 继承 PR γ0 的硬边界

PR β 承接 PR γ0 锁定的三条运行时契约:

1. `AgentNodeAST.validator: bool = False` 与 `SubgraphNodeAST.validator: bool = False` 已存在, PR β 只消费字段, 不再改 AST。
2. validator 统一签名已锁定为 `def validate(output: dict, state_slice: dict, **kwargs) -> None | dict`, PR β 实施 Agent runtime 调用和错误反馈。
3. `MVP0_MIDDLEWARE_ORDER_CONTRACT` 已锁定为 `ProtocolValidation → CognitiveFlow → ExecutionControl → Tracing → ToolError → LoopDetection`, PR β 负责把字符串契约变成真实 runtime 装配。

明确不做:

- 不改 `manifest.py` / `loader.py` / parser 的核心语义; compile-schema 与 body XML 回归留 PR γ1。
- 不做 compile/predict 静态 validator 阻断; 留 PR γ1.5。
- 不做 StateMapper / smart reducer / subgraph isolation; 留 PR γ2。
- 不删 `SkillNodeAST.exit_contract`、`runtime/exit_contract.py`、`codemod/v21_migrator.py`; legacy cleanup 留 PR γ3。

## §1 任务依赖图

```text
β1 spec intake + test plan
  └─> β2 tests-first
        ├─> β3 middleware order factory + skeleton classes
        │     ├─> β4 CognitiveFlow finish_task + SchemaEngine strict io.outputs gate
        │     │     └─> β5 validator runtime signature + error feedback
        │     ├─> β6 Agent runtime装配接入 / graph_assembler职责剥离
        │     └─> β7 ask_clarification parity + new skeleton no-op behavior
        └─> β8-β11 audit + docs + report + ship gate
```

可并行:

- β2 的 failing tests 可按 factory / CognitiveFlow / validator / graph_assembler integration 分文件并行写。
- β3 skeleton/factory 与 β4 SchemaEngine strict gate 可并行实现, 但合并前必须统一由 factory 装配。

必须串行:

- β3 必须先于 β6, 因为 Agent runtime 接入需要真实 factory。
- β4 必须先于 β5, 因为 business validator 只能在 `io.outputs` schema 通过后运行。
- Step 5 src audit 必须先于 Step 6 docs 同步 audit。

## §2 β1: SOP-08 Step 1 Spec Intake 和责任边界确认 (1.5h)

Owner: a1 主笔 / a2 audit / a3 audit。

实施内容:

1. 读取 `design.md`, `requirements.md`, `research.md`, PR γ0 `PR-REPORT.md`。
2. 把 requirements 的“替代旧 ReAct loop”落到责任剥离方案:
   - `finish_task` 校验职责迁出 graph assembler。
   - `ask_clarification` 拦截职责迁出 graph assembler。
   - validator runtime 调用职责迁出 graph assembler。
   - LangGraph node shell 和 tool/model/prompt 装配职责可保留。
3. 核对 PR γ0 contract:
   - `MVP0_MIDDLEWARE_ORDER_CONTRACT` 是唯一顺序真相源。
   - `V030_AGENT_EXIT_CONTRACT_TEXT` 使 Agent 端输出约束变成系统默认字符串 + `io.outputs`; PR β 必须补强 SchemaEngine strict gate。
   - `AgentNodeAST.validator` 是 bool flag, 不等同 legacy `LLMPhase.validator` module path。

验收:

- 本 tasks.md 不再保留 spec conflict 标记。
- implementation 任务不要求 full replacement。

## §3 β2: SOP-08 Step 2 Tests First (3h)

Owner: a1 主笔 / a2 audit / a3 audit。

建议新增/修改测试文件:

- `packages/graph-agent/tests/middleware/test_beta_middleware_factory.py`
- `packages/graph-agent/tests/middleware/test_beta_cognitive_flow_schema_gate.py`
- `packages/graph-agent/tests/middleware/test_beta_validator_runtime.py`
- `packages/graph-agent/tests/core/test_beta_agent_runtime_middleware_integration.py`

必须先写 failing tests:

1. Factory 顺序测试:
   - factory 返回 6 个 middleware instance。
   - 名称顺序严格等于 `MVP0_MIDDLEWARE_ORDER_CONTRACT`。
   - 测试禁止复制另一份硬编码顺序; 必须从 contract 常量读期望。
2. Skeleton 初始化测试:
   - `TracingMiddleware`, `ToolErrorHandlingMiddleware`, `LoopDetectionMiddleware` 均可实例化。
   - no-op 行为不改变非目标请求。
3. SchemaEngine strict gate 测试:
   - `finish_task` payload 与 `io.outputs` 不匹配时, `CognitiveFlowMiddleware` 拒绝。
   - 拒绝结果必须进入 LLM 可见 ToolMessage / retry feedback。
   - 不写入 final business data。
4. Validator 调用顺序测试:
   - SchemaEngine 校验失败时, validator 不被调用。
   - SchemaEngine 校验成功后, validator 接收 schema 通过后的 `output: dict`。
5. Validator 新签名测试:
   - 返回 `None` 表示通过。
   - 返回 `dict` 表示业务失败/提示 payload。
   - 抛异常时包装 `[F-v3-agent-validator-failed]`。
6. `ask_clarification` parity 测试:
   - attended 使用 interrupt 或现有等价路径。
   - unattended 返回保守 auto-answer。
   - 非 `finish_task` / `ask_clarification` 工具 pass-through。
7. Agent runtime integration:
   - 通过真实最小 Agent phase 或最小 graph assembler node, 证明 Agent path 的 `finish_task` 经过 middleware chain。
   - 证明 graph assembler 只做 shell 装配, 不直接判定 Agent `finish_task` 成败。

验收:

- tests-first commit 中这些测试应失败或明确 pending。
- 不在 tests-first commit 混入 src 实现。

## §4 β3: SOP-08 Step 4 Middleware Factory 和 6 层骨架 (5h)

Owner: a1 主笔 / a2 audit / a3 audit。

实施范围:

1. 新增 middleware factory, 推荐路径 `packages/graph-agent/src/graph_agent/middleware/factory.py`。
2. factory 输入显式参数:
   - `io_manager`
   - `schema_engine`
   - `current_phase_schema`
   - `business_validator`
   - `phase_name`
   - `unattended`
   - `interrupt_fn`
   - tracing/tool-error/loop-detection 所需可选依赖
3. factory 必须消费 `MVP0_MIDDLEWARE_ORDER_CONTRACT`, 输出 `list[AgentMiddleware]`。
4. 新增可实例化 skeleton:
   - `TracingMiddleware`
   - `ToolErrorHandlingMiddleware`
   - `LoopDetectionMiddleware`
5. `DEFAULT_MIDDLEWARE_ORDER` 可继续表示当前已实现 class tuple, 但不得破坏 γ0 TDD; PR β 的完整顺序以 factory 为准。

验收:

- `pytest packages/graph-agent/tests/middleware/test_beta_middleware_factory.py -v` 通过。
- `grep -R "MVP0_MIDDLEWARE_ORDER_CONTRACT" packages/graph-agent/src/graph_agent/middleware` 显示 factory 消费契约。
- 不存在另一份与 contract 平行漂移的顺序列表。

## §5 β4: SOP-08 Step 4 CognitiveFlow 接管 finish_task + SchemaEngine strict `io.outputs` gate (8h)

Owner: a1 主笔 / a2 audit / a3 audit。

这是 PR β 必修项, 来自 PR γ0 全局 audit 预警。

背景: PR γ0 删除 Agent body `<exit_contract>` 后, LLM 端只剩系统默认退出提示和 `io.outputs` schema。PR β 接管 `finish_task` 时, 必须确保底层 `SchemaEngine` 对 `io.outputs` 的结构化校验仍然严密, 不能因为输出契约降维成系统默认文案而放松。

实施要求:

1. `CognitiveFlowMiddleware` 的 finish_task 路径必须先解析 `business_data_md`, 再用 `SchemaEngine` / compiled `io.outputs` schema 做结构校验。
2. schema 失败时:
   - 返回 ToolMessage 或等价 retry feedback 给 LLM。
   - 标记 schema validation failed。
   - 不写入 final business data。
   - 不调用业务 validator。
3. schema 成功后才进入 validator runtime。
4. schema 缺失时必须 fatal 或明确拒绝, 不允许 silent pass。
5. 保留现有 `IOManager.resolve_hoist` / state update 语义, 不在 PR β 改 State-IO。

字段级 contract:

- `output`: validator 看到的是 schema 通过后的 dict。
- `state_slice`: middleware 提供最小只读 state view, 不把完整 mutable state 直接交给 validator。
- `phase_name`: 通过 `**kwargs` 传入。
- `attempt`: 如当前 runtime 能得到 retry 次数则传入; 不能得到时先传 `0` 并标注 followup。

验收:

- SchemaEngine failure test 通过。
- validator-not-called-on-schema-failure test 通过。
- 现有 `tests/middleware/test_cognitive_flow.py` 无回归。

## §6 β5: SOP-08 Step 4 Validator Runtime 新签名和错误反馈 (6h)

Owner: a1 主笔 / a2 audit / a3 audit。

实施要求:

1. 替换旧 `business_validator: Callable[[list[dict[str, Any]]], tuple[bool, list[str]]]` 语义。
2. 新 callable 形态对齐 γ0: `def validate(output: dict, state_slice: dict, **kwargs) -> None | dict`。
3. 返回语义:
   - `None`: 通过。
   - `dict`: 业务失败/提示 payload, middleware 包装成 retry feedback。
   - 抛异常: middleware 捕获并包装为 `[F-v3-agent-validator-failed]`。
4. 错误反馈必须进入 LLM 可见 ToolMessage / nudge loop, 不直接吞掉。
5. 超过重试次数时按现有执行控制策略阻断或交给 `ExecutionControlMiddleware`, 不在 validator 里直接改 loop 控制。

验收:

- validator pass/return-dict/raise 三类测试通过。
- 错误消息包含 `[F-v3-agent-validator-failed]`。
- 不给 `[F-v3-subgraph-validator-failed]` / `[F-v3-logic-validator-failed]` 写假 runtime; PR β 只落 Agent CognitiveFlow 路径, 其他 domain 标注 followup。

## §7 β6: SOP-08 Step 4 Agent Runtime 装配接入和 `graph_assembler.py` 职责剥离 (5h)

Owner: a1 主笔 / a2 audit / a3 audit。

实施要求:

1. 在 Agent phase runtime 装配入口接入 middleware factory。当前主要候选是 `graph_assembler.py` 的 Agent/SKILL node 组装路径。
2. `graph_assembler.py` 保留 shell 职责:
   - 组装 prompt。
   - 组装 business/resource/subagent tools。
   - 绑定模型。
   - 调用 middleware factory。
   - 把 middleware 产生的 state updates 接回 LangGraph。
3. `graph_assembler.py` 剥离职责:
   - 不直接判定 Agent `finish_task` 是否成功。
   - 不直接做 Agent `finish_task` schema/business validator gate。
   - 不直接处理 Agent `ask_clarification`。
   - 不自行维护 middleware order。
4. legacy `SkillNodeAST` path 如仍使用旧 private loop, 必须显式隔离并测试不影响 Agent path。

验收:

- integration test 证明 Agent `finish_task` 经过 `CognitiveFlowMiddleware`。
- grep/代码审查证明 Agent path 不再绕过 middleware 直接处理 finish_task 成败。
- 不要求删除整个 graph assembler LangGraph node shell。

## §8 β7: SOP-08 Step 4 ask_clarification + Tracing/ToolError/LoopDetection 最小闭环 (4h)

Owner: a1 主笔 / a2 audit / a3 audit。

实施要求:

1. `ask_clarification` 由 `CognitiveFlowMiddleware` 统一拦截:
   - attended: 使用 interrupt 或现有等价路径。
   - unattended: 返回保守 auto-answer 并继续执行。
2. `TracingMiddleware` skeleton:
   - 可实例化。
   - no-op 通过。
   - 预留 trace hook 名称, 不承诺完整 tracing 事件。
3. `ToolErrorHandlingMiddleware` skeleton:
   - 可实例化。
   - no-op 或最小 tool exception 包装, 不吞异常。
4. `LoopDetectionMiddleware` skeleton:
   - 可实例化。
   - PR β 如只做占位, 需文档说明真正 loop detection 策略留后续。

验收:

- middleware package exports 6 层所需 class。
- factory integration test 覆盖所有 class 初始化。
- 不引入不被测试覆盖的 silent fallback。

## §9 β8: SOP-08 Step 5 Src 偏移 Audit Gate (2h)

Owner: a1 提交候选实现 / a2 honesty audit / a3 PM-proxy audit。

a2 必查:

1. 是否真实消费 `MVP0_MIDDLEWARE_ORDER_CONTRACT`, 而不是复制一份顺序字符串。
2. `CognitiveFlowMiddleware` 是否仍使用旧 `(passed, errors)` validator 协议。
3. SchemaEngine 失败时业务 validator 是否被错误调用。
4. Agent path 是否仍绕过 middleware 直接处理 `finish_task` 成败。
5. 新增 skeleton 是否只是可导入, 但 factory 未装配。

a3 必查:

1. 是否遵守 PM 三原则: 对齐 MVP0, 不向后兼容 Agent 新 path, 不写 fallback/mock。
2. 是否把 γ1/γ1.5/γ2/γ3 scope 偷偷塞进 PR β。
3. 是否遗漏 γ0 audit 预警的 `io.outputs` 严格校验。
4. responsibility extraction 是否被误实现成半套旧 loop + 半套 middleware 双系统。

通过标准:

- a2/a3 对 src 偏移均 PASS, 或所有 NEEDS FIX 已修复并复验。

## §10 β9: SOP-08 Step 6 Docs 同步 Audit Gate (2h)

Owner: a1 docs sync / a2 audit / a3 audit。

必须同步:

1. `docs/engine/mvp0/execution-runtime/mvp0-alignment.md`
   - middleware chain 顺序。
   - finish_task 由 CognitiveFlow 接管。
   - SchemaEngine `io.outputs` strict gate。
   - validator 新签名和错误反馈。
   - responsibility extraction: graph assembler shell 保留, runtime control 责任迁出。
2. `docs/engine/mvp0/skill-spec/06-cognitive-template-spec.md`
   - 如 PR β 改变 finish_task feedback 文案或 runtime 行为, 必须同步。
3. `docs/engine/mvp0/skill-spec/11-error-code-spec.md`
   - `[F-v3-agent-validator-failed]` 从 placeholder 变成 runtime 行为时, 补触发条件。
4. 本 spec 4 件套:
   - `design.md`, `requirements.md`, `research.md`, `tasks.md` 若实现阶段有主控裁决或工程现实调整, 必须同步。

Step 6 特别区分:

- src 偏移归 §9。
- docs 缺字段、错误码残留、ship gate 文案不准归本节。

## §11 β10: SOP-08 Step 7 PR β Report (1.5h)

Owner: a1 主笔 / a2 audit / a3 audit。

报告落盘:

- `.kiro/specs/engine-mvp0-rebuild-v030/round-11-PR-beta-middleware/PR-REPORT.md`

报告必须包含:

1. middleware factory 字段级翻译。
2. CognitiveFlow finish_task / SchemaEngine / validator 三段式流程。
3. `graph_assembler.py` responsibility extraction 边界。
4. tests 和 ship gate 数字。
5. 已知 followup: γ1/γ1.5/γ2/γ3。

## §12 β11: SOP-08 Step 8-9 Ship Gate 和合并前检查 (3h)

Owner: a1 执行 / a2 audit / a3 audit / 主控最终复核。

本地 ship gate:

```bash
uvx ruff check packages/graph-agent
UV_PROJECT_ENVIRONMENT=/tmp/agent-harness-uv-beta uv run --package graph-agent mypy packages/graph-agent/src
UV_PROJECT_ENVIRONMENT=/tmp/agent-harness-uv-beta uv run pytest packages/graph-agent/tests/middleware -v
UV_PROJECT_ENVIRONMENT=/tmp/agent-harness-uv-beta uv run pytest packages/graph-agent/tests/core/test_gamma0_contract_tdd.py -v
UV_PROJECT_ENVIRONMENT=/tmp/agent-harness-uv-beta uv run pytest packages/graph-agent/tests -q
```

grep ship checks:

```bash
grep -R "MVP0_MIDDLEWARE_ORDER_CONTRACT" -n packages/graph-agent/src/graph_agent/middleware
grep -R "Callable\\[\\[list\\[dict\\[str, Any\\]\\]\\], tuple\\[bool, list\\[str\\]\\]\\]" -n packages/graph-agent/src/graph_agent || true
grep -R "F-v3-agent-validator-failed" -n packages/graph-agent/src/graph_agent docs/engine
grep -R "finish_task_result" -n packages/graph-agent/src/graph_agent/core/graph_assembler.py
```

合并前:

1. a2 honesty audit PASS。
2. a3 PM-proxy audit PASS。
3. responsibility extraction 边界未被实现阶段扩大。
4. CI green。

## §13 Task 清单汇总

| Task | 内容 | 估算 | Owner / Audit |
|---|---|---:|---|
| β1 | Spec intake + responsibility extraction 边界确认 | 1.5h | a1 / a2 / a3 |
| β2 | Tests-first plan and failing tests | 3h | a1 / a2 / a3 |
| β3 | Middleware factory + 6 class order/skeleton | 5h | a1 / a2 / a3 |
| β4 | CognitiveFlow finish_task + SchemaEngine strict `io.outputs` gate | 8h | a1 / a2 / a3 |
| β5 | Validator runtime new signature + `[F-v3-agent-validator-failed]` feedback | 6h | a1 / a2 / a3 |
| β6 | Agent runtime装配接入 / graph_assembler responsibility extraction | 5h | a1 / a2 / a3 |
| β7 | ask_clarification + Tracing/ToolError/LoopDetection minimum closure | 4h | a1 / a2 / a3 |
| β8 | Step 5 src audit gate | 2h | a1 / a2 / a3 |
| β9 | Step 6 docs sync audit gate | 2h | a1 / a2 / a3 |
| β10 | Step 7 PR report | 1.5h | a1 / a2 / a3 |
| β11 | Step 8-9 ship gate + merge checks | 3h | a1 / a2 / a3 / 主控 |

实施任务 β1-β7 小计: 32.5h。

Audit / docs / report / ship gate β8-β11 小计: 8.5h。

合计: 41h。frontmatter 仍保留 a2 三件套原估算 `34h`; 是否压缩实施或 audit buffer 由主控复核。
