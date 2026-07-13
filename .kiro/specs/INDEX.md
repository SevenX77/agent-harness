# .kiro/specs/ — Active Specifications Index

本目录是当前活跃 (in-flight) 的架构演进施工单。已完结 / 已废弃 spec 物理归档到 [`_archive/`](./_archive/)。

## Active (Draft / Implementing)

| Spec | 状态 | 主题 | Level 3 关联 |
|---|---|---|---|
| [`studio-feature-canvas-topology/`](./studio-feature-canvas-topology/) | Draft (P0) | **画布唯一主文档(全部 canvas 功能)**:纵向布局 · 黑板可视化连线+i/o panel · 拖拽改拓扑 · 三层下钻 · 运行态展开/Nudge · 空画布快捷 · 统一 Rust 文件管线(写校验解耦)。吸收并取代 ↓ canvas-authoring-v1 + canvas-micro-topology-v1 | [`docs/studio/02_features/canvas-topology/baseline.md`](../../docs/studio/02_features/canvas-topology/baseline.md) |
| [`canvas-micro-topology-v1/`](./canvas-micro-topology-v1/) | **Superseded → studio-feature-canvas-topology** | 运行态微观展开/Nudge/Payload schema 已吸收入主文档(REQ-11..14),待物理归档到 `_archive/` | [`docs/studio/02_features/canvas-topology/mvp0-alignment.md`](../../docs/studio/02_features/canvas-topology/mvp0-alignment.md) |
| [`canvas-authoring-v1/`](./canvas-authoring-v1/) | **Superseded → studio-feature-canvas-topology** | 编辑态(连线反写/新建节点/属性编辑)已实现并吸收入主文档(REQ-3/9/10,需迁 Rust),待物理归档到 `_archive/` | [`docs/studio/02_features/canvas-topology/mvp0-alignment.md`](../../docs/studio/02_features/canvas-topology/mvp0-alignment.md) |
| [`studio-feature-trace-inspector/`](./studio-feature-trace-inspector/) | Draft (P1) | **运行追踪唯一权威 spec(完全去黑盒)**:Trace Panel 实时+回看 · 节点过滤/检索 · 边 dot→真实 state 黑板→编辑器查看 · Prompt 透视 · PropertiesPanel 净化。由 ↓ trace-and-predict-visibility 改名合并 | [`docs/studio/02_features/trace-inspector/baseline.md`](../../docs/studio/02_features/trace-inspector/baseline.md) |
| [`trace-and-predict-visibility/`](./trace-and-predict-visibility/) | **Superseded → studio-feature-trace-inspector** | 旧名;内容已合并入 trace-inspector,待物理归档到 `_archive/` | [`docs/studio/02_features/trace-inspector/baseline.md`](../../docs/studio/02_features/trace-inspector/baseline.md) |
| [`studio-api-keys-redesign/`](./studio-api-keys-redesign/) | Superseded (UX only) | API Keys Round 2/3 UX 参考；v2 生产契约见 `llm-provider-intelligence-v2` | [`docs/graph-agent-gateway/mvp0/baseline.md`](../../docs/graph-agent-gateway/mvp0/baseline.md) |
| [`studio-api-keys-regression-hardening/`](./studio-api-keys-regression-hardening/) | Implementing | API Keys 回归收敛：先恢复删除前前端状态，再接 v2 API | [`docs/development/FRONTEND_UI_SPEC.md`](../../docs/development/FRONTEND_UI_SPEC.md) |
| [`studio-gateway-runtime-schema-boundary/`](./studio-gateway-runtime-schema-boundary/) | Draft | Gateway runtime schema 去 UI 字段；Studio 后端拥有 display projection | [`docs/graph-agent-gateway/mvp0/baseline.md`](../../docs/graph-agent-gateway/mvp0/baseline.md) |
| [`graph-agent-gateway-mvp1/`](./graph-agent-gateway-mvp1/) | Implementing | Graph-Agent-Gateway MVP1 workstreams；当前 WS-2 base_url 保存时归一化交 Gemini 实施、Codex 复审 | [`docs/graph-agent-gateway/mvp1/README.md`](../../docs/graph-agent-gateway/mvp1/README.md) |
| [`studio-llm-platform-control-plane-runtime/`](./studio-llm-platform-control-plane-runtime/) | Implementing | LLM Platform v2.0：Control Plane / Gateway Runtime Plane / 多客户接入 | [`apps/studio/backend/docs/llm-registry/LLM_PLATFORM_CONTROL_PLANE_RUNTIME_V1.md`](../../apps/studio/backend/docs/llm-registry/LLM_PLATFORM_CONTROL_PLANE_RUNTIME_V1.md) |
| [`studio-llm-gateway-redesign/`](./studio-llm-gateway-redesign/) | Draft (Review-ready) | LLM Gateway 回归修复切片：save 解耦 · resolver 解析期跳过 · 测试状态 SSOT 回写 · 远端就绪形状（platform-control-plane-runtime 的近期子集，见 `architecture-direction.md`） | [`docs/studio/03_platform/llm-gateway/baseline.md`](../../docs/studio/03_platform/llm-gateway/baseline.md) |
| [`studio-llm-remote-draft-catalog/`](./studio-llm-remote-draft-catalog/) | Draft | LLM draft/evidence 远端 GitHub catalog：route_id 稳定性 · remote-first sync · sanitized PR writeback · historical_ready 蓝态收口 | [`docs/graph-agent-gateway/mvp1/08-orch-test-status-ssot/mvp1-alignment.md`](../../docs/graph-agent-gateway/mvp1/08-orch-test-status-ssot/mvp1-alignment.md) |
| [`community-probe-catalog-service-phase2a/`](./community-probe-catalog-service-phase2a/) | Implemented (Phase 2a) | 社区探测目录服务 Phase 2a 免费档(三方审核定稿,已实现):客户端脱敏+白名单丢弃 opt-in 上传(`/catalog/contribute`)· manifest/分片签名校验同步到 disposable cache(`/catalog/sync-verified`)· serverless 门卫(不持写仓 token)+ 定时发布 Action(唯一写仓,最小 `contents:write`)落在 `services/community-catalog-gate/`(独立 node --test,默认休眠不改 MVP1)。`studio-llm-remote-draft-catalog` 的二期后续 | [`docs/development/COMMUNITY_PROBE_CATALOG_SERVICE_DESIGN.md`](../../docs/development/COMMUNITY_PROBE_CATALOG_SERVICE_DESIGN.md) |
| [`studio-llm-roles-frontend-cutover/`](./studio-llm-roles-frontend-cutover/) | Draft | LLM Roles 前端按 6 个可回滚 PR 接入 Model Groups DTO | [`docs/development/FRONTEND_UI_SPEC.md`](../../docs/development/FRONTEND_UI_SPEC.md) |
| [`studio-llm-copilot-reconciliation/`](./studio-llm-copilot-reconciliation/) | Draft (P0) | API Key 参数/端点双层校验 + Roles 全局状态回写 + Copilot SDK 专属工具测试 | [`docs/development/FRONTEND_UI_SPEC.md`](../../docs/development/FRONTEND_UI_SPEC.md) |
| [`studio-llm-endpoint-connectivity-and-status-projection/`](./studio-llm-endpoint-connectivity-and-status-projection/) | Draft (requirements+research+已确认 design) | endpoint 测试=只测连通性 · **状态投影归一**(单一持久化 ui_state,删前端文本匹配) · 没模型不猜 notable(untested+⚠,不判 failed) · invalid_key⇒disabled · 探测全链路日志 · 手动探测扇出全 endpoint(含 failed) · ark 多协议 · provider id tooltip+索引澄清。上游 `studio-llm-credentials-catalog-ssot` | [`docs/development/FRONTEND_UI_SPEC.md`](../../docs/development/FRONTEND_UI_SPEC.md) |
| [`studio-frontend-v21-multifile-editor/`](./studio-frontend-v21-multifile-editor/) | Draft | Studio v3 多文件 skill 编辑架构 (VS Code 风格) | [`docs/studio/system-level/workspace-file-system/baseline.md`](../../docs/studio/system-level/workspace-file-system/baseline.md) |
| [`studio-feature-skill-lifecycle/`](./studio-feature-skill-lifecycle/) | Draft (Review-ready) | 测试输入管理(原生选路径→Python 读入)+ 批量运行(序列自动批量)。已收敛去过度设计:S1 哈希冲突移出(DEF-011)、文件转换工具移交引擎(DEF-012)。建议改名 `test-inputs-batch` | [`docs/studio/02_features/skill-lifecycle/baseline.md`](../../docs/studio/02_features/skill-lifecycle/baseline.md) |
| [`studio-moirai-agent-system/`](./studio-moirai-agent-system/) | Implemented (2026-07-11 tasks 1–4 全勾;资产层 ah 编队交付+跨泳道锚定审计,backend/tauri/前端卡片单 agent 收尾;4.3 人工验收待 PM) | **MoirAI 代理人体系(四层资产单源,双路装载)**:角色/手册/知识库/技能四层收拢 `app/prompts/` 随包 · MoirAI 从"分诊台"改代理人闭环(理解→research→计划→执行→择机派遣) · 知识库索引+13 篇主题文档取代开发仓 docs 挂载(打包版不再缺知识) · SDK 面板=MoirAI 化身+原生 AgentDefinition 派三女神 · 工具边界代码强制(读声明式放开/写白名单经 PreToolUse hook/Bash 审批;超时停任务保会话) · 新增 predict_skill MCP 补齐 compile→predict 诊断链 · lib.rs 人格/技能常量全退役改运行时物化。PM 2026-07-07 两轮指令定向;取代 ah-orchestration-design §9.8。**v4 复审修订(research §T6)**:spike 实测 SDK subagent 仅薄基座(基座+delta 前提四运行位差异化,手册须自足)· ah 1.4.0 对齐(cli.md 收缩纯 delta,`ah status` 条目作废)· R10 变更卡一键撤销+注入风险记账 · 指纹全资产覆盖 | [`docs/studio/mvp1/03_regions/copilot/ah-orchestration-design.md`](../../docs/studio/mvp1/03_regions/copilot/ah-orchestration-design.md) |
| [`studio-open-in-binary-provenance/`](./studio-open-in-binary-provenance/) | Draft (research+design 完成) | **Open in Codex/Claude 二进制来源守卫**:Windows Codex 的 WSL 集成劫持 `~/.local/bin/codex` 指向 `/mnt/*` PE → interop 当 Windows 进程执行 → ah 环境变量级沙盒被整体穿透(2026-07-06 实证)。修复:master cmd 拒 `/mnt/*` + codex standalone 稳定路径优先 + 安装脚本自愈 + 设计矩阵补「二进制必须本 OS 原生」铁律 | [`docs/studio/mvp1/03_regions/copilot/ah-orchestration-design.md`](../../docs/studio/mvp1/03_regions/copilot/ah-orchestration-design.md) |
| [`studio-runtime-import-intent-model/`](./studio-runtime-import-intent-model/) | Implemented (2026-07-13 backend三态契约落地; 前端三态渲染另单) | Runtime import 三态意图模型: candidate manifest / active bindings / removed tombstone; refresh reconcile 不复活 removed; v1 import 槽 no-backward-compat regenerate; engine 只消费 active。遗留/跨项: 前端配置树按 candidate/active/removed 三态渲染与交互另单。 | [`docs/studio/mvp1/03_regions/input/mvp1-alignment.md`](../../docs/studio/mvp1/03_regions/input/mvp1-alignment.md) |



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
