---
spec: engine-mvp0-rebuild-v030/round-12-PR-delta-skill-resolution-cutover
phase: PR δ (skill-resolution hard cutover)
owner: a2 主笔 / a1 audit
---

# PR δ: Skill Resolution Hard Cutover Requirements

## §0 继承字段表 (Round 9/10/11 不动)
- **ModelResolverProtocol**: 签名及职责不动。
- **Agent AST**: `exit_contract` 移除不动，业务 `validator` 开关语意不动，中间件顺序不动。
- **CognitiveFlowMiddleware**: 接管 `finish_task` / `ask_clarification` 职责不动。

## §1 业务诉求 (PM 视角)
- **按 `skill_id` 纯逻辑寻址**: 彻底摒弃由于历史原因遗留的“根据物理目录的相对路径”来加载子 Agent (subagent) 和 SUBGRAPH 的方式。引擎只需也只能通过全局唯一的 `skill_id` 来加载任何相关的 Skill。这使得上层 (Studio) 可以灵活地从数据库或远程注册表中提供 Skill 实体，不再强求本地目录树的刚性嵌套。
- **显式 Resolver 依赖与 Fast-fail**: 整个引擎执行链路（编译图、组装图、执行图、Studio 后端调用侧）将强制要求传入 Skill 解析器。若未提供且触发了解析动作，系统必须立刻抛出结构化错误（Fast-fail），绝不允许退回到隐式或默认的路径寻找逻辑。
- **Subagent 注册表化**: 开发者定义子 Agent 时，仅需要指定其目标 `target_skill`。系统会在启动前确保所有的子 Agent 均存在于当前的注册表中，提升配置的严谨性与健壮性。

## §2 User-facing 行为变更
- Studio 后端调用 Engine API 时，如果没有显式挂载实现了相应协议的 `skill_resolver`，并且触发了 Subagent 加载或 SUBGRAPH 执行，将立即遭遇致命错误，流程终止。本次 Cutover 会同步升级 Studio Backend。
- 开发者编写图文件或配置 Subagent 时，原有的基于相对文件路径的方法失效，只能声明 `target_skill: <skill_id>`。
- 运行中出现找不到 Skill 的情况时，返回的不再是标准的文件 `FileNotFoundError`，而是专门的 `SkillResolutionError` 附带详细的失败原因码。

## §3 验收标准 (Ship Gate)
按 SOP-05 Cutover Discipline 执行验收：
- **Grep Guard**: 源码中无 `SubagentSpec.path` 残留。
- **Grep Guard**: 源码中无 `_resolve_subagent_root` 残留。
- **Grep Guard**: 测试 Fixture 中无 `subagents\[.*\].path` (或等效的 YAML/JSON 路径配置) 残留。
- SUBGRAPH `target_skill` 最小 Compile/Runtime Smoke 测试通过。
- Studio Backend Resolver 注入 Smoke 测试通过。