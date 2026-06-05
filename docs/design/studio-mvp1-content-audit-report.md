# Studio MVP1 内容审计报告（R0-R3 专审）

范围：只审 `docs/studio/mvp1/` 内容轨 R0/R1/R2/R3 与 Q2/Q3；不复审结构项。R2 已按当前工作区代码符号核验，代码证据以当前未提交工作区为准。

判定权威：最新内容以 `docs/studio/mvp1/01_workflows/`、`docs/studio/_reorg/workflow-action-catalog.md`、`docs/studio/_reorg/alignment-notes.md`、`docs/studio/mvp1/01_workflows/00_settings-ux-spec.md` 为准；engine-owned contract 以 `docs/engine/mvp1/` 为准。

## 全局 1. 内容矛盾清单（按严重度）

- [major] Provider 状态在同一 workflow 内同时写成 6 态和 5 态，且保留已取消的 `needs_setup`。证据：`docs/studio/mvp1/01_workflows/00_settings.md:38`、`:50` 写 6 态；`:75-81` 又写五个 UI state 与 `needs_setup`。正确值：`ready / historical_ready / untested / failed(reason) / cooling_down / off`，取消 `needs_setup`。权威：`docs/studio/mvp1/01_workflows/00_settings-ux-spec.md:261-285`、`:467-486`。当前代码仍是旧 5 态：`apps/studio/backend/app/services/llm_state_projection.py:ProviderUiState`、`apps/studio/frontend/src/api/llm.ts:ProviderUiState`。
- [major] Publish 口径冲突：Settings 把 General 的 Gitea 主机写成 MVP1 Publish 前提，但 06_eval 已裁定 publish 是 Artifact Registry zip 上传，非 git push。证据：`docs/studio/mvp1/01_workflows/00_settings.md:32`、`:97`；正确权威：`docs/studio/mvp1/01_workflows/06_eval.md:6`、`:18`、`:25-26`、`:34`。
- [major] Golden diff / 摘要归属冲突：workflow 仍把 run 后字段级 diff 放在 `properties`，而最新 region 决策说 golden 完全不在 Properties，入口归 I/O output + Assets，详细 diff 在 editor。证据：`docs/studio/mvp1/01_workflows/04_run-and-verify.md:128`；正确权威：`docs/studio/mvp1/03_regions/properties/mvp1-alignment.md:44-53`、`docs/studio/mvp1/03_regions/input/mvp1-alignment.md:54-56`、`:72-73`。残余冲突：`docs/studio/mvp1/03_regions/editor/mvp1-alignment.md:63` 仍说 Properties 留字段级摘要。
- [major] Golden 批量入口冲突：旧说法要求 `sonner` 批量开 N chat；更新后的 copilot-assist 决策改为 Copilot 输入框上方分析 bar（sonner -> 弹窗）。证据：旧口径 `docs/studio/mvp1/01_workflows/04_run-and-verify.md:124`、`:137`，`docs/studio/mvp1/02_capabilities/golden-eval/mvp1-alignment.md:38-40`，`docs/studio/mvp1/03_regions/timeline/mvp1-alignment.md:53-55`；正确权威：`docs/studio/mvp1/02_capabilities/copilot-assist/mvp1-alignment.md:77-82`、`:100-101`。
- [major] i18n 对当前后端中文残留少报：文档说后端只剩 6 处中文，但当前 Studio backend 还有 Copilot 系统提示、事件错误、工具错误、配置警告等多处中文。证据：`docs/studio/mvp1/04_platform/i18n.md:41`、`:64`、`:83`、`:97`；实际代码：`apps/studio/backend/app/services/copilot.py:BASE_SYSTEM_PROMPT_TEMPLATE`、`apps/studio/backend/app/services/copilot.py:_translate_sdk_message`、`apps/studio/backend/app/services/copilot.py:_error_event_for_exception`、`apps/studio/backend/app/models/skills.py:ConfigMismatchWarning`。
- [minor] Local History 同一文档内既说 RunDetail/BatchSummary 还需 PM 确认，又在“已决”里写明只归 Timeline。证据：`docs/studio/mvp1/03_regions/local-history/mvp1-alignment.md:34-45`。正确值：Local History 只做 git snapshot；RunDetailDrawer / BatchSummary 归 Timeline / I/O。
- [minor] DESIGN_UNITS_INDEX 自身 evidence/source 口径有错：`golden-per-agent-node` 的源 workflow 写 `06_eval`，但 06_eval 明说 golden 不在该节点；`settings-six-state-provider-health` 的 drift evidence 写 `00_settings.md:4`，实际 5 态在 `00_settings.md:75-80`。证据：`docs/studio/mvp1/DESIGN_UNITS_INDEX.md:26`、`:39`；正确源：`docs/studio/mvp1/01_workflows/04_run-and-verify.md:118-137`、`docs/studio/mvp1/01_workflows/00_settings.md:75-80`。

## 全局 2. Stale 决策清单

