---
spec: engine-mvp0-rebuild-v030/round-10-PR-gamma0-contract-patch
phase: PR γ0 (契约补丁, PR α 后 PR β 前)
owner: a1 主笔 tasks.md / a2 主笔 3 文档 / 主控复核
工程量: 14h (1.75d) + audit/e2e/CI buffer 1.25d
依赖: PR α (Gateway + llm-roles Phase 1) 已 push (#91 待 review/merge)
后续: PR β (middleware 34h) → γ1 (compile-schema 50h) → γ1.5 (preflight 38h) → γ2 (state-io 40h) → γ3 (cleanup 44h)
---

# PR γ0: Contract Patch Requirements

## §1 与 MVP0 R1-R12 的映射关系
γ0 是快速的契约补丁，承接并预执行了以下 MVP0 需求的部分子集：
- **R4 (部分)**: 完全剥离了 Agent AST (`AgentNodeAST`) 对 `exit_contract` 的强依赖，为后续编译解除了强制 XML 标签约束。注意：γ0 不动 legacy `SkillNodeAST` path。

## §2 PR γ0 独有需求 [NEW]
- **R[NEW]-γ0-01 (Validator AST)**: `AgentNodeAST` 与 `SubgraphNodeAST` 必须原生支持 `validator: bool = False` 字段的解析与验证。
- **R[NEW]-γ0-02 (Validator 签名契约)**: 锁定统一签名 `def validate(output: dict, state_slice: dict, **kwargs) -> None | dict` 和 3 个 placeholder 错误码，不实施 runtime 处理。
- **R[NEW]-γ0-03 (Middleware 顺序契约)**: 锁定严格加载顺序：`ProtocolValidation → CognitiveFlow → ExecutionControl → Tracing → ToolError → LoopDetection`。

## §3 验收标准 (Acceptance Criteria)

### 3.1 功能验收 (Functional)
1. 编译一个在 `SKILL.md` 的 body XML 中故意删除了 `<exit_contract>` 标签的 Agent Phase，断言引擎不再抛出 `[F-v3-agent-exit-contract-missing]` 的 fatal 错误，且能够成功生成 AST。
2. 在 `SKILL.md` 和 `SUBGRAPH.md` 的 Frontmatter 中显式写入 `validator: true`，断言经过 `manifest.py` 校验后，对应的 `AgentNodeAST` 和 `SubgraphNodeAST` 对象中的 `validator` 属性被正确置为 `True`。

### 3.2 架构测试验收 (Testing)
1. 新增架构测试或常量断言：验证中间件执行顺序常量的准确定义。

### 3.3 代码规范与 CI
1. 删除 `exit_contract` 后，必须保证相关的 MyPy 静态类型检查不报遗漏字段错误。
2. Pydantic 的 `extra="forbid"` 配置不抛出关于 `validator` 为未知字段的异常。
3. PR 提交时，所有依赖旧 AST `AgentNodeAST.exit_contract` 字段的测试夹具（fixtures）必须一并剔除。

### 3.4 Ship Gate (要全过才能 ship γ0)
- ruff check packages/graph-agent: clean
- mypy packages/graph-agent: 0 errors
- pytest packages/graph-agent/tests/{models,core,middleware}: 100% pass
- grep -r exit_contract packages/graph-agent/src/: 仅命中 `SkillNodeAST` legacy path (不命中 AgentNodeAST / loader)
- grep -r DEFAULT_MIDDLEWARE_ORDER packages/graph-agent/src/middleware/: 命中新 6 string constant 定义

### 3.5 Out of Scope (γ0 不做, 留给后续 PR)
- middleware runtime 实施 → PR β
- validator runtime 处理 → PR β
- 错误码具体 code (现在只锁 placeholder) → PR β/γ1.5
- legacy SkillNodeAST.exit_contract → PR γ3 cleanup