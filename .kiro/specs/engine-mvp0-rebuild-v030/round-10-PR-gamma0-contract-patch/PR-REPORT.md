---
spec: engine-mvp0-rebuild-v030/round-10-PR-gamma0-contract-patch
phase: PR γ0 Step 7 report
branch: feat/pr-gamma0-contract-patch
owner: a1 主笔 / a2 honesty audit / a3 audit 复审
---

# PR γ0 Report: Contract Patch

## 1. PR 目标

PR γ0 是 V0.3.0 engine MVP0 cutover 在 PR α 之后、PR β 之前的契约补丁。它不实现 middleware runtime, 不清理全部 legacy V2.1 路径, 只把 PR β 必须依赖的 AST、loader、validator、middleware 顺序契约先钉住。

根本动机不是“修几处测试红灯”, 而是把 V0.3.0 的 Agent 契约从旧 `SkillNodeAST` 思路里切出来。旧路径把 `<exit_contract>` 当成作者必须写在 `SKILL.md` body 里的字段; MVP0 要求输出契约由 cognitive template 统一装配, 所以 AST 入口必须先变干净。否则 PR β 接 middleware factory 时会继续把旧字段当真相源。

本 PR 的最终分支包含 6 个有效提交:

- `c7af5fc` 写 round-10 γ0 四件套 spec。
- `6042fc1` 先写 γ0 TDD。
- `8145600` 实施 5 项必修源码契约。
- `3c48931` 删除私有 exit_contract 兜底常量, 澄清 validator 字段语义。
- `f67f1cf` 同步 skill-spec 文档、修复 05-agent 文件尾部损坏、补 validator 非 bool 测试。
- `8541f9a` 清掉 F8/F9 文档残留, 让 cognitive-template 与 execution-runtime 对齐。

## 2. 五项必修字段级翻译

### 2.1 Agent AST 删除 `exit_contract`, Skill legacy 保留 (对应 γ0_1 cutover 上半段)

`AgentNodeAST` 现在只表达 V0.3.0 Agent body 和 frontmatter 的真实输入: `role`, `goal`, `steps`, `protocols`, `io`, `validator`, `tools`, `subagents`, `subgraphs`, `references`, `examples`, `max_iterations`, `llm_role`, `system_prompt`。在 [manifest.py](/home/sevenx/coding/agent-harness/packages/graph-agent/src/graph_agent/core/manifest.py:157) 到 [manifest.py](/home/sevenx/coding/agent-harness/packages/graph-agent/src/graph_agent/core/manifest.py:175) 之间已经没有 `exit_contract` 字段。

`SkillNodeAST.exit_contract` 没有删除, 仍在 [manifest.py](/home/sevenx/coding/agent-harness/packages/graph-agent/src/graph_agent/core/manifest.py:193) 到 [manifest.py](/home/sevenx/coding/agent-harness/packages/graph-agent/src/graph_agent/core/manifest.py:199) 保留。这不是向后兼容回流到 Agent, 而是 legacy `mode: skill` 路径还未进入 PR γ3 cleanup。换句话说, γ0 切的是 Agent 合同入口, 不顺手拆旧仓库。

Loader 也按这条边界实现。`extract_raw_blocks` 的 shared allowed list 仍含 `"exit_contract"`, 因为旧 `SkillNodeAST` 还要读取它, 见 [loader.py](/home/sevenx/coding/agent-harness/packages/graph-agent/src/graph_agent/core/loader.py:1091) 到 [loader.py](/home/sevenx/coding/agent-harness/packages/graph-agent/src/graph_agent/core/loader.py:1100)。但 Agent 分支不消费该 block, 而是在 `_parse_agent_body` 里用 substring guard 明确拒绝 `<exit_contract>`, 见 [loader.py](/home/sevenx/coding/agent-harness/packages/graph-agent/src/graph_agent/core/loader.py:1179)。失败消息是 `unknown top-level tag exit_contract`, 表达的是“这个标签不再属于 Agent body”, 而不是“缺了一个必填字段”。

测试把这条边界钉住: 没有 `<exit_contract>` 的 Agent 可加载, 见 [test_gamma0_contract_tdd.py](/home/sevenx/coding/agent-harness/packages/graph-agent/tests/core/test_gamma0_contract_tdd.py:106); 仍写 `<exit_contract>` 的 Agent 会失败, 见 [test_gamma0_contract_tdd.py](/home/sevenx/coding/agent-harness/packages/graph-agent/tests/core/test_gamma0_contract_tdd.py:117)。