- [major] `needs_setup` / 5 态被 `00_settings-ux-spec` 6 态裁定推翻。被推翻处：`docs/studio/mvp1/01_workflows/00_settings.md:75-81`。推翻证据：`docs/studio/mvp1/01_workflows/00_settings-ux-spec.md:261-285`。
- [major] Golden in Properties 被 PM 2026-06-04 的 I/O + Assets + Editor 分工推翻。被推翻处：`docs/studio/mvp1/01_workflows/04_run-and-verify.md:128`、`docs/studio/mvp1/02_capabilities/golden-eval/mvp1-alignment.md:61`、`docs/studio/mvp1/03_regions/editor/mvp1-alignment.md:63`。推翻证据：`docs/studio/mvp1/03_regions/properties/mvp1-alignment.md:44-53`。
- [major] `sonner` 批量开 chat 被 Copilot 分析 bar 推翻。被推翻处：`docs/studio/mvp1/01_workflows/04_run-and-verify.md:124`、`:137`，`docs/studio/mvp1/02_capabilities/golden-eval/mvp1-alignment.md:38-40`，`docs/studio/mvp1/03_regions/timeline/mvp1-alignment.md:53-55`，`docs/studio/mvp1/03_regions/copilot/mvp1-alignment.md:54-56`。推翻证据：`docs/studio/mvp1/02_capabilities/copilot-assist/mvp1-alignment.md:77-82`、`:100-101`。
- [major] `.kiro/specs`、旧 `docs/engine/mvp0/skill-spec`、`_reorg/*prompt*` 作为 SSOT 被最新权威顺序推翻。被推翻处见“权威泄漏”清单。正确值：studio 只引用最新 workflow / alignment / ux-spec；engine contract 只引用 `docs/engine/mvp1/`。
- [minor] 子图只写“local path”的口径已被 engine mvp1 的“绝对 `path`”裁定收紧。被推翻处：`phase-editing`、`skill-workspace`、`assets`、`canvas` alignment。推翻证据：`docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md:37-45`、`docs/engine/mvp1/02-mechanism/02-resolver/mvp1-alignment.md:18-25`、`:45`。

## 全局 3. 跨模块 drift（对照 DESIGN_UNITS_INDEX）

- [major] `settings-six-state-provider-health`：`00_settings.md` 保留 5 态 / `needs_setup`，但 `studio-settings`、`settings` region、`gateway` baseline/alignment 以及 UX spec 都以 6 态为目标。证据：`docs/studio/mvp1/DESIGN_UNITS_INDEX.md:39`、`docs/studio/mvp1/01_workflows/00_settings.md:75-81`、`docs/studio/mvp1/02_capabilities/studio-settings/mvp1-alignment.md:56-59`、`docs/studio/mvp1/03_regions/settings/mvp1-alignment.md:63-66`。
- [major] `golden-per-agent-node`：workflow / golden-eval / timeline / copilot 仍保留 Properties 或 sonner 旧入口；input / properties / copilot-assist 已更新为 I/O + Assets + editor diff + Copilot analysis bar。证据：`docs/studio/mvp1/DESIGN_UNITS_INDEX.md:26`、`docs/studio/mvp1/01_workflows/04_run-and-verify.md:124-128`、`docs/studio/mvp1/03_regions/properties/mvp1-alignment.md:44-53`、`docs/studio/mvp1/02_capabilities/copilot-assist/mvp1-alignment.md:77-82`。
- [major] `subgraph-path-inline-drilldown`：engine contract 要绝对 `path`；多个 studio alignment 仍写泛化的 local path，代码基线仍是旧 `mode: subgraph` / `target_skill`。证据：`docs/studio/mvp1/DESIGN_UNITS_INDEX.md:21`、`apps/studio/frontend/src/components/GraphCanvas/canvas-authoring.ts:defaultPhaseMarkdown`、`apps/studio/frontend/src/components/studio/panels/AssetsPanel.tsx:AssetsPanel`、`docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md:37-45`。
- [major] `publish-artifact-autocommit`：INDEX 与 06_eval/publish 能力说 publish != git push；00_settings 仍把 Publish 说成推 Gitea。证据：`docs/studio/mvp1/DESIGN_UNITS_INDEX.md:37`、`docs/studio/mvp1/01_workflows/00_settings.md:32`、`:97`、`docs/studio/mvp1/01_workflows/06_eval.md:6`、`:34`。
- [minor] `local-history-snapshot`：local-history alignment 同时留“PM confirmation needed”和“已决只做 git 快照”。证据：`docs/studio/mvp1/DESIGN_UNITS_INDEX.md:38`、`docs/studio/mvp1/03_regions/local-history/mvp1-alignment.md:34-45`。

## 全局 4. 权威泄漏（R1/R6）

- [major] `.kiro/specs` 被写成设计来源/设计权威：`docs/studio/mvp1/README.md:4`、`docs/studio/mvp1/01_workflows/00_settings.md:4`、`docs/studio/mvp1/01_workflows/02_authoring.md:5`。
- [major] 旧 engine mvp0 FROZEN 被写成字段/格式 SSOT：`docs/studio/mvp1/01_workflows/02_authoring.md:5`、`:11`。正确值：`docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md:15-16` 明确旧 mvp0 spec 不得作为 SSOT。
- [major] `_reorg/*prompt*` 被写成引擎需求落点：`docs/studio/mvp1/01_workflows/03_compile.md:44`、`docs/studio/mvp1/01_workflows/04_run-and-verify.md:145-147`、`docs/studio/mvp1/01_workflows/05_debugging.md:39`、`docs/studio/mvp1/01_workflows/INDEX.md:18`。正确值：engine-owned contract 应引用 `docs/engine/mvp1/`。
- [minor] 非全屏 sidecar gate 的部分 region/platform 文档引用 `docs/studio/INDEX.md` 作为来源，而最新权威已在 `_reorg/alignment-notes.md` D10 收口。证据：`docs/studio/mvp1/03_regions/shell-layout/mvp1-alignment.md:22`、`docs/studio/mvp1/04_platform/native-fs/mvp1-alignment.md:56`、`docs/studio/mvp1/04_platform/state-engine/mvp1-alignment.md:55`；正确权威：`docs/studio/_reorg/alignment-notes.md:70-95`。

