---
spec: engine-mvp0-rebuild-v030/round-12-PR-delta-skill-resolution-cutover
phase: PR δ (skill-resolution hard cutover)
owner: a2 主笔 / a1 audit
---

# PR δ: Skill Resolution Hard Cutover Design

## §0 继承字段表 (Round 9/10/11 不动)
- **ModelResolverProtocol**: 签名及职责不动。
- **Agent AST**: `exit_contract` 移除不动，业务 `validator` 开关语意不动，中间件顺序不动。
- **CognitiveFlowMiddleware**: 接管 `finish_task` / `ask_clarification` 职责不动。

## §1 字段表与变更清单

| 字段/实体 | 现状态 | 目标状态 | 标记 | 迁移路径 (SOP-06) |
|---|---|---|---|---|
| `SubagentSpec.path` | `str \| None` (L104) | 已移除 | **[BREAKING]** | 删除此字段，使用 `target_skill` 替代。旧包含此字段的文档将引发 Compile 错误。 |
| `SubagentSpec.target_skill` | `str \| None` | `str` | **[BREAKING]** | 将此字段设为必填。AST 校验时确保有值。 |
| `SubgraphNodeAST.sub_skill_ref` | `str \| None` (L150) | 已移除 | **[BREAKING]** | 本轮退役，完全移除。改用 registry 寻址。 |
| `SubgraphNodeAST.target_skill` | `str \| None` (L151) | `str` | **[BREAKING]** | 移除 Optional 变必填。 |
| `_resolve_subagent_root` | `Callable` (L488) | 完全删除 | **[BREAKING]** | `loader.py` 及引用侧全部删除此私有函数。 |
| `resolve_skill_root` 桥接行为 | `Callable` (L50) | 保持存在 | **[MODIFIED]** | 调用的前提将是必填的 `skill_resolver`。不再容忍传入 None。 |
| 统一错误码 `[F-v3-resolver-missing]` | 缺失/不统一 | 新增/规范化 | **[NEW]** | 若入口或核心 API `skill_resolver` 缺失，引发含此 Code 的 Exception。 |

## §2 API 形态

### 2.1 引擎核心入口签名强制注入
所有核心入口将 `skill_resolver: SkillResolverProtocol | None = None` 全部改为 **`skill_resolver: SkillResolverProtocol,`**（强制必填，无默认值）。
需迁移的全量清单：
- `packages/graph-agent/src/graph_agent/core/compiler.py:41` `compile_skill`
- `packages/graph-agent/src/graph_agent/core/runner.py:162` `run_skill` (L173), L243 (第二入口), L471 (第三入口)
- `packages/graph-agent/src/graph_agent/core/graph_assembler.py:69` `assemble_graph`
- `packages/graph-agent/src/graph_agent/core/loader.py:145-149` `SkillLoader.compile_skill`
- `packages/graph-agent/src/graph_agent/core/loader.py:251` 处的 inline `assemble_graph(compile_skill(root), ...)` 必须同步透传 resolver。
- **Studio Backend**：采用**同 PR 迁移方案**。`apps/studio/backend/app/services/` 下所有相关调用需同步注入 Backend 实现的 resolver 适配器。

### 2.2 错误码清单标准化与源码漂移修正
- 将源码中的 `[F-v3-invalid-skill-id]` **修正为 `[F-v3-resolver-skill-id-invalid]`**，以严格对齐 `10-skill-resolver-protocol-spec.md` 规范，不固化当前偏差。
- 确认注册/使用的错误码：
  - `[F-v3-resolver-missing]`: 引擎入口或图装配缺少必须的 `skill_resolver`。
  - `[F-v3-resolver-skill-id-invalid]`: `skill_id` 正则验证不通过。
  - `[F-v3-skill-not-registered]`: 内部查找失败（Miss）。
  - `[F-v3-resolver-path-invalid]`: 返回了非法路径。

### 2.3 决策记录：Studio Backend 与 SUBGRAPH Scope
**1. Studio Backend 迁移策略 (MF-2)**
决定采用**方案 A (引擎 + Studio backend 同 PR cutover)**。基于 Engine MVP0 原子切换原则，入口签名变为强制要求 `skill_resolver`，为了保证主线不挂，必须在同一 PR 中完成 Studio 消费侧的注入升级。

**2. SUBGRAPH Cutover 与 γ2 关系分工 (MF-4 & MF-6)**
本次 PR δ 包含 SUBGRAPH `target_skill` 的最小 Compile 与 Runtime Smoke，与后续的 γ2 (State/IO Isolation) 形成明确分工：
- **PR δ 职责 (打地基)**：仅负责 Resolver 寻址闭环。确保 `SubgraphNodeAST` 退役 `sub_skill_ref` 并要求 `target_skill`；将 runtime 的 `_resolve_sub_skill_path` (`graph_assembler.py:198`) 改写为通过 `skill_resolver` 解析。此部分工时为 **SUBGRAPH Smoke ~12h**。
- **γ2 职责 (隔离执行)**：负责子图执行期的 State IO 隔离、黑板上下文隔离等复杂状态机变更。PR δ 不碰状态隔离。
- **核心寻址与单测迁移** (Resolver-only): **~24h**（含 Studio 侧入口变更）。总预估 ~36h。

### 2.4 测试 Fixture Pattern 的重构
原有的 `tests/fixtures/subagent_minimal/` 中所有的按相对路径嵌套的形态必须平铺至 `tests/fixtures/v030_skill_registry/`，测试代码统一依赖 `InMemorySkillResolver`。