### 2.2 Agent/Subgraph 新增 `validator: bool = False` (对应 γ0_2)

`SubgraphNodeAST.validator` 在 [manifest.py](/home/sevenx/coding/agent-harness/packages/graph-agent/src/graph_agent/core/manifest.py:153) 到 [manifest.py](/home/sevenx/coding/agent-harness/packages/graph-agent/src/graph_agent/core/manifest.py:154) 定义为 bool flag。`AgentNodeAST.validator` 在 [manifest.py](/home/sevenx/coding/agent-harness/packages/graph-agent/src/graph_agent/core/manifest.py:166) 到 [manifest.py](/home/sevenx/coding/agent-harness/packages/graph-agent/src/graph_agent/core/manifest.py:167) 同样定义为 bool flag。

这个字段的含义是“V0.3 AST 上是否启用业务 validator”, 不是旧 `LLMPhase.validator` 的 module path, 也不是 runtime callable。代码注释明确写了 “not the legacy LLMPhase.validator module path”。这个注释是必要的, 因为旧 engine 里 `validator` 曾经承载过 module path/callable 语义; γ0 只锁新 AST 表面, runtime 迁移留给 PR β/γ1.5。

`LogicNodeAST` 没有被加同名字段。理由是 γ0 brief 只要求 Agent/Subgraph, LOGIC 的 validator 生命周期在既有 spec 里已经存在, 不在这轮 AST contract patch 里扩大。

测试覆盖三种语义: 默认值是 `False`, frontmatter `validator: true` 能进入 AST, 非 bool 会走 Pydantic `ValidationError`。对应断言在 [test_gamma0_contract_tdd.py](/home/sevenx/coding/agent-harness/packages/graph-agent/tests/core/test_gamma0_contract_tdd.py:125)、[test_gamma0_contract_tdd.py](/home/sevenx/coding/agent-harness/packages/graph-agent/tests/core/test_gamma0_contract_tdd.py:137)、[test_gamma0_contract_tdd.py](/home/sevenx/coding/agent-harness/packages/graph-agent/tests/core/test_gamma0_contract_tdd.py:148)。

### 2.3 Cognitive Template 内置 exit contract 文案 (对应 γ0_1 cutover 下半段, 来自 fix commit 3c48931)

`apply_v030_cognitive_template` 不再接收 `exit_contract` 入参。函数签名从外部注入输出契约, 改成内部统一装配, 见 [prompt.py](/home/sevenx/coding/agent-harness/packages/graph-agent/src/graph_agent/cognitive/prompt.py:130) 到 [prompt.py](/home/sevenx/coding/agent-harness/packages/graph-agent/src/graph_agent/cognitive/prompt.py:142)。

固定文案现在由 `V030_AGENT_EXIT_CONTRACT_TEXT` 承载, 见 [prompt.py](/home/sevenx/coding/agent-harness/packages/graph-agent/src/graph_agent/cognitive/prompt.py:20)。模板尾部的 `<exit_contract>` 使用这个常量并追加 `output_schema`, 见 [prompt.py](/home/sevenx/coding/agent-harness/packages/graph-agent/src/graph_agent/cognitive/prompt.py:223) 到 [prompt.py](/home/sevenx/coding/agent-harness/packages/graph-agent/src/graph_agent/cognitive/prompt.py:225)。

这里的设计决策是: 输出契约像系统统一发的安全带, 不应该每个 skill 作者自己绑一条。作者仍声明 `io.outputs`; engine 负责把它放到 prompt 尾部, 用 recency bias 约束 `finish_task`。

Step 6 F8/F9 把文档也同步到这个事实。`06-cognitive-template-spec.md` 的概览表现在写“系统默认字符串 + io.outputs schema”, 错误码是 `[F-v3-cognitive-output-schema-render-failed]`, 见 [06-cognitive-template-spec.md](/home/sevenx/coding/agent-harness/docs/engine/skill-spec/06-cognitive-template-spec.md:86)。`execution-runtime/mvp0-alignment.md` 明确 `AgentNodeAST.exit_contract` 退役、`SkillNodeAST.exit_contract` 只作为 legacy path 保留, 见 [mvp0-alignment.md](/home/sevenx/coding/agent-harness/docs/engine/execution-runtime/mvp0-alignment.md:93) 到 [mvp0-alignment.md](/home/sevenx/coding/agent-harness/docs/engine/execution-runtime/mvp0-alignment.md:94)。

