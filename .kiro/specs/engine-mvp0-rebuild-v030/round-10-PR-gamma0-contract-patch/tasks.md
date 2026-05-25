---
spec: engine-mvp0-rebuild-v030/round-10-PR-gamma0-contract-patch
phase: PR γ0 (契约补丁, PR α 后 PR β 前)
owner: a1 主笔 / a2 audit / 主控复核
工程量: 14h (1.75d) + audit/e2e/CI buffer 1.25d
依赖: PR α (Gateway + llm-roles Phase 1) 已 push (#91 待 review/merge)
后续: PR β (middleware 34h) → γ1 (compile-schema 50h) → γ1.5 (preflight 38h) → γ2 (state-io 40h) → γ3 (cleanup 44h)
---

# PR γ0: Contract Patch Tasks

## §0 PM 决策记录和 Scope

PR γ0 是 PR alpha 之后、PR beta 之前的 **契约补丁 PR**，实施量锁定为 **14h = 1.75d**。它只处理会阻塞 PR beta middleware runtime refactor 的契约偏移，不替代 beta，也不宣称 R1-R12 完成。

PM 最新真相来自 `/tmp/v030-cutover-correction-todo-2026-05-24.md` §12 和 §13 优先级声明；§12.5 明确要求关键契约段先锁死，包括 Agent body allowlist、`<exit_contract>` 不再来自 SKILL.md、validator 统一签名、middleware order、resolver DI、trace 双层边界。

γ0 精确定义:

1. **做 R4 前置契约修正**: Agent AST/loader 移除 SKILL.md body `<exit_contract>` 必填，避免 PR beta 接 middleware factory 后继续背旧 AST。
2. **做 validator 字段契约**: `AgentNodeAST` 和 `SubgraphNodeAST` 增加 `validator: bool = False`，loader 能解析，测试能锁住默认值。
3. **做 middleware order 契约**: 在 docs/spec 和 minimal code constants 中锁定 PR beta 的 runtime middleware 顺序。
4. **做 validator 统一签名和错误码 placeholder**: 只锁接口和错误码，不在 γ0 实施 validator runtime。
5. **做 test/docs/CI 修尾**: 让 γ0 成为 PR beta 的稳定起点。

明确不做:

- 不做 **PR alpha** 已完成内容: Gateway independent package、`ModelResolverProtocol` DI、LLM Roles Phase 1 data layer、gateway `[F-v3-gateway-*]`。
- 不做 **PR beta**: 不替换手写 ReAct loop，不新建 factory，不接 `CognitiveFlowMiddleware` live，不新增 ToolErrorHandling/Tracing/LoopDetection middleware。
- 不做 **γ1**: 不恢复 GRAPH.md body XML，不补 7 类 mention 静态校验，不做 compile-schema 大段。
- 不做 **γ1.5**: 不做 predict/preflight 阻断，不做 compile 期 LLM 提醒。
- 不做 **γ2**: 不做 StateMapper / state-io / subgraph isolation。
- 不做 **γ3**: 不做 V2.1 cleanup、全 engine trace/error contract 清扫。
- 不做 LLM Roles UI Phase 2-5。

## §1 字段级现状实证

整体 MVP0 spec 当前仍要求 Agent AST 与 cognitive template 对齐。`requirements.md:53` 标出 R4 "Agent AST and cognitive template"，`design.md:29-37` 定义 Agent/Subgraph AST，`tasks.md:124-132` 曾要求 `AgentNodeAST` 替换旧 `SkillNodeAST`，但旧任务里仍列了 `exit_contract` 字段。

当前 src 中 `packages/graph-agent/src/graph_agent/core/manifest.py:155-172` 的 `AgentNodeAST` 仍有 `exit_contract: str = Field(min_length=1)`，这与 PM §12.5 的 "cognitive template `<exit_contract>` hardcode 在模板, 不从 SKILL.md" 冲突。γ0 必须先删掉 AST 必填输入，PR beta 才不会把旧字段带进 middleware factory。

当前 `packages/graph-agent/src/graph_agent/core/manifest.py:146-152` 的 `SubgraphNodeAST` 有 `mode/sub_skill_ref/target_skill/io`，没有 `validator`。`AgentNodeAST` 同样没有 `validator`。PM §11.4 已确认 "AST schema 改造 manifest.py:145+:165 加 validator 字段" 维持。

当前 loader 在 `packages/graph-agent/src/graph_agent/core/loader.py:1091-1100` 的 `allowed` 仍包含 `exit_contract`。Agent path 在 `loader.py:1117-1120` 调 `_parse_agent_body` 后校验 `AgentNodeAST`。`_parse_agent_body` 在 `loader.py:1179-1185` 读取并强制 `<exit_contract>`，缺失时抛 `[F-v3-agent-exit-contract-missing]`，并在 `loader.py:1186-1192` 返回 `exit_contract` 字段。γ0 必须移除这条 body 输入链。

当前 middleware 常量在 `packages/graph-agent/src/graph_agent/middleware/__init__.py:42-55`，`DEFAULT_MIDDLEWARE_ORDER` 只有 `ProtocolValidationMiddleware`、`CognitiveFlowMiddleware`、`ExecutionControlMiddleware` 三项。PM §12.5 要先锁未来顺序，γ0 只加 minimal constants，不实现 beta middleware。

当前 `ProtocolValidationMiddleware` 在 `packages/graph-agent/src/graph_agent/middleware/protocol_validation.py:68-213` 已存在 state contract 检查。`CognitiveFlowMiddleware` 在 `cognitive_flow.py:54-90` 已接受 `business_validator`，但签名仍是 `Callable[[list[dict[str, Any]]], tuple[bool, list[str]]]`；`_run_business_validator` 在 `cognitive_flow.py:371-390` 仍按旧 `(passed, errors)` 风格调用。γ0 只锁新签名契约，不改 runtime 调用路径。

当前 `ExecutionControlMiddleware` 在 `execution_control.py:67-90` 已拥有 iteration/dead-end/light loop detection 描述，但 PM §12.4 把 PR beta 的最小 LoopDetection 独立列为后续项。γ0 不在这里扩实现，只把 order contract 写清，避免 beta 接线时顺序跑偏。

## §2 依赖图

```text
γ0_1 Agent exit_contract removal
  ├─> γ0_2 validator bool field parse
  │     └─> γ0_4 validator signature + error placeholders
  └─> γ0_3 middleware order contract

γ0_5 tests/docs/CI depends on γ0_1-γ0_4
```

可并行:

- γ0_1 和 γ0_3 可并行，分别处理 AST/loader 与 middleware order。
- γ0_2 和 γ0_4 可并行起草测试，但 γ0_4 的 placeholder 文档需引用 γ0_2 的字段名。

必须串行:

- γ0_1 必须先于 PR beta，因为 beta factory 会读取 Agent AST。
- γ0_3 必须先于 PR beta，因为 beta 会按 order 常量装配 middleware。
- γ0_5 最后，负责回归测试、docs/spec 对齐和 ship gate。

## §3 Task 列表

### γ0_1 R4 Agent AST/loader `exit_contract` removal (4h)

**WHY**: PM §12.5 已拍板 `<exit_contract>` hardcode 在 cognitive template，不再从 SKILL.md body 读取。当前 `AgentNodeAST.exit_contract` 和 loader body 强制要求会让 PR beta 继续消费旧 contract。

**WHAT**:

- 修改 `packages/graph-agent/src/graph_agent/core/manifest.py:155-172`:
  - 删除 `AgentNodeAST.exit_contract: str = Field(min_length=1)`。
  - 保留 `role`, `goal`, `steps`, `protocols`, `io`, `tools`, `subagents`, `subgraphs`, `references`, `examples`, `max_iterations`, `llm_role`, `system_prompt`。
  - `_render_legacy_system_prompt` 不再依赖 `exit_contract` 字段。
- 修改 `packages/graph-agent/src/graph_agent/core/loader.py:1091-1100`:
  - 从 Agent body allowed tags 移除 `exit_contract`。
  - 若 legacy `SkillNodeAST` path 仍需要旧 `<exit_contract>`，必须限定在非 `mode: agent` 旧 path，不能污染 V0.3 Agent。
- 修改 `loader.py:1170-1192`:
  - `_parse_agent_body` 只强制 `<role>` 和 `<goal>`。
  - 删除 `[F-v3-agent-exit-contract-missing]` 生产路径。
  - 返回 dict 不再包含 `exit_contract`。
- 同步 loader allowed/required tag tests:
  - `SKILL.md mode: agent` 缺 `<exit_contract>` 必须通过 parse。
  - `SKILL.md mode: agent` 出现 `<exit_contract>` 必须按 unknown/unsupported tag 失败，防止旧字段回流。

**HOW**:

- 先写 failing tests 锁定: no-exit-contract agent body succeeds, legacy tag rejected。
- 再改 AST/loader。
- 不引入 fallback 字段，不保留 deprecated alias。

### γ0_2 Agent/Subgraph `validator: bool = False` field contract (2h)

**WHY**: PM §11.4 已确认 `manifest.py:145+:165` 加 validator 字段。它是后续 LOGIC/SUBGRAPH wrapper 和 Agent CognitiveFlow validator 的开关，但 γ0 只建立 AST/parse 契约。

**WHAT**:

- 修改 `packages/graph-agent/src/graph_agent/core/manifest.py:146-152`:
  - `SubgraphNodeAST` 新增 `validator: bool = False`。
  - 字段含义: 是否启用该 phase 的业务 validator。
  - 默认 false，缺省时不触发任何 runtime validator。
- 修改 `packages/graph-agent/src/graph_agent/core/manifest.py:155-172`:
  - `AgentNodeAST` 新增 `validator: bool = False`。
  - 字段含义同 Subgraph，后续 PR beta/γ1.5 消费。
- 修改 loader parse:
  - frontmatter 中的 `validator: true/false` 能进入 AST。
  - 未声明时 AST 字段稳定为 `False`。
  - 非 bool 值应走 Pydantic validation fatal，不做字符串宽松转换。
- 不给 `LogicNodeAST` 加本任务字段，除非 requirements/design 明确同步要求；γ0 brief 只要求 Agent/Subgraph。

**HOW**:

- 先补 manifest/loader unit tests:
  - Agent validator default false。
  - Agent validator true parse。
  - Subgraph validator default false。
  - Subgraph validator true parse。
  - validator 非 bool fatal。
- 再改 schema。
- 不接 runtime hook，不加载 `validator.py`。

### γ0_3 Middleware order contract docs/spec + minimal code constants (3h)

**WHY**: PR beta 要做 middleware runtime refactor。若 order 不先锁死，beta 很容易把 ProtocolValidation、CognitiveFlow、Tracing、ToolError、LoopDetection 等职责接反。

**WHAT**:

- 在 `.kiro/specs/engine-mvp0-rebuild-v030/round-10-PR-gamma0-contract-patch/{requirements,design,research}.md` 或同 PR 文档中锁定顺序:
  1. `ProtocolValidation`
  2. `CognitiveFlow`
  3. `ExecutionControl`
  4. `Tracing`
  5. `ToolError`
  6. `LoopDetection`
- 修改 `packages/graph-agent/src/graph_agent/middleware/__init__.py:42-55` minimal constants:
  - 保留当前可实例化 class tuple，避免引用不存在 class 造成 import error。
  - 新增纯字符串契约常量，例如 `MVP0_MIDDLEWARE_ORDER_CONTRACT: tuple[str, ...] = (...)`。
  - 注释明确 "γ0 locks order; PR beta implements missing middleware classes"。
- 现有 `DEFAULT_MIDDLEWARE_ORDER` 如仍只含 3 个 class，需在 docstring 中说明它是 "currently implemented order"，不是完整 MVP0 contract。
- 增加 order regression test:
  - 字符串 contract 必须等于六项顺序。
  - 当前 class order 前三项必须与 contract 前三项一致。

**HOW**:

- 不新建 `tracing.py`、`tool_error_handling.py`、`loop_detection.py`。
- 不改 create_agent 装配。
- 不把 order contract 放在 chat 注释里，必须有 code-level constant 供 tests pin。

### γ0_4 Validator unified signature contract + error code placeholders (2h)

**WHY**: PM §12.5 已锁 validator 统一签名: `def validate(output: dict, state_slice: dict, **kwargs) -> None | dict`。γ0 先锁接口和错误码，PR beta/γ1.5 再做实际 runtime hook。

**WHAT**:

- 在 spec/doc 中锁定 validator 文件接口:
  - 文件名: `validator.py`。
  - 入口函数: `validate`。
  - 签名: `def validate(output: dict, state_slice: dict, **kwargs) -> None | dict`。
  - `output`: phase 已生成并通过 schema/Pydantic 的业务输出。
  - `state_slice`: runtime 提供的最小 state 视图，不允许 validator 直接拿完整 mutable state。
  - `**kwargs`: 后续扩展口，如 `phase_name`, `mode`, `attempt`, `run_id`。
  - 返回 `None`: 通过。
  - 返回 `dict`: 结构化失败/提示 payload；具体字段由后续 PR 锁定。
- 锁错误码 placeholder，不实施:
  - `[F-v3-agent-validator-failed]`
  - `[F-v3-subgraph-validator-failed]`
  - `[F-v3-logic-validator-failed]`
- 对当前 `CognitiveFlowMiddleware` 旧 `business_validator` 签名做文档标注:
  - `cognitive_flow.py:68` 当前是旧 callable。
  - `cognitive_flow.py:371-390` 当前按旧 `(passed, errors)` 调用。
  - PR beta 改 factory/live middleware 时再替换 wrapper。

**HOW**:

- γ0 可以新增只读 protocol/type alias 或 docs-level contract；若新增 code constant，应避免 runtime import side effect。
- 不在 γ0 动态 import `validator.py`。
- 不在 γ0 改 LOGIC/SUBGRAPH/AGENT hook 行为。

### γ0_5 Tests, docs, CI and ship gate (3h)

**WHY**: γ0 是 PR beta 的地基 PR。它小但必须精确，测试要卡住 "不再读 `<exit_contract>`" 和 "middleware order 不漂移"。

**WHAT**:

- 测试覆盖 γ0_1-γ0_4。
- 同步四件套 spec:
  - `requirements.md`: 明确 Agent body 不含 `<exit_contract>`，validator 字段默认 false，middleware order contract。
  - `design.md`: 写字段级设计和边界。
  - `research.md`: 记录为什么 γ0 前置于 beta，为什么不实施 runtime。
  - `tasks.md`: 本文件作为执行清单。
- 同步 docs 时只改 γ0 相关文档，不顺手清其他 spec。
- 运行最小 CI gate。

**HOW**:

- SOP-08: tests first，src 服测试。
- a1 实施后交 a2 drift audit；PM 复核后才进入 beta。
- 不以 "后续会改" 为理由放宽 γ0 tests。

## §4 Test 覆盖矩阵

| Task | Unit tests | Integration tests | Ship checks |
|---|---|---|---|
| γ0_1 | `AgentNodeAST` 无 `exit_contract`; loader 缺 `<exit_contract>` 成功; legacy `<exit_contract>` tag rejected | minimal Agent `SKILL.md` parse/load succeeds | `rg -n "AgentNodeAST.*exit_contract|F-v3-agent-exit-contract-missing|blocks.get\\(\"exit_contract\"\\)" packages/graph-agent/src/graph_agent/core` 无 V0.3 Agent 命中 |
| γ0_2 | Agent/Subgraph `validator` default false / true parse / non-bool fatal | phase document parse 后 AST 字段稳定 | mypy 覆盖 manifest/loader |
| γ0_3 | middleware order string constant 等于六项; class order 前三项一致 | PR beta factory 可直接消费 order contract | `rg -n "MVP0_MIDDLEWARE_ORDER_CONTRACT|DEFAULT_MIDDLEWARE_ORDER" packages/graph-agent/src/graph_agent/middleware` |
| γ0_4 | validator signature docs/constant test; error code placeholder presence | 无 runtime hook integration | `rg -n "\\[F-v3-(agent|subgraph|logic)-validator-failed\\]"` 命中 spec/docs |
| γ0_5 | docs/spec consistency smoke | selected graph-agent tests | a2 drift audit PASS, CI green |

最低命令集:

```bash
uvx ruff check packages/graph-agent/src packages/graph-agent/tests
uvx mypy packages/graph-agent/src
pytest packages/graph-agent/tests -q
```

如实施中触及 Studio backend 或 gateway package，应视为 scope drift，必须退回或另开任务；γ0 正常不需要跑 Studio/Tauri。

## §5 工程量估算

| Task | 工时 | 说明 |
|---|---:|---|
| γ0_1 R4 Agent AST/loader `exit_contract` removal | 4h | manifest + loader + parse tests + grep verify |
| γ0_2 Agent/Subgraph `validator: bool = False` | 2h | schema 字段 + loader parse + validation tests |
| γ0_3 middleware order contract | 3h | spec/docs + minimal code constant + order tests |
| γ0_4 validator signature + error placeholders | 2h | docs/spec contract + placeholder grep/tests |
| γ0_5 tests/docs/CI 修尾 | 3h | focused pytest/ruff/mypy + a2 audit prep |
| **合计** | **14h = 1.75d** | 不含 audit/e2e/CI buffer |

额外 wall-clock buffer:

- a2 drift audit: 0.5d。
- a3 e2e / smoke: 0.5d。
- CI/rebase/main 三连绿: 0.25d。
- 合计: 1.25d，不计入 14h 实施工时。

## §6 Ship 验收

PR γ0 合入前必须同时满足:

- V0.3 Agent `SKILL.md` body 不再要求 `<exit_contract>`。
- V0.3 Agent `SKILL.md` body 出现 `<exit_contract>` 不被静默接受。
- `AgentNodeAST` 不再含 `exit_contract` 字段。
- `AgentNodeAST.validator` 和 `SubgraphNodeAST.validator` 存在，类型为 bool，默认 false。
- loader 能解析 Agent/Subgraph frontmatter `validator: true/false`。
- middleware 完整顺序契约以 code-level constant 锁定: `ProtocolValidation -> CognitiveFlow -> ExecutionControl -> Tracing -> ToolError -> LoopDetection`。
- `DEFAULT_MIDDLEWARE_ORDER` 当前实现顺序与完整契约前三项一致。
- validator 统一签名写入 spec/docs: `def validate(output: dict, state_slice: dict, **kwargs) -> None | dict`。
- 三个 validator placeholder 错误码写入 spec/docs: `[F-v3-agent-validator-failed]`, `[F-v3-subgraph-validator-failed]`, `[F-v3-logic-validator-failed]`。
- 未新增 PR beta runtime 实现文件，未替换 create_agent，未改 ReAct loop。
- `ruff` / `mypy` / focused `pytest` 通过。
- a2 drift audit PASS: implementation 与 γ0 requirements/design/research/tasks 字段一致。
- 主控复核确认 PR beta 可以基于 γ0 order/AST/validator contract 启动。

## §7 风险点

- `exit_contract` 清理容易误伤 legacy `SkillNodeAST` path。γ0 目标是 V0.3 Agent body，不应破坏仍存在的旧 path，除非同 PR 明确 hard cut。
- `validator: bool` 容易被误实现成 runtime hook。γ0 只加字段和 contract，不加载 `validator.py`。
- middleware order 常量容易引用尚未实现的 class 导致 import error。γ0 应使用 string contract 表达未来六项顺序，同时保持当前 class tuple 可导入。
- `ExecutionControlMiddleware` 当前 docstring 已写 "lightweight loop detection"，但 PM beta 仍要求最小 `LoopDetectionMiddleware` 独立项。γ0 文档必须写清当前实现与未来 contract 的差异，避免 beta 误判已完成。
- validator 新签名与 `CognitiveFlowMiddleware` 当前旧 `business_validator` 签名不一致。γ0 只锁新签名，PR beta 改 live middleware 时必须做 wrapper/call-site cutover。
