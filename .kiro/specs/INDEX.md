# .kiro/specs/ — Active Specifications Index

本目录是当前活跃 (in-flight) 的架构演进施工单。已完结 / 已废弃 spec 物理归档到 [`_archive/`](./_archive/)。

## Active (Draft / Implementing)

| Spec | 状态 | 主题 | Level 3 关联 |
|---|---|---|---|
| [`canvas-micro-topology-v1/`](./canvas-micro-topology-v1/) | Draft (P0) | React Flow 画布微观拓扑展开 + 前后端嵌套 Payload schema | [`docs/studio/UX_WORKFLOW_BLUEPRINT.md`](../../docs/studio/UX_WORKFLOW_BLUEPRINT.md) + [`docs/engine/GRAPH_EXECUTION_MODEL.md`](../../docs/engine/GRAPH_EXECUTION_MODEL.md) |
| [`trace-and-predict-visibility/`](./trace-and-predict-visibility/) | Draft (P1) | Trace 瀑布流 + Prompt 透视仪 + Edge Inspection + Compile 结构化报错 | [`docs/studio/TRACE_AND_VISUALIZATION.md`](../../docs/studio/TRACE_AND_VISUALIZATION.md) |
| [`studio-api-keys-redesign/`](./studio-api-keys-redesign/) | Superseded (UX only) | API Keys Round 2/3 UX 参考；v4 生产契约见 `llm-provider-intelligence-v2` | [`docs/engine/LLM_ROUTING_AND_FALLBACK.md`](../../docs/engine/LLM_ROUTING_AND_FALLBACK.md) |
| [`studio-api-keys-regression-hardening/`](./studio-api-keys-regression-hardening/) | Implementing | API Keys 回归收敛：先恢复删除前前端状态，再接 v4 API | [`docs/development/FRONTEND_UI_SPEC.md`](../../docs/development/FRONTEND_UI_SPEC.md) |
| [`studio-gateway-runtime-schema-boundary/`](./studio-gateway-runtime-schema-boundary/) | Draft | Gateway runtime schema 去 UI 字段；Studio 后端拥有 display projection | [`docs/engine/LLM_ROUTING_AND_FALLBACK.md`](../../docs/engine/LLM_ROUTING_AND_FALLBACK.md) |
| [`studio-llm-roles-frontend-cutover/`](./studio-llm-roles-frontend-cutover/) | Draft | LLM Roles 前端按 6 个可回滚 PR 接入 Model Groups DTO | [`docs/development/FRONTEND_UI_SPEC.md`](../../docs/development/FRONTEND_UI_SPEC.md) |
| [`studio-frontend-v21-multifile-editor/`](./studio-frontend-v21-multifile-editor/) | Draft | V2.1 多文件 skill 编辑架构 (VS Code 风格) | [`docs/studio/WORKSPACE_FILE_MANAGEMENT.md`](../../docs/studio/WORKSPACE_FILE_MANAGEMENT.md) |

## Archive (历史归档区)

[`_archive/`](./_archive/) 收容 24 个已完结或废弃的 spec 目录, 包括:

- V1 reset 阶段 6 个 MVP (mvp-0..mvp-5)
- 老版 deprecated copilot / api-keys
- 老版 studio MVP1 / canvas-v1 / frontend-v2 / llm-config-v2 / tunnel-safety / uikit-redesign (5 份核心 token/skillnode/design 规范已提炼到 docs/development/FRONTEND_UI_SPEC.md)
- Tauri t2 / t3 历史方案
- Engine 优化方向 (graph-agent-optimizations / graph-agent-studio / graph-agent-v2.1-subagent / predict-v2 / harness-split)

完整去向记录见提交 `chore(docs): archive 151 legacy md files (baseline cleanup batch 1/3)`.

## 命名规范

新 spec 目录名:
- 全小写, 短横线分隔
- 主题前缀: `studio-*` / `engine-*` / `harness-*` / `tauri-*`
- 完成后保留在本目录直至 PM 决定归档 (避免历史断层)

每个 spec 子目录至少含: `requirement.md` / `research.md`. PM 解锁 implementation 阶段后才补 `design.md` / `tasks.md`. 复杂 spec 可加 `round*-design.md` / `pm-pending-questions.md` 等扩展。

## 阶段化 spec 文件约束 (2026-05-19 PM 设立)

- **Baseline 阶段 (现在)**: 只允许写 `requirement.md` + `research.md` (收敛 PM 真实需求 + 调研行业方案)
- **Implementation 阶段 (PM 解锁后)**: 再补 `design.md` (具体实现方案) + `tasks.md` (拆任务)
- 历史 archive spec 全部 4 文件齐全是因为它们在该规则前已完成