### 2.4 Validator contract placeholder (对应 γ0_4)

γ0 新增 `graph_agent.core.validator_contract` 作为轻量契约模块。`VALIDATOR_SIGNATURE` 锁定字符串 `def validate(output: dict, state_slice: dict, **kwargs) -> None | dict`, 见 [validator_contract.py](/home/sevenx/coding/agent-harness/packages/graph-agent/src/graph_agent/core/validator_contract.py:9)。

`VALIDATOR_ERROR_CODES` 锁定三类 placeholder: `[F-v3-agent-validator-failed]`, `[F-v3-subgraph-validator-failed]`, `[F-v3-logic-validator-failed]`, 见 [validator_contract.py](/home/sevenx/coding/agent-harness/packages/graph-agent/src/graph_agent/core/validator_contract.py:11) 到 [validator_contract.py](/home/sevenx/coding/agent-harness/packages/graph-agent/src/graph_agent/core/validator_contract.py:15)。

这个模块不动态 import `validator.py`, 不调用用户代码, 不决定 retry 行为。它只把签名钉在代码层, 避免 PR β 或 γ1.5 分别发明不同 validator 入口。测试同时检查 spec 文档和 code constant, 见 [test_gamma0_contract_tdd.py](/home/sevenx/coding/agent-harness/packages/graph-agent/tests/core/test_gamma0_contract_tdd.py:203) 到 [test_gamma0_contract_tdd.py](/home/sevenx/coding/agent-harness/packages/graph-agent/tests/core/test_gamma0_contract_tdd.py:215)。

### 2.5 Middleware order contract (对应 γ0_3)

`DEFAULT_MIDDLEWARE_ORDER` 仍是当前已经实现的三类 runtime middleware: `ProtocolValidationMiddleware`, `CognitiveFlowMiddleware`, `ExecutionControlMiddleware`, 见 [middleware/__init__.py](/home/sevenx/coding/agent-harness/packages/graph-agent/src/graph_agent/middleware/__init__.py:49) 到 [middleware/__init__.py](/home/sevenx/coding/agent-harness/packages/graph-agent/src/graph_agent/middleware/__init__.py:53)。

γ0 新增 `MVP0_MIDDLEWARE_ORDER_CONTRACT`, 用字符串锁定 PR β 完整顺序: `ProtocolValidation`, `CognitiveFlow`, `ExecutionControl`, `Tracing`, `ToolError`, `LoopDetection`, 见 [middleware/__init__.py](/home/sevenx/coding/agent-harness/packages/graph-agent/src/graph_agent/middleware/__init__.py:55) 到 [middleware/__init__.py](/home/sevenx/coding/agent-harness/packages/graph-agent/src/graph_agent/middleware/__init__.py:62)。`DEFAULT_MIDDLEWARE_ORDER_CONTRACT` 是同一个契约的公开别名, 见 [middleware/__init__.py](/home/sevenx/coding/agent-harness/packages/graph-agent/src/graph_agent/middleware/__init__.py:64) 到 [middleware/__init__.py](/home/sevenx/coding/agent-harness/packages/graph-agent/src/graph_agent/middleware/__init__.py:65)。

这里没有创建不存在的 middleware class。原因很直接: runtime class 还没实现时, class tuple 里不能放空气; 但字符串顺序可以提前成为 PR β 的接口合同。测试检查完整字符串 contract, 并确保当前三项 class order 是 contract 前缀, 见 [test_gamma0_contract_tdd.py](/home/sevenx/coding/agent-harness/packages/graph-agent/tests/core/test_gamma0_contract_tdd.py:182) 到 [test_gamma0_contract_tdd.py](/home/sevenx/coding/agent-harness/packages/graph-agent/tests/core/test_gamma0_contract_tdd.py:200)。

## 3. Audit 闭环

Step 5 a2 audit 抓到 3 个偏移: 私有 `_DEFAULT_AGENT_EXIT_CONTRACT` 常量没有 spec 来源、runtime 仍有 legacy `exit_contract` 消费、`validator` 命名和旧 module path/callable 语义容易碰撞。a1 先验证事实, 再用 `3c48931` 收敛: 删掉 graph_assembler 私有兜底, 把默认文案放进 cognitive template; 给 AST `validator` 字段加语义注释; 不扩大到 runtime cleanup。a2 二审 PASS。