## 逐档审计

### docs/studio/mvp1/README.md
- R0: 无
- R1: [major] 把 `.kiro/specs/studio-feature-*` 写成设计来源，违反“`.kiro/specs` 仅过去参考，不作 SSOT”。证据：`docs/studio/mvp1/README.md:4`。
- R2: 无
- R3: 无
- Q2/Q3: 无

### docs/studio/mvp1/DESIGN_UNITS_INDEX.md
- R0: [minor] `settings-six-state-provider-health` 把 drift evidence 写成 `00_settings.md:4`，但实际 5 态 / `needs_setup` 在 `00_settings.md:75-80`；`:4` 是设计源行。证据：`docs/studio/mvp1/DESIGN_UNITS_INDEX.md:39`、`docs/studio/mvp1/01_workflows/00_settings.md:75-80`。
- R1: 无
- R2: 无
- R3: 无
- Q2/Q3: [minor] `golden-per-agent-node` 的源 workflow 写 `06_eval`，但 `06_eval` 自己声明 golden 不在本节点；正确源应是 `04_run-and-verify` 的 golden-eval 段。证据：`docs/studio/mvp1/DESIGN_UNITS_INDEX.md:26`、`docs/studio/mvp1/01_workflows/06_eval.md:11`、`docs/studio/mvp1/01_workflows/04_run-and-verify.md:118-137`。

### docs/studio/mvp1/01_workflows/00_settings-ux-spec.md
- R0: 无
- R1: 无
- R2: 无
- R3: 无
- Q2/Q3: 无
- 结论: 无内容 finding

### docs/studio/mvp1/01_workflows/00_settings.md
- R0: [major] 文内先写 6 态，后又写五个 UI state，并保留已取消的 `needs_setup`。证据：`docs/studio/mvp1/01_workflows/00_settings.md:38`、`:50`、`:75-81`。正确值：`ready / historical_ready / untested / failed(reason) / cooling_down / off`，取消 `needs_setup`，见 `docs/studio/mvp1/01_workflows/00_settings-ux-spec.md:261-285`。
- R1: [major] 把 `.kiro/specs/studio-*` 写成设计源。证据：`docs/studio/mvp1/01_workflows/00_settings.md:4`。
- R2: 无（该文档的 5 态段与当前代码一致，但它是 stale 目标口径，不是 baseline 错写；当前代码证据：`apps/studio/backend/app/services/llm_state_projection.py:ProviderUiState`、`apps/studio/frontend/src/api/llm.ts:ProviderUiState`。）
- R3: [major] Publish 仍写 Gitea 推送前提，被 06_eval “Artifact Registry zip 上传，非 git push”推翻。证据：`docs/studio/mvp1/01_workflows/00_settings.md:32`、`:97`；正确权威：`docs/studio/mvp1/01_workflows/06_eval.md:6`、`:18`、`:34`。
- Q2/Q3: [major] `settings-six-state-provider-health` 与 `publish-artifact-autocommit` 两个单元跨模块口径不一致。证据：`docs/studio/mvp1/DESIGN_UNITS_INDEX.md:37`、`:39`。

### docs/studio/mvp1/01_workflows/01_init.md
- R0: 无
- R1: 无
- R2: 无
- R3: 无
- Q2/Q3: 无
- 结论: 无内容 finding

### docs/studio/mvp1/01_workflows/02_authoring.md
- R0: [minor] 下游链接指向不存在的 `./03_run-and-verify.md`，实际文件是 `04_run-and-verify.md`。证据：`docs/studio/mvp1/01_workflows/02_authoring.md:48`。
- R1: [major] 把 `.kiro/specs/studio-feature-canvas-topology` 与旧 `docs/engine/mvp0/skill-spec` 写成设计权威 / 字段格式权威。证据：`docs/studio/mvp1/01_workflows/02_authoring.md:5`、`:11`；正确权威：`docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md:15-16`。
- R2: 无（其列出的 `defaultPhaseMarkdown`、`phase-frontmatter`、`PropertiesPanel` 等 stale-code 与当前代码一致：`apps/studio/frontend/src/components/GraphCanvas/canvas-authoring.ts:defaultPhaseMarkdown`、`apps/studio/frontend/src/components/studio/panels/AssetsPanel.tsx:AssetsPanel`。）
- R3: [minor] 子图 path 方向只写“path”，未吸收 2026-06-05 engine mvp1 对“绝对 path”的收紧；该文主要由 R1 旧 FROZEN 污染。证据：`docs/studio/mvp1/01_workflows/02_authoring.md:37-38`；正确权威：`docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md:37-45`。
- Q2/Q3: 无

### docs/studio/mvp1/01_workflows/03_compile.md
- R0: 无
- R1: [major] “引擎需求”仍指向 `_reorg/engine-prompt-trace-compile-debug.md`，engine-owned contract 应以 `docs/engine/mvp1/` 为准。证据：`docs/studio/mvp1/01_workflows/03_compile.md:44`。
- R2: 无
- R3: 无
- Q2/Q3: 无

