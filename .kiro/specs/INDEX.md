# .kiro/specs/ — Active Specifications Index

本目录是当前活跃 (in-flight) 的架构演进施工单。已完结 / 已废弃 spec 物理归档到 [`_archive/`](./_archive/)。

## Active (Draft / Implementing / Shipped-but-not-frozen)

| Spec | 状态 | 主题 | Level 3 关联 |
|---|---|---|---|
| [`studio-api-keys-redesign/`](./studio-api-keys-redesign/) | Implementing | API Keys 多 provider 配置 + 测试 + redesign Round 2/3 | [`docs/engine/LLM_ROUTING_AND_FALLBACK.md`](../../docs/engine/LLM_ROUTING_AND_FALLBACK.md) |
| [`studio-frontend-v21-multifile-editor/`](./studio-frontend-v21-multifile-editor/) | Draft | V2.1 多文件 skill 编辑架构 (VS Code 风格) | [`docs/studio/WORKSPACE_FILE_MANAGEMENT.md`](../../docs/studio/WORKSPACE_FILE_MANAGEMENT.md) |
| [`studio-uikit-redesign/`](./studio-uikit-redesign/) | Shipped | UI 设计 token + skillnode 规范 (3 份核心规范保留) | [`docs/development/FRONTEND_UI_SPEC.md`](../../docs/development/FRONTEND_UI_SPEC.md) |

## Archive (历史归档区)

[`_archive/`](./_archive/) 收容 23 个已完结或废弃的 spec 目录, 包括:

- V1 reset 阶段 6 个 MVP (mvp-0..mvp-5)
- 老版 deprecated copilot / api-keys
- 老版 studio MVP1 / canvas-v1 / frontend-v2 / llm-config-v2 / tunnel-safety
- Tauri t2 / t3 历史方案
- Engine 优化方向 (graph-agent-optimizations / graph-agent-studio / graph-agent-v2.1-subagent / predict-v2 / harness-split)

完整去向记录见提交 `chore(docs): archive 151 legacy md files (baseline cleanup batch 1/3)`.

## 命名规范

新 spec 目录名:
- 全小写, 短横线分隔
- 主题前缀: `studio-*` / `engine-*` / `harness-*` / `tauri-*`
- 完成后保留在本目录直至 PM 决定归档 (避免历史断层)

每个 spec 子目录至少含: `design.md` / `requirements.md` / `research.md` / `tasks.md`. 复杂 spec 可加 `round*-design.md` / `pm-pending-questions.md` 等扩展。