Step 6 a3 PM 替身 audit 抓到 7 项 doc/test 偏移: a2 改过的 skill-spec 文档未纳入 γ0, `05-agent-md-spec.md` 文件尾部有损坏字节和重复片段, `validator` 非 bool fatal 缺测试, ship gate 文案仍写错 loader grep 期望, subgraph validator 行错误码不准, design 文案把实现说成移出 allowed list。a1 用 `f67f1cf` 闭合, γ0 TDD 从 10 条变为 11 条。

Step 6 a3 audit 二轮又抓到 F8/F9: `06-cognitive-template-spec.md` 概览表仍引用已删 `[F-v3-agent-exit-contract-missing]`, `execution-runtime/mvp0-alignment.md` 仍写 `AgentNodeAST` 保留 `exit_contract`。a1 用 `8541f9a` 清掉残留, 并把 `AgentNodeAST` 退役与 `SkillNodeAST` legacy 保留分开写清。

## 4. Pre-existing 和非 γ0 Scope

`06-cognitive-template-spec.md` 仍有 7/8 插槽计数表述歧义, 例如 [06-cognitive-template-spec.md](/home/sevenx/coding/agent-harness/docs/engine/skill-spec/06-cognitive-template-spec.md:88) 与锚点命名不完全一致。这是 a3 标记的 pre-existing P2, 本 PR 不修, 避免 Step 6 变成全文重写。

部分 doc-ahead-of-impl 错误码仍存在, 例如 docs 里提到 `[F-v3-agent-body-tag-unknown]`, 但当前 loader 对 `<exit_contract>` 的实现是裸消息 `unknown top-level tag exit_contract`, 见 [loader.py](/home/sevenx/coding/agent-harness/packages/graph-agent/src/graph_agent/core/loader.py:1179) 到 [loader.py](/home/sevenx/coding/agent-harness/packages/graph-agent/src/graph_agent/core/loader.py:1184)。这是 compile-schema / error-code cleanup 后续工作, 不属于 γ0 contract patch。

Legacy `runtime/exit_contract.py`, `codemod/v21_migrator.py`, `SkillNodeAST.exit_contract` 也没有在 γ0 删除。原因是它们属于 PR γ3 V2.1 cleanup, 不是 PR β middleware 的前置阻塞项。

## 5. Ship Gate 终态

最终 γ0 TDD: `11 passed`, 包含 Agent 无 `<exit_contract>` 可加载、legacy `<exit_contract>` tag 对 Agent 被拒绝、Agent/Subgraph `validator` 默认 false 和 true parse、`validator: "maybe"` 非 bool fatal、middleware order contract、validator signature/error placeholder、docs/source smoke。

最终 graph-agent 全套 pytest: `956 passed, 3 skipped, 50 xfailed, 53 xpassed, 0 failed`。

最终 ruff: `All checks passed!`。

最终 mypy: `Success: no issues found in 119 source files`。

最终 doc grep: `grep -rn 'F-v3-agent-exit-contract-missing' docs/engine/` 为 0 命中。`execution-runtime/mvp0-alignment.md` 的 `exit_contract` 命中已不再写 Agent 保留字段; Agent 退役、Skill legacy 保留、系统默认字符串三件事分别落在 [mvp0-alignment.md](/home/sevenx/coding/agent-harness/docs/engine/execution-runtime/mvp0-alignment.md:93)、[mvp0-alignment.md](/home/sevenx/coding/agent-harness/docs/engine/execution-runtime/mvp0-alignment.md:94)、[mvp0-alignment.md](/home/sevenx/coding/agent-harness/docs/engine/execution-runtime/mvp0-alignment.md:298)。

## 6. 后续建议

下一步建议先派 a2 做 honesty audit, 然后派 a3 做 PM-proxy audit 复审。原因是本报告是 Step 7 ship report, 不是实现 commit; 需要用同一套审计链确认 report 是否如实覆盖 PR γ0 的 code、test、docs 和已知残留。

PR γ0 ship 后, 后续工程顺序应进入 PR β middleware。round-11 目录已经出现在工作区, 但本报告没有读取或修改它; 等 γ0 report 审过后, 再由 a1 主笔 PR β tasks.md, 对齐本 PR 已锁定的 `MVP0_MIDDLEWARE_ORDER_CONTRACT`。