### docs/studio/mvp1/01_workflows/04_run-and-verify.md
- R0: [major] Golden 字段级 diff 区域写 `properties`，与 Properties/I/O/editor 最新分工冲突。证据：`docs/studio/mvp1/01_workflows/04_run-and-verify.md:128`；正确权威：`docs/studio/mvp1/03_regions/properties/mvp1-alignment.md:44-53`、`docs/studio/mvp1/03_regions/input/mvp1-alignment.md:54-56`。
- R1: [major] 引擎需求仍指向 `_reorg/*prompt*`。证据：`docs/studio/mvp1/01_workflows/04_run-and-verify.md:145-147`。
- R2: 无
- R3: [major] Golden 批量入口仍写 `sonner` 批量开 N chat，被 copilot-assist 的分析 bar 决策推翻。证据：`docs/studio/mvp1/01_workflows/04_run-and-verify.md:124`、`:137`；正确权威：`docs/studio/mvp1/02_capabilities/copilot-assist/mvp1-alignment.md:77-82`。
- Q2/Q3: [major] `golden-per-agent-node` 在 workflow、golden-eval、timeline、copilot、input/properties/editor 之间归属不一致。证据：`docs/studio/mvp1/DESIGN_UNITS_INDEX.md:26`。

### docs/studio/mvp1/01_workflows/05_debugging.md
- R0: 无
- R1: [major] “引擎需求”仍指向 `_reorg/engine-prompt-trace-compile-debug.md`，checkpoint/resume contract 应引用 `docs/engine/mvp1/`。证据：`docs/studio/mvp1/01_workflows/05_debugging.md:39`；正确权威示例：`docs/engine/mvp1/00-architecture-overview.md:92-95`。
- R2: 无
- R3: 无
- Q2/Q3: 无

### docs/studio/mvp1/01_workflows/06_eval.md
- R0: 无
- R1: 无
- R2: 无
- R3: 无
- Q2/Q3: 无
- 结论: 无内容 finding

### docs/studio/mvp1/01_workflows/INDEX.md
- R0: 无
- R1: [major] 走查状态把 engine 设计需求指向 `_reorg/engine-prompt-*` 与 `gemini-prompt-batch-loop`。证据：`docs/studio/mvp1/01_workflows/INDEX.md:18`。
- R2: 无
- R3: 无
- Q2/Q3: 无

### docs/studio/mvp1/02_capabilities/README.md
- R0: 无
- R1: 无
- R2: 无
- R3: 无
- Q2/Q3: 无
- 结论: 无内容 finding

### docs/studio/mvp1/02_capabilities/compile-lint/baseline.md
- R0: 无
- R1: 无
- R2: 无（已核 `Workspace.tsx`、`useDebouncedLint.ts`、`skills.py` 相关符号，baseline 对当前代码现状成立。）
- R3: 无
- Q2/Q3: 无
- 结论: 无内容 finding

### docs/studio/mvp1/02_capabilities/compile-lint/mvp1-alignment.md
- R0: 无
- R1: 无
- R2: 无
- R3: 无
- Q2/Q3: 无
- 结论: 无内容 finding

### docs/studio/mvp1/02_capabilities/conflict-overwrite/baseline.md
- R0: 无
- R1: 无
- R2: 无（已核 `canvas-authoring.ts:handleSaveConflict` 与相关保存流程，baseline 对当前代码现状成立。）
- R3: 无
- Q2/Q3: 无
- 结论: 无内容 finding

### docs/studio/mvp1/02_capabilities/conflict-overwrite/mvp1-alignment.md
- R0: 无
- R1: 无
- R2: 无
- R3: 无
- Q2/Q3: 无
- 结论: 无内容 finding

### docs/studio/mvp1/02_capabilities/copilot-assist/baseline.md
- R0: 无
- R1: 无
- R2: 无（已核 `apps/studio/backend/app/services/copilot.py:build_options`、`stream_query`、`_translate_sdk_message`、`_resolve_copilot_runtime`；baseline 对当前 SDK 直写 / ThinkingBlock 缺失现状成立。）
- R3: 无
- Q2/Q3: 无
- 结论: 无内容 finding

### docs/studio/mvp1/02_capabilities/copilot-assist/mvp1-alignment.md
- R0: 无
- R1: 无
- R2: 无
- R3: 无（该文已把 golden 批量入口细化为 analysis bar，属于最新修正来源。）
- Q2/Q3: 无
- 结论: 无内容 finding

### docs/studio/mvp1/02_capabilities/debug-resume/baseline.md
- R0: 无
- R1: 无
- R2: 无（已核 `apps/studio/backend/app/routers/runs.py:resume_run` 为 501，baseline 对当前代码现状成立。）
- R3: 无
- Q2/Q3: 无
- 结论: 无内容 finding

### docs/studio/mvp1/02_capabilities/debug-resume/mvp1-alignment.md
- R0: 无
- R1: 无
- R2: 无
- R3: 无
- Q2/Q3: 无
- 结论: 无内容 finding

### docs/studio/mvp1/02_capabilities/file-editing/baseline.md
- R0: 无
- R1: 无
- R2: 无（已核 `writeSkillFile` / editor save 相关路径，baseline 对当前代码现状成立。）
- R3: 无
- Q2/Q3: 无
- 结论: 无内容 finding

### docs/studio/mvp1/02_capabilities/file-editing/mvp1-alignment.md
- R0: 无
- R1: 无
- R2: 无
- R3: 无
- Q2/Q3: 无
- 结论: 无内容 finding

### docs/studio/mvp1/02_capabilities/golden-eval/baseline.md
- R0: 无
- R1: 无
- R2: 无（已核 `apps/studio/backend/app/services/golden_diff.py:set_golden_baseline_for_run`、`compare_run_to_golden`、`apps/studio/frontend/src/hooks/useGoldenDiff.ts:compare`，baseline 对当前代码现状成立。）
- R3: 无
- Q2/Q3: 无
- 结论: 无内容 finding

