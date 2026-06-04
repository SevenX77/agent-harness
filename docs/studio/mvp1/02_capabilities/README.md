# 02_capabilities — 能力维 (维度 ②)

> 治理规则见 [../INDEX.md](../INDEX.md)。本 tier 拥有**跨组件的数据流/行为**, **只链接 region 不重述组件**(见 INDEX §2 不变量)。文档模板见 INDEX §7 capability 模板。
> **状态**: MVP1 baseline + alignment 已落为文件夹制。每个能力文件夹含 `baseline.md` 与 `mvp1-alignment.md`。

## 计划文档 (14)

| 文档 | 状态 | 迁移来源 |
|---|---|---|
| [`skill-workspace/`](./skill-workspace/mvp1-alignment.md) | baseline + alignment | 旧 workspace-fs(前端) + system-layout(路由); IDE 模型(无注册表, 子图按 path) |
| [`graph-authoring/`](./graph-authoring/mvp1-alignment.md) | baseline + alignment | 旧 canvas-topology(流程) |
| [`phase-editing/`](./phase-editing/mvp1-alignment.md) | baseline + alignment | 旧 asset-explorer(表单); 进阶字段待补 |
| [`file-editing/`](./file-editing/mvp1-alignment.md) | baseline + alignment | 旧 asset-explorer(编辑器) |
| [`compile-lint/`](./compile-lint/mvp1-alignment.md) | baseline + alignment | 旧 skill-lifecycle(compile) |
| [`predict/`](./predict/mvp1-alignment.md) | baseline + alignment | 旧 skill-lifecycle(predict); 多处未挂载 |
| [`run-execution/`](./run-execution/mvp1-alignment.md) | baseline + alignment | 旧 skill-lifecycle(run) + state-engine(流) |
| [`trace-observability/`](./trace-observability/mvp1-alignment.md) | baseline + alignment | 旧 trace-inspector |
| [`golden-eval/`](./golden-eval/mvp1-alignment.md) | baseline + alignment | 旧 ux-workflow; judge 无主 |
| [`debug-resume/`](./debug-resume/mvp1-alignment.md) | baseline + alignment | 全孤儿, 新建 |
| [`conflict-overwrite/`](./conflict-overwrite/mvp1-alignment.md) | baseline + alignment | 旧 skill-lifecycle + canvas-topology(并) |
| [`copilot-assist/`](./copilot-assist/mvp1-alignment.md) | 已有 baseline + alignment | 旧 copilot-chat(流程) |
| [`publish/`](./publish/mvp1-alignment.md) | baseline + alignment | 无主, 新建(发布最小占坑) |
| [`studio-settings/`](./studio-settings/mvp1-alignment.md) | baseline + alignment | 无主, 新建(settings 旅程配套) |
