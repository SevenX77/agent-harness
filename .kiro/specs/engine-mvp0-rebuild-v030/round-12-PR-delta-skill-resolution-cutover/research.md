---
spec: engine-mvp0-rebuild-v030/round-12-PR-delta-skill-resolution-cutover
phase: PR δ (skill-resolution hard cutover)
owner: a2 主笔 / a1 audit
---

# PR δ: Skill Resolution Hard Cutover Research

## §0 继承字段表 (Round 9/10/11 不动)
- **ModelResolverProtocol**: 签名及职责不动。
- **Agent AST**: `exit_contract` 移除不动，业务 `validator` 开关语意不动，中间件顺序不动。
- **CognitiveFlowMiddleware**: 接管 `finish_task` / `ask_clarification` 职责不动。

## §1 现有代码占地考古

### 1.1 `SkillResolverProtocol` 与桥接函数现状
- **位置**: `packages/graph-agent/src/graph_agent/core/skill_resolver_protocol.py`
- **核心契约**: `class SkillResolverProtocol(Protocol)` (L32) 定义了 `resolve_skill(self, skill_id: str) -> str | Path` (L35)。
- **错误定义**: `SkillResolutionError` (L18) 已继承自 `SkillLoadError` 并提供了结构化的报错方式。
- **桥接函数**: `resolve_skill_root(resolver: SkillResolverProtocol, skill_id: str)` (L50) 作为 helper 被 `loader.py:382` 等处调用，用于实际触发解析并校验目录合法性。

### 1.2 `SubagentSpec.path` 用法与 AST 现状
- **定义**: `packages/graph-agent/src/graph_agent/core/manifest.py` 中 `SubagentSpec` (L97) 仍然支持 legacy 的 `path` 字段 (L104)。
- **影响**: 这导致了目前的 AST 依然允许开发者通过旧有的文件系统相对路径进行引用，未强制迁移到 registry 模式。

### 1.3 `_resolve_subagent_root` 调用链
- **位置**: `packages/graph-agent/src/graph_agent/core/loader.py:488` `def _resolve_subagent_root(...)` 仍然 active。
- **触发点**: `loader.py` 在解析 `doc.ast.subagents` 时，如果 `target_skill` 为空，会直接退回到这个 fallback 函数去计算本地的相对路径。此外，当前入口层即使不传 `skill_resolver`，由于这里有 fallback，也能在路径寻址时勉强工作，这是本轮硬切换必须砍掉的尾巴。

### 1.4 测试 Fixtures 的现存 V2.1 形态盘点
- **Subagent Fixtures**: 现存在 `packages/graph-agent/tests/fixtures/subagent_minimal/` 等测试数据中，使用旧的相对路径嵌套结构，未平铺。
- **入口可选性**:
  - `compiler.py` 的 `compile_skill` (L41) 中 `skill_resolver` 参数在 L46 仍是 Optional。
  - `runner.py` 的 `run_skill` (L162) 中 `skill_resolver` 参数在 L173 仍是 Optional。这使得旧测试可以在不提供 resolver 的情况下静默运行。