### docs/studio/mvp1/02_capabilities/golden-eval/mvp1-alignment.md
- R0: 无
- R1: 无
- R2: 无
- R3: [major] F3 仍写 trace + sonner 两入口都必需，被 copilot-assist F7 分析 bar（sonner -> 弹窗）推翻。证据：`docs/studio/mvp1/02_capabilities/golden-eval/mvp1-alignment.md:38-40`；正确权威：`docs/studio/mvp1/02_capabilities/copilot-assist/mvp1-alignment.md:77-82`、`:100-101`。
- Q2/Q3: [major] F5 归属仍列 `properties`，与 Properties 最新“golden 完全不在 Properties”冲突。证据：`docs/studio/mvp1/02_capabilities/golden-eval/mvp1-alignment.md:61`；正确权威：`docs/studio/mvp1/03_regions/properties/mvp1-alignment.md:44-53`。

### docs/studio/mvp1/02_capabilities/graph-authoring/baseline.md
- R0: 无
- R1: 无
- R2: 无（已核 `apps/studio/frontend/src/components/GraphCanvas/canvas-authoring.ts:defaultPhaseMarkdown` 仍写旧 `mode` / `target_skill`，baseline 对当前代码现状成立。）
- R3: 无
- Q2/Q3: 无
- 结论: 无内容 finding

### docs/studio/mvp1/02_capabilities/graph-authoring/mvp1-alignment.md
- R0: 无
- R1: 无
- R2: 无
- R3: 无（该文已明确子图 frontmatter 写绝对 `path`，与 engine mvp1 对齐。）
- Q2/Q3: 无
- 结论: 无内容 finding

### docs/studio/mvp1/02_capabilities/phase-editing/baseline.md
- R0: 无
- R1: 无
- R2: 无（已核 `phase-frontmatter.ts:parsePhaseForm` 与 `PropertiesPanel` 旧字段，baseline 对当前代码现状成立。）
- R3: 无
- Q2/Q3: 无
- 结论: 无内容 finding

### docs/studio/mvp1/02_capabilities/phase-editing/mvp1-alignment.md
- R0: 无
- R1: 无
- R2: 无
- R3: [minor] F4 写 “local path reference”，未吸收 engine mvp1 “绝对 `path`”要求。证据：`docs/studio/mvp1/02_capabilities/phase-editing/mvp1-alignment.md:47-50`；正确权威：`docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md:37-45`。
- Q2/Q3: [minor] 与 `graph-authoring` 的“绝对 path”说法不一致。证据：`docs/studio/mvp1/02_capabilities/graph-authoring/mvp1-alignment.md:46`。

### docs/studio/mvp1/02_capabilities/predict/baseline.md
- R0: 无
- R1: 无
- R2: 无（已核 `Workspace.tsx:onPredict` 当前仍为桩 / 未接 `postPredictRun`，baseline 对当前代码现状成立。）
- R3: 无
- Q2/Q3: 无
- 结论: 无内容 finding

### docs/studio/mvp1/02_capabilities/predict/mvp1-alignment.md
- R0: 无
- R1: 无
- R2: 无
- R3: 无
- Q2/Q3: 无
- 结论: 无内容 finding

### docs/studio/mvp1/02_capabilities/publish/baseline.md
- R0: 无
- R1: 无
- R2: 无（已核 `artifact_registry.py:build_publish_package`、`skills.py:publish_skill` 相关 zip 发布路径，baseline 对当前代码现状成立。）
- R3: 无
- Q2/Q3: 无
- 结论: 无内容 finding

### docs/studio/mvp1/02_capabilities/publish/mvp1-alignment.md
- R0: 无
- R1: 无
- R2: 无
- R3: 无（该文与 06_eval 的 Artifact Registry / 非 git push 口径一致。）
- Q2/Q3: 无
- 结论: 无内容 finding

### docs/studio/mvp1/02_capabilities/run-execution/baseline.md
- R0: 无
- R1: 无
- R2: 无（已核 `run_manager.py`、`Workspace.tsx:onRun` 当前现状，baseline 对当前代码现状成立。）
- R3: 无
- Q2/Q3: 无
- 结论: 无内容 finding

### docs/studio/mvp1/02_capabilities/run-execution/mvp1-alignment.md
- R0: 无
- R1: 无
- R2: 无
- R3: 无
- Q2/Q3: 无
- 结论: 无内容 finding

### docs/studio/mvp1/02_capabilities/skill-workspace/baseline.md
- R0: 无
- R1: 无
- R2: 无（已核 `apps/studio/backend/app/services/skills.py:import_existing` / `list_skill_summaries` 仍保留注册表聚合和根文档门禁，baseline 对当前代码现状成立。）
- R3: 无
- Q2/Q3: 无
- 结论: 无内容 finding

### docs/studio/mvp1/02_capabilities/skill-workspace/mvp1-alignment.md
- R0: 无
- R1: 无
- R2: 无
- R3: [minor] F4 写 “resolve by local path”，未说明绝对 `path`；engine mvp1 已要求绝对路径。证据：`docs/studio/mvp1/02_capabilities/skill-workspace/mvp1-alignment.md:44-49`；正确权威：`docs/engine/mvp1/01-contract/01-physical-layout/mvp1-alignment.md:31-33`、`:45`。
- Q2/Q3: [minor] 与 `graph-authoring` 的“绝对 path”说法不一致。证据：`docs/studio/mvp1/02_capabilities/graph-authoring/mvp1-alignment.md:46`。

### docs/studio/mvp1/02_capabilities/studio-settings/baseline.md
- R0: 无
- R1: 无
- R2: 无（已核 `apps/studio/backend/app/services/llm_state_projection.py:ProviderUiState`、`apps/studio/frontend/src/api/llm.ts:ProviderUiState`、`LlmRolesTab.tsx:roleTestStates`，baseline 对当前代码现状成立。）
- R3: 无
- Q2/Q3: 无
- 结论: 无内容 finding

