---
spec: engine-mvp0-rebuild-v030/round-10-PR-gamma0-contract-patch
phase: PR γ0 (契约补丁, PR α 后 PR β 前)
owner: a1 主笔 tasks.md / a2 主笔 3 文档 / 主控复核
工程量: 14h (1.75d) + audit/e2e/CI buffer 1.25d
依赖: PR α (Gateway + llm-roles Phase 1) 已 push (#91 待 review/merge)
后续: PR β (middleware 34h) → γ1 (compile-schema 50h) → γ1.5 (preflight 38h) → γ2 (state-io 40h) → γ3 (cleanup 44h)
---

# PR γ0: Contract Patch Design

## §0.5 继承字段表 (round 9 / PR α 完成后现状, γ0 默认不动)

### `packages/graph-agent/src/graph_agent/core/manifest.py`

| 字段 | 现状 (round 9) | round 10/γ0 状态 |
|---|---|---|
| `LogicNodeAST.mode` (139:Literal) | 不改 | 不改 (default no-touch) |
| `LogicNodeAST.python_callable` (140) | 不改 | 不改 |
| `SubgraphNodeAST.mode/sub_skill_ref/target_skill/io` (146-152) | 不改 | 不改 |
| `SubgraphNodeAST.validator` | **N/A** | `[NEW] validator: bool = False` |
| `AgentNodeAST.role/goal/steps/protocols/io/tools/subagents/subgraphs/references/examples/max_iterations/llm_role/system_prompt` (155-172) | 不改 | 不改 |
| `AgentNodeAST.exit_contract` (~158) | `str = Field(min_length=1)` | **[BREAKING remove]** |
| `AgentNodeAST.validator` | **N/A** | `[NEW] validator: bool = False` |
| `SkillNodeAST.exit_contract` (190-195) | legacy path | **不改 (γ0 不动 legacy path)** |

### `packages/graph-agent/src/graph_agent/core/loader.py`

| Hook | 现状 file:line | round 10/γ0 状态 |
|---|---|---|
| shared `extract_raw_blocks` allowed tags (1091-1098) | 包含 `exit_contract` | **保留给 legacy `SkillNodeAST` 共用解析; Agent path 另设 substring reject guard** |
| `_parse_agent_body` required tag (1179-1185) | `exit_contract` fatal-required | **[BREAKING] 移除** |
| `_parse_agent_body` return dict (1186-1192) | 写入 `exit_contract` | **[BREAKING] 移除该 key** |
| legacy `SkillNodeAST` else path | — | **不改 (γ0 不动)** |

### `packages/graph-agent/src/graph_agent/middleware/__init__.py`

| 字段 | 现状 (round 9) | round 10/γ0 状态 |
|---|---|---|
| `DEFAULT_MIDDLEWARE_ORDER` (51-55) | 3 class tuple: `ProtocolValidation/CognitiveFlow/ExecutionControl` | **[NEW] 6 string contract constants + 默认顺序** |

## §1 R4 Agent AST/Loader `exit_contract` Removal
- **AST 调整**: `packages/graph-agent/src/graph_agent/core/manifest.py` 中的 `AgentNodeAST` 的 `exit_contract: str = Field(min_length=1)` **[BREAKING]** 修改为彻底删除该字段。**γ0 不动 legacy `SkillNodeAST` path**: `manifest.py:190-195` 的 `SkillNodeAST.exit_contract` 留给 PR γ3 cleanup, 防止 scope creep。
- **Loader 调整**: `packages/graph-agent/src/graph_agent/core/loader.py` 中：
  - Agent path 不再消费 `<exit_contract>` 提取结果。
  - 移除 `if not exit_contract: _fatal(...)` 的强制阻断逻辑。
  - 保留 legacy `SkillNodeAST` 共用 allowed 列表, 在 Agent 分支用 substring guard 显式拒绝 `<exit_contract>`。

## §2 AST `validator` 字段与统一签名
- **AST 新增字段**: 在 `manifest.py` 的 `AgentNodeAST` 与 `SubgraphNodeAST` 模型中 **[NEW]** 增加 `validator: bool = False`。
- **统一函数签名**: 明确后续业务中需要动态加载的 `validator.py` 必须遵守以下签名（通过内部协议文档或 stub 注释固化）：
  ```python
  def validate(output: dict, state_slice: dict, **kwargs) -> None | dict:
      pass
  ```
- **Error Code Placeholders**: 在 `exceptions.py` (或统一的 error enum 文件) 中，**[NEW]** 预先定义 3 个后续使用的错误码占位符：
  - `[F-v3-logic-validator-failed]`
  - `[F-v3-agent-validator-failed]`
  - `[F-v3-subgraph-validator-failed]`
- **统一 validator 失败语义**:
  - γ0 锁定 validator 签名: `def validate(output: dict, state_slice: dict, **kwargs) -> None | dict`
  - γ0 锁定 3 个 placeholder 错误码 (具体 code 留 PR β/γ1.5 决定)
  - γ0 不实施 runtime 处理 (留 PR β middleware)
  - γ0 不要求抛 `GraphAgentValidationError` 类异常 (那是 runtime 行为, 留 PR β)

## §3 Middleware Order 契约 (Docs & Constants)
在 `graph_agent` 的中间件配置模块中（例如 `middleware/__init__.py:51-55`），显式声明 Middleware 的执行顺序，固化为 6 个字符串常量的契约数组：
`ProtocolValidation → CognitiveFlow → ExecutionControl → Tracing → ToolError → LoopDetection`

## §4 边界划分 (不属于 PR γ0)
- ❌ **Middleware 实施 (PR β)**: γ0 只通过常量锁定 middleware 顺序，**不实施** 任何中间件改写逻辑或 `factory.py` 接入逻辑。
- ❌ **Compile Schema (PR γ1)**: 不处理 `GRAPH.md` body XML 回归。
- ❌ **Preflight / Predict (PR γ1.5)**: 不编写校验阻断的具体运行态代码。
- ❌ **State-IO / Cleanup (PR γ2 / γ3)**: 不处理状态降维。legacy `SkillNodeAST.exit_contract` → PR γ3 cleanup。