### docs/studio/mvp1/02_capabilities/studio-settings/mvp1-alignment.md
- R0: 无
- R1: 无
- R2: 无
- R3: 无
- Q2/Q3: 无
- 结论: 无内容 finding

### docs/studio/mvp1/02_capabilities/trace-observability/baseline.md
- R0: 无
- R1: 无
- R2: 无（已核 `ContextEdge.tsx:getMockEdgeContext`、`PropertiesPanel` selected-edge JSON，baseline 对当前代码现状成立。）
- R3: 无
- Q2/Q3: 无
- 结论: 无内容 finding

### docs/studio/mvp1/02_capabilities/trace-observability/mvp1-alignment.md
- R0: 无
- R1: 无
- R2: 无
- R3: 无
- Q2/Q3: 无
- 结论: 无内容 finding

### docs/studio/mvp1/03_regions/README.md
- R0: 无
- R1: 无
- R2: 无
- R3: 无
- Q2/Q3: 无
- 结论: 无内容 finding

### docs/studio/mvp1/03_regions/assets/baseline.md
- R0: 无
- R1: 无
- R2: 无（已核 `apps/studio/frontend/src/components/studio/panels/AssetsPanel.tsx:AssetsPanel` 仍读旧 `mode` / `target_skill` / `sub_skill_ref`，baseline 对当前代码现状成立。）
- R3: 无
- Q2/Q3: 无
- 结论: 无内容 finding

### docs/studio/mvp1/03_regions/assets/mvp1-alignment.md
- R0: 无
- R1: 无
- R2: 无
- R3: [minor] F2 写 “local subgraph path references”，未吸收 engine mvp1 “绝对 `path`”要求。证据：`docs/studio/mvp1/03_regions/assets/mvp1-alignment.md:25-30`；正确权威：`docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md:37-45`。
- Q2/Q3: [minor] 与 `graph-authoring` / engine 的绝对 path 口径不一致。证据：`docs/studio/mvp1/02_capabilities/graph-authoring/mvp1-alignment.md:46`。

### docs/studio/mvp1/03_regions/canvas/baseline.md
- R0: 无
- R1: 无
- R2: 无（已核 canvas selected/open/status/mock 相关符号，baseline 对当前代码现状成立。）
- R3: 无
- Q2/Q3: 无
- 结论: 无内容 finding

### docs/studio/mvp1/03_regions/canvas/mvp1-alignment.md
- R0: 无
- R1: 无
- R2: 无
- R3: [minor] F4 写 “child graph references are local paths”，未吸收 engine mvp1 “绝对 `path`”要求。证据：`docs/studio/mvp1/03_regions/canvas/mvp1-alignment.md:46-51`；正确权威：`docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md:37-45`。
- Q2/Q3: [minor] 与 `graph-authoring` / engine 的绝对 path 口径不一致。证据：`docs/studio/mvp1/02_capabilities/graph-authoring/mvp1-alignment.md:46`。

### docs/studio/mvp1/03_regions/center-action-bar/baseline.md
- R0: 无
- R1: 无
- R2: 无（已核 center action stage gate 当前状态，baseline 对当前代码现状成立。）
- R3: 无
- Q2/Q3: 无
- 结论: 无内容 finding

### docs/studio/mvp1/03_regions/center-action-bar/mvp1-alignment.md
- R0: 无
- R1: 无
- R2: 无
- R3: 无
- Q2/Q3: 无
- 结论: 无内容 finding

### docs/studio/mvp1/03_regions/copilot/baseline.md
- R0: 无
- R1: 无
- R2: 无（已核 `Workspace.tsx` 传入 CopilotPanel 的 skill id 风险、Copilot panel 当前状态，baseline 对当前代码现状成立。）
- R3: 无
- Q2/Q3: 无
- 结论: 无内容 finding

### docs/studio/mvp1/03_regions/copilot/mvp1-alignment.md
- R0: 无
- R1: 无
- R2: 无
- R3: [major] F5 仍写 golden creation 有 trace-local 与 batch copilot entries，被 copilot-assist 的 analysis bar 细化推翻。证据：`docs/studio/mvp1/03_regions/copilot/mvp1-alignment.md:52-58`；正确权威：`docs/studio/mvp1/02_capabilities/copilot-assist/mvp1-alignment.md:77-82`、`:100-101`。
- Q2/Q3: [major] 与 `golden-eval` / `timeline` / `copilot-assist` 对同一批量入口的说法不一致。证据：`docs/studio/mvp1/DESIGN_UNITS_INDEX.md:26`。

### docs/studio/mvp1/03_regions/editor/baseline.md
- R0: 无
- R1: 无
- R2: 无（已核 editor/file/trace 虚拟文档相关现状，baseline 对当前代码现状成立。）
- R3: 无
- Q2/Q3: 无
- 结论: 无内容 finding

### docs/studio/mvp1/03_regions/editor/mvp1-alignment.md
- R0: 无
- R1: 无
- R2: 无
- R3: [major] 已决里说 Properties 只留 golden 字段级摘要，但 Properties 最新已决是 golden 完全不在 Properties。证据：`docs/studio/mvp1/03_regions/editor/mvp1-alignment.md:63`；正确权威：`docs/studio/mvp1/03_regions/properties/mvp1-alignment.md:44-53`。
- Q2/Q3: [major] `golden-per-agent-node` 在 editor/properties/input 三个 region 的归属不一致。证据：`docs/studio/mvp1/DESIGN_UNITS_INDEX.md:26`。

### docs/studio/mvp1/03_regions/input/baseline.md
- R0: 无
- R1: 无
- R2: 无（已核 `InputPanel` 假文件 / schema inference 当前现状，baseline 对当前代码现状成立。）
- R3: 无
- Q2/Q3: 无
- 结论: 无内容 finding

### docs/studio/mvp1/03_regions/input/mvp1-alignment.md
- R0: 无
- R1: 无
- R2: 无
- R3: 无
- Q2/Q3: 无
- 结论: 无内容 finding

### docs/studio/mvp1/03_regions/local-history/baseline.md
- R0: 无
- R1: 无
- R2: 无（已核 History/Local History 当前 git snapshot 现状，baseline 对当前代码现状成立。）
- R3: 无
- Q2/Q3: 无
- 结论: 无内容 finding

### docs/studio/mvp1/03_regions/local-history/mvp1-alignment.md
- R0: [minor] F3 仍写 “PM confirmation needed”，同文后续“已决”已明确 Local History 只做 git 快照，RunDetailDrawer / BatchSummary 归 Timeline。证据：`docs/studio/mvp1/03_regions/local-history/mvp1-alignment.md:34-45`。
- R1: 无
- R2: 无
- R3: [minor] `Status: ownership gap` 已被该文 `已决(PM 2026-06-04)` 推翻。证据：`docs/studio/mvp1/03_regions/local-history/mvp1-alignment.md:40-45`。
- Q2/Q3: [minor] 与 `run-execution` / `timeline` 的运行时间语义归属不一致。证据：`docs/studio/mvp1/DESIGN_UNITS_INDEX.md:38`。

### docs/studio/mvp1/03_regions/properties/baseline.md
- R0: [minor] Current Region Ownership 仍写 “golden diff placement if PM keeps it here”，但 PM 已决 golden 完全不在 Properties；baseline 不应继续留下未决条件。证据：`docs/studio/mvp1/03_regions/properties/baseline.md:20-23`；正确权威：`docs/studio/mvp1/03_regions/properties/mvp1-alignment.md:44-53`。
- R1: 无
- R2: 无（已核 `PropertiesPanel.tsx` 当前无 golden UI，旧 phase form / edge JSON dump 现状成立。）
- R3: [minor] “if PM keeps it here” 已被 PM 2026-06-04 决策推翻。证据：`docs/studio/mvp1/03_regions/properties/mvp1-alignment.md:51-53`。
- Q2/Q3: [major] 与 `input` / `editor` 对 golden 归属冲突。证据：`docs/studio/mvp1/03_regions/input/mvp1-alignment.md:54-56`、`docs/studio/mvp1/03_regions/editor/mvp1-alignment.md:63`。

### docs/studio/mvp1/03_regions/properties/mvp1-alignment.md
- R0: 无
- R1: 无
- R2: 无
- R3: 无
- Q2/Q3: 无
- 结论: 无内容 finding

### docs/studio/mvp1/03_regions/settings/baseline.md
- R0: 无
- R1: 无
- R2: 无（已核 `apps/studio/frontend/src/api/llm.ts:ProviderUiState` 与 `apps/studio/backend/app/services/llm_state_projection.py:ProviderUiState`，baseline 对当前代码现状成立。）
- R3: 无
- Q2/Q3: 无
- 结论: 无内容 finding

### docs/studio/mvp1/03_regions/settings/mvp1-alignment.md
- R0: 无
- R1: 无
- R2: 无
- R3: 无
- Q2/Q3: 无
- 结论: 无内容 finding

### docs/studio/mvp1/03_regions/shell-layout/baseline.md
- R0: 无
- R1: 无
- R2: 无（已核 `apps/studio/frontend/src/App.tsx:App` 与 `apps/studio/frontend/src/components/RuntimeGate.tsx:RuntimeGate` 当前全屏 gate 现状，baseline 对当前代码现状成立。）
- R3: 无
- Q2/Q3: 无
- 结论: 无内容 finding

### docs/studio/mvp1/03_regions/shell-layout/mvp1-alignment.md
- R0: 无
- R1: [minor] F1 的 non-fullscreen sidecar gate 证据引用 `docs/studio/INDEX.md:221`，最新权威应引用 `_reorg/alignment-notes.md` D10 或 `00_settings.md`。证据：`docs/studio/mvp1/03_regions/shell-layout/mvp1-alignment.md:22`；正确权威：`docs/studio/_reorg/alignment-notes.md:70-95`。
- R2: 无
- R3: 无（决策本身仍对，只是证据来源 stale。）
- Q2/Q3: 无

### docs/studio/mvp1/03_regions/timeline/baseline.md
- R0: 无
- R1: 无
- R2: 无（已核 Timeline/TracePanel/useRunStream 当前 orphan 或未挂载状态，baseline 对当前代码现状成立。）
- R3: 无
- Q2/Q3: 无
- 结论: 无内容 finding

### docs/studio/mvp1/03_regions/timeline/mvp1-alignment.md
- R0: 无
- R1: 无
- R2: 无
- R3: [major] F5 仍写 golden prompts 有 trace-local 和 sonner batch entries，被 copilot-assist analysis bar 推翻。证据：`docs/studio/mvp1/03_regions/timeline/mvp1-alignment.md:51-58`；正确权威：`docs/studio/mvp1/02_capabilities/copilot-assist/mvp1-alignment.md:77-82`、`:100-101`。
- Q2/Q3: [major] 与 copilot-assist 对 `golden-per-agent-node` 的批量入口口径不一致。证据：`docs/studio/mvp1/DESIGN_UNITS_INDEX.md:26`。

### docs/studio/mvp1/03_regions/welcome/baseline.md
- R0: 无
- R1: 无
- R2: 无（已核 Welcome/Home 当前 open/create/recent 现状，baseline 对当前代码现状成立。）
- R3: 无
- Q2/Q3: 无
- 结论: 无内容 finding

### docs/studio/mvp1/03_regions/welcome/mvp1-alignment.md
- R0: 无
- R1: 无
- R2: 无
- R3: 无
- Q2/Q3: 无
- 结论: 无内容 finding

### docs/studio/mvp1/04_platform/README.md
- R0: 无
- R1: 无
- R2: 无
- R3: 无
- Q2/Q3: 无
- 结论: 无内容 finding

### docs/studio/mvp1/04_platform/engine/baseline.md
- R0: 无
- R1: 无
- R2: 无（已核 engine compile/lint/run/predict API current shape，baseline 对当前代码现状成立。）
- R3: 无
- Q2/Q3: 无
- 结论: 无内容 finding

### docs/studio/mvp1/04_platform/engine/mvp1-alignment.md
- R0: 无
- R1: 无
- R2: 无
- R3: 无
- Q2/Q3: 无
- 结论: 无内容 finding

### docs/studio/mvp1/04_platform/gateway/baseline.md
- R0: 无
- R1: 无
- R2: 无（已核 `llm_state_projection.py:ProviderUiState` 当前 5 态，baseline 对当前代码现状成立。）
- R3: 无
- Q2/Q3: 无
- 结论: 无内容 finding

### docs/studio/mvp1/04_platform/gateway/mvp1-alignment.md
- R0: 无
- R1: 无
- R2: 无
- R3: 无
- Q2/Q3: 无
- 结论: 无内容 finding

### docs/studio/mvp1/04_platform/i18n.md
- R0: [major] 文档说后端残留中文 6 处，但当前 Studio backend 还有 Copilot 系统提示、SDK 错误、工具错误、配置警告等多处中文，少报现状。证据：`docs/studio/mvp1/04_platform/i18n.md:41`、`:64`、`:83`、`:97`；实际代码：`apps/studio/backend/app/services/copilot.py:BASE_SYSTEM_PROMPT_TEMPLATE`、`apps/studio/backend/app/services/copilot.py:_translate_sdk_message`、`apps/studio/backend/app/services/copilot.py:_error_event_for_exception`、`apps/studio/backend/app/models/skills.py:ConfigMismatchWarning`。
- R1: 无
- R2: [major] 当前代码事实不符：`copilot.py` 中 `BASE_SYSTEM_PROMPT_TEMPLATE`、`build_system_prompt`、`stream_query`、`_translate_sdk_message`、`_resolve_copilot_runtime`、`_error_event_for_exception` 都含中文用户可见/模型可见文案，不在“6 处”清单内。证据：`apps/studio/backend/app/services/copilot.py:BASE_SYSTEM_PROMPT_TEMPLATE`、`apps/studio/backend/app/services/copilot.py:_translate_sdk_message`、`apps/studio/backend/app/services/copilot.py:_error_event_for_exception`。
- R3: 无
- Q2/Q3: 无

### docs/studio/mvp1/04_platform/llm-copilot-http-api/baseline.md
- R0: 无
- R1: 无
- R2: 无（已核 `routers/llm.py:_probe_copilot_sdk_tool_call` 走 `AsyncAnthropic`，而 `copilot.py:stream_query` 走 `ClaudeSDKClient`，baseline 对当前代码现状成立。）
- R3: 无
- Q2/Q3: 无
- 结论: 无内容 finding

### docs/studio/mvp1/04_platform/llm-copilot-http-api/mvp1-alignment.md
- R0: 无
- R1: 无
- R2: 无
- R3: 无
- Q2/Q3: 无
- 结论: 无内容 finding

### docs/studio/mvp1/04_platform/native-fs/baseline.md
- R0: 无
- R1: 无
- R2: 无（已核 `Workspace.tsx` / FastAPI file writes / Python zip packaging current state，baseline 对当前代码现状成立。）
- R3: 无
- Q2/Q3: 无
- 结论: 无内容 finding

### docs/studio/mvp1/04_platform/native-fs/mvp1-alignment.md
- R0: 无
- R1: [minor] F5 的 non-fullscreen sidecar gate 证据引用 `docs/studio/INDEX.md:221`，最新权威应引用 `_reorg/alignment-notes.md` D10。证据：`docs/studio/mvp1/04_platform/native-fs/mvp1-alignment.md:56`；正确权威：`docs/studio/_reorg/alignment-notes.md:70-95`。
- R2: 无
- R3: 无（决策本身仍对，只是证据来源 stale。）
- Q2/Q3: 无

### docs/studio/mvp1/04_platform/state-engine/baseline.md
- R0: 无
- R1: 无
- R2: 无（已核 RuntimeGate / state hooks / websocket bridge 当前现状，baseline 对当前代码现状成立。）
- R3: 无
- Q2/Q3: 无
- 结论: 无内容 finding

### docs/studio/mvp1/04_platform/state-engine/mvp1-alignment.md
- R0: 无
- R1: [minor] F5 的 non-fullscreen sidecar gate 证据引用 `docs/studio/INDEX.md:221`，最新权威应引用 `_reorg/alignment-notes.md` D10。证据：`docs/studio/mvp1/04_platform/state-engine/mvp1-alignment.md:55`；正确权威：`docs/studio/_reorg/alignment-notes.md:70-95`。
- R2: 无
- R3: 无（决策本身仍对，只是证据来源 stale。）
- Q2/Q3: 无
