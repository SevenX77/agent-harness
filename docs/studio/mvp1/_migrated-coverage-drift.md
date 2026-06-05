> 临时存档：retrofit 前各 baseline 的旧 Coverage/Drift。**待对应代码实现 + 验证无误后彻底删除。** 现行真相 = 各 baseline 的新结构（测试锚点 + ⚠️ drift 行）；本档仅迁移期安全网。

<a id="02-capabilities-compile-lint"></a>

## 02_capabilities/compile-lint

来源: [`baseline.md`](02_capabilities/compile-lint/baseline.md)

### 原 Current Coverage（迁移保留）
- live: 800ms lint, manual compile, compile-pass/fail stage, Predict gate from compile-pass.
- stale: bottom error panel still exists; no drawer; compile toasts still global.
- missing: canvas node marker, property-field marker, Monaco line marker, copyable compile drawer.

### 原 Known Drift / 待办（迁移保留）
- Workflow requires three contextual error locations plus a drawer; current UI only shows center button color/toast/floating panel (`apps/studio/frontend/src/components/studio/Workspace.tsx:CompileErrorPanel（L571）`).
- Predict-pass is never set because Predict is still a stub; Run remains unreachable through the intended gate (`apps/studio/frontend/src/components/studio/Workspace.tsx:currentCompileErrors（L537）`).

<a id="02-capabilities-conflict-overwrite"></a>

## 02_capabilities/conflict-overwrite

来源: [`baseline.md`](02_capabilities/conflict-overwrite/baseline.md)

### 原 Current Coverage（迁移保留）
- live: expected-hash file conflict, graph serialization conflict, sequential overwrite warning and opt-in.
- stale: overwrite marker is written to old frontmatter shape and not unified with compile diagnostics.
- missing: single conflict taxonomy shared by canvas, editor, and compile drawer.

### 原 Known Drift / 待办（迁移保留）
- Sequential overwrite is currently front-end detected; engine compile should be the durable authority for invalid data flow (`apps/studio/frontend/src/components/GraphCanvas/canvas-authoring.ts:checkSequentialOverwrites（L237）`).
- The UX has two conflict paths: graph overwrite popover and file conflict dialog (`apps/studio/frontend/src/components/studio/Workspace.tsx:handleUseRemote（L264）`).

<a id="02-capabilities-copilot-assist"></a>

## 02_capabilities/copilot-assist

来源: [`baseline.md`](02_capabilities/copilot-assist/baseline.md) · [`mvp1-alignment.md`](02_capabilities/copilot-assist/mvp1-alignment.md)

### 原 Current Coverage（迁移保留）
1. skill 打开 → `copilotOpen=Boolean(skillId)`（`Workspace.tsx:41,545`），welcome 屏无 copilot。
2. `useCopilot` 建 WS `/api/skills/{id}/copilot/ws`；skillId 变即 reset 消息（**纯内存**，`copilotStore.ts:10-12,27-28`）。
3. 发消息 → `{user_message, model_override?}`（`useCopilot.ts:143-157`，**无 mentions / dirty buffer / 选中态**）。
4. 后端 `stream_query` → SDK；`TextBlock/ToolUse/ToolResult` 翻成事件 `send_json`（`copilot.py:378-400`）；**`ThinkingBlock` 丢**。
5. 流式 `text_delta` 进 textQueue，75ms flush（`useCopilot.ts:50-70`）。
6. SDK `acceptEdits` → Write/Edit **直接落盘**（`copilot.py:129`），**无提案**。

### 原 Known Drift / 待办（迁移保留）
- 实现前重核 file:line（baseline 基于 2026-05-20 mvp0 + 本轮 SDK 复核）。
- `ThinkingBlock`/`ServerToolUse`/`SystemMessage` 翻译补全范围（alignment 要求全流式不省略）。

### 原 gaps / 待设计（迁移保留）
- F3 主动诊断触发粒度(compile-fail 事件→主动消息 vs 错误旁一键)— 实现细化。
- F1 `ThinkingBlock`/`ServerToolUse`/`SystemMessage` 翻译范围 + 折叠分类细则。
- F4 tiptap 类富文本编辑器选型(内联 pill)。
- F5 SDK `can_use_tool`/PreToolUse 拦截 + Bash auto-allow 白名单范围 — 先 30 行 PoC。
- 工具集是否扩(Grep/Glob 给 F1 Explored 探索)。

<a id="02-capabilities-debug-resume"></a>

## 02_capabilities/debug-resume

来源: [`baseline.md`](02_capabilities/debug-resume/baseline.md)

### 原 Current Coverage（迁移保留）
- backend-only/placeholder: resume route, checkpoint file, engine clarification events.
- missing frontend: failed-node red light, node Resume, HitL question frame, context tamper editor, dirty checkpoint invalidation.
- engine gap: node-level checkpoint validity and resume-from-node semantics.

### 原 Known Drift / 待办（迁移保留）
- Workflow requires node-level resume from the failed node without rerunning upstream; current route is 501 (`apps/studio/backend/app/routers/runs.py:resume_run（L69）`).
- Workflow requires dirty-state invalidation; current Studio has no checkpoint validity model (`apps/studio/backend/app/services/run_manager.py:_ensure_run_files（L167）`).

<a id="02-capabilities-file-editing"></a>

## 02_capabilities/file-editing

来源: [`baseline.md`](02_capabilities/file-editing/baseline.md)

### 原 Current Coverage（迁移保留）
- live: open, autosave, manual save via callback, expected-hash conflict path, read-only editor option.
- stale: write path goes through Python, not Rust/native-fs target.
- missing: trace read-only document view, writable context-tamper editor for debug-resume, editor gutter diagnostics.

### 原 Known Drift / 待办（迁移保留）
- D12 says local writes should be Rust/native-fs; current file writes route through FastAPI (`apps/studio/backend/app/services/skills.py:update_skill_file（L410）`).
- Compile errors should appear inline like an IDE; Monaco diagnostics are not wired (`apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:handleChange（L217）` only toggles read-only).
- Trace wants a human-readable read-only trace document; existing trace components are not mounted into the editor flow (`apps/studio/frontend/src/components/TracePanel.tsx:filter（L50）`).

<a id="02-capabilities-golden-eval"></a>

## 02_capabilities/golden-eval

来源: [`baseline.md`](02_capabilities/golden-eval/baseline.md)

### 原 Current Coverage（迁移保留）
- live/backend: list/set whole-run golden, run-vs-golden diff, predict trace guard.
- orphan/frontend: useGoldenDiff, TracePanel compare/golden buttons.
- target gap: per-node golden state, i/o panel golden JSON editing, copilot-assisted design, output-schema invalidation.

### 原 Known Drift / 待办（迁移保留）
- Target golden is per-agent-node author expectation; current implementation copies whole-run final_state (`apps/studio/backend/app/services/golden_diff.py:set_golden_baseline_for_run（L34）`).
- Frontend diff hook route is wrong for current backend (`apps/studio/frontend/src/hooks/useGoldenDiff.ts:response（L27）`).

<a id="02-capabilities-graph-authoring"></a>

## 02_capabilities/graph-authoring

来源: [`baseline.md`](02_capabilities/graph-authoring/baseline.md)

### 原 Current Coverage（迁移保留）
- live: render, select, double-click open, connect/disconnect persistence, cycle overlay, add phase command.
- stale: phase type inference still reads `mode`/old subgraph fields.
- placeholder: subgraph inline rows, edge context JSON, status derivation from run events.

### 原 Known Drift / 待办（迁移保留）
- The target graph spec says node type comes from phase file kind; current authoring helpers still generate old body/frontmatter shapes (`apps/studio/frontend/src/components/GraphCanvas/canvas-authoring.ts:defaultPhaseMarkdown（L143）`).
- The target trace/dot model needs real transition state; current edge panel is mock (`apps/studio/frontend/src/components/edges/ContextEdge.tsx:getMockEdgeContext（L30）`).
- D12 says writes should route through Rust/native-fs; current graph persist uses the Python file API (`apps/studio/frontend/src/components/studio/Workspace.tsx:handlePersistConnection（L206）`).

<a id="02-capabilities-phase-editing"></a>

## 02_capabilities/phase-editing

来源: [`baseline.md`](02_capabilities/phase-editing/baseline.md)

### 原 Current Coverage（迁移保留）
- live: selected-node Properties form, phase file read/save, editor synchronization.
- stale: field set, node kind inference, subgraph target field, XML body blocks.
- missing: current three node-type field whitelist, i/o output artifact settings, L3 step editing, golden output settings.

### 原 Known Drift / 待办（迁移保留）
- Workflow calls the current Properties form stale and requires a field whitelist rebuild (`docs/studio/mvp1/01_workflows/02_authoring.md:02_authoring（L28）`, `docs/studio/mvp1/01_workflows/02_authoring.md:02_authoring（L29）`).
- Current helpers still write old fields that the target authoring flow should not expose (`apps/studio/frontend/src/components/GraphCanvas/canvas-authoring.ts:defaultPhaseMarkdown（L143）`).

<a id="02-capabilities-publish"></a>

## 02_capabilities/publish

来源: [`baseline.md`](02_capabilities/publish/baseline.md)

### 原 Current Coverage（迁移保留）
- live: Release action, Artifact Registry zip upload, user/registry precondition checks, local run autocommit.
- stale-doc deleted by workflow: git push, commit-message UI, confetti.
- target gap: package build should move to Rust/native-fs if D12 is applied strictly.

### 原 Known Drift / 待办（迁移保留）
- Publish is hidden under Team menu and does not close the loop back to Home automatically (`apps/studio/frontend/src/components/studio/Header.tsx:prTitle（L98）`).
- Packaging is Python-sidecar code today, while D12 targets Rust-native local packaging (`apps/studio/backend/app/services/artifact_registry.py:build_publish_package（L91）`).

<a id="02-capabilities-run-execution"></a>

## 02_capabilities/run-execution

来源: [`baseline.md`](02_capabilities/run-execution/baseline.md)

### 原 Current Coverage（迁移保留）
- live/backend: start run, worker, run files, websocket stream, run history, batch route, autocommit.
- orphan/frontend: batch runner, run detail drawer, run stream hook, node status animation.
- missing: Run button hookup, `statusByNodeId` mapping, focus follow, i/o panel entry.

### 原 Known Drift / 待办（迁移保留）
- Workflow requires node lights driven by real run events; Workspace does not pass `statusByNodeId` to GraphCanvas (`apps/studio/frontend/src/components/studio/Workspace.tsx:currentCompileErrors（L515）`).
- Run should start from i/o panel input selection; current button has no input contract (`apps/studio/frontend/src/components/studio/Workspace.tsx:currentCompileErrors（L538）`).

<a id="02-capabilities-skill-workspace"></a>

## 02_capabilities/skill-workspace

来源: [`baseline.md`](02_capabilities/skill-workspace/baseline.md)

### 原 Current Coverage（迁移保留）
- live: Home list, recent skills, folder picker path, create/import/delete API path, reveal in file manager.
- stale: registry/public workspace aggregation and strict import gate.
- target gap: open any local folder first, then let compile/copilot repair the skill into standard form.

### 原 Known Drift / 待办（迁移保留）
- D11 expects an IDE/workspace model with no registry as the primary user mental model; current backend still treats a saved index/registry as central (`apps/studio/backend/app/services/skills.py:list_skill_summaries（L183）`).
- D2 says import should not be blocked by file shape; current import rejects folders without both root docs (`apps/studio/backend/app/services/skills.py:create_new_skill（L512）`).
- D12 says local writes should move to Rust/native-fs; create/import/write still go through FastAPI/Python (`apps/studio/backend/app/routers/skills.py:list_skills（L81）`).

<a id="02-capabilities-studio-settings"></a>

## 02_capabilities/studio-settings

来源: [`baseline.md`](02_capabilities/studio-settings/baseline.md)

### 原 Current Coverage（迁移保留）
- live: settings shell, credential CRUD, endpoint/model tests, roles save, websocket refresh, copilot role tab.
- stale: five-state provider projection, fake/copilot test divergence, role key prefix bug.
- target gap: canonical six-state model and full role-fit/materializer projection in the visible UI.

### 原 Known Drift / 待办（迁移保留）
- MVP1 settings spec defines a six-state canonical state; current code still has `needs_setup` and lacks `historical_ready`/`failed(reason)` (`apps/studio/backend/app/services/llm_state_projection.py:llm_state_projection（L12）`).
- Copilot role save can lose the `copilot_` naming boundary, while backend split logic depends on it (`apps/studio/frontend/src/components/studio/settings/copilot/CopilotTab.tsx:selectModelGroup（L219）`, `apps/studio/backend/app/routers/llm.py:_is_copilot_role（L909）`).

<a id="02-capabilities-trace-observability"></a>

## 02_capabilities/trace-observability

来源: [`baseline.md`](02_capabilities/trace-observability/baseline.md)

### 原 Current Coverage（迁移保留）
- live/backend: trace file, websocket stream, run history detail.
- orphan/frontend: TracePanel, PromptInspector, RunDetailDrawer, useRunStream, filtering.
- placeholder/mock: edge dot context, node state derivation, human-readable full trace doc.

### 原 Known Drift / 待办（迁移保留）
- Workflow wants run-time panel auto-open and run-after readable trace document; current mounted Timeline only lists runs (`apps/studio/frontend/src/components/studio/panels/TimelinePanel.tsx:TimelinePanel（L71）`).
- Dot semantics are real blackboard transitions; current edge context uses generated mock JSON (`apps/studio/frontend/src/components/edges/ContextEdge.tsx:getMockEdgeContext（L30）`).

<a id="03-regions-assets"></a>

## 03_regions/assets

来源: [`baseline.md`](03_regions/assets/baseline.md)

### 原 Current Region Ownership / Coverage（迁移保留）
- Owns: file tree, folder/file rows, subgraph path status/recovery UI.
- Does not own: Properties fields, workspace import root policy, graph topology.

### 原 Known Drift（迁移保留）
- MVP1 subgraph references should be local paths; current code still detects registry-era target fields (`apps/studio/frontend/src/components/studio/panels/AssetsPanel.tsx:mode（L103）`).
- Fallback subgraph rows are demo data and must not ship as actual workspace state (`apps/studio/frontend/src/components/studio/panels/AssetsPanel.tsx:displaySubgraphs（L120）`).

<a id="03-regions-canvas"></a>

## 03_regions/canvas

来源: [`baseline.md`](03_regions/canvas/baseline.md)

### 原 Current Region Ownership / Coverage（迁移保留）
- Owns: graph drawing, node/edge hit targets, canvas context menus, visible node status, subgraph visual affordance.
- Does not own: Properties form fields, engine compile rules, trace data interpretation.

### 原 Known Drift（迁移保留）
- Target dot means blackboard transition; current ContextEdge data is generated mock JSON (`apps/studio/frontend/src/components/edges/ContextEdge.tsx:getMockEdgeContext（L30）`).
- Target runtime/debug status needs trace event derivation; current Canvas receives no real status map from Workspace (`apps/studio/frontend/src/components/studio/Workspace.tsx:currentCompileErrors（L515）`).

<a id="03-regions-center-action-bar"></a>

## 03_regions/center-action-bar

来源: [`baseline.md`](03_regions/center-action-bar/baseline.md)

### 原 Current Region Ownership / Coverage（迁移保留）
- Owns: centered primary workflow controls, stage gate visualization, compile drawer target.
- Does not own: actual predict/run data config, compile engine rules, trace panel.

### 原 Known Drift（迁移保留）
- Workflow deletes the bottom floating compile error panel and replaces it with a drawer (`apps/studio/frontend/src/components/studio/Workspace.tsx:CompileErrorPanel（L571）`).
- Predict-pass is never set, so Run cannot become the intended next action (`apps/studio/frontend/src/components/studio/Workspace.tsx:currentCompileErrors（L537）`).

<a id="03-regions-copilot"></a>

## 03_regions/copilot

来源: [`baseline.md`](03_regions/copilot/baseline.md)

### 原 Current Region Ownership / Coverage（迁移保留）
- Owns: chat panel UI, message rendering, model picker in chat, tool/diff bubbles, input composer.
- Does not own: Settings Copilot tab, backend route/materializer, full capability decisions.

### 原 Known Drift（迁移保留）
- Workspace prop mismatch can attach chat to stale skill when navigating subgraphs or switching current skill (`apps/studio/frontend/src/components/studio/Workspace.tsx:currentCompileErrors（L554）`).
- Attach file and Add context buttons are visible but not wired to a real picker/context selection flow (`apps/studio/frontend/src/components/copilot/copilot-panel.tsx:submit（L200）`).

<a id="03-regions-editor"></a>

## 03_regions/editor

来源: [`baseline.md`](03_regions/editor/baseline.md)

### 原 Current Region Ownership / Coverage（迁移保留）
- Owns: Monaco editor surface, split editor layout, file save/read-only behavior, future virtual documents.
- Does not own: file tree, Properties field form, trace interpretation.

### 原 Known Drift（迁移保留）
- Compile inline markers are required but not wired to Monaco diagnostics (`apps/studio/frontend/src/components/studio/LazyMonacoPanel.tsx:handleChange（L217）` only covers read-only).
- Run-after full trace should open as human-readable read-only document; no such editor flow is mounted (`apps/studio/frontend/src/components/TracePanel.tsx:filter（L50）`).

<a id="03-regions-input"></a>

## 03_regions/input

来源: [`baseline.md`](03_regions/input/baseline.md)

### 原 Current Region Ownership / Coverage（迁移保留）
- Owns: target i/o panel for test input files, schema, per-node i/o config, output artifacts, golden JSON/settings, single/batch run input selection.
- Current code only owns: input file rows and local schema inference demo.

### 原 Known Drift（迁移保留）
- Workflow renames/expands this to i/o panel; current UI still says "Input" and lacks output/golden settings (`apps/studio/frontend/src/components/studio/panels/InputPanel.tsx:sample（L78）`).
- Input/predict/run should use configured files; current buttons ignore the panel (`apps/studio/frontend/src/components/studio/Workspace.tsx:currentCompileErrors（L537）`).

<a id="03-regions-local-history"></a>

## 03_regions/local-history

来源: [`baseline.md`](03_regions/local-history/baseline.md)

### 原 Current Region Ownership / Coverage（迁移保留）
- Owns: local git snapshot list, selection, revert, run-autocommit visibility.
- Ownership conflict: run detail and batch summary appear closer to `timeline`/`input` than local git history.

### 原 Known Drift（迁移保留）
- Workflow assigns successful-run autocommit to publish/save; Local History shows snapshots but does not explain git status (`apps/studio/frontend/src/components/history/HistoryPanel.tsx:selectedItem（L67）`).
- Run detail drawer has Compare/Replay/Export but no integration point (`apps/studio/frontend/src/components/history/RunDetailDrawer.tsx:RunDetailDrawer（L54）`).

<a id="03-regions-properties"></a>

## 03_regions/properties

来源: [`baseline.md`](03_regions/properties/baseline.md)

### 原 Current Region Ownership / Coverage（迁移保留）
- Owns: selected node property forms, selected edge summary if kept, field-level compile markers.（**golden 不归 Properties** —— PM 2026-06-04 已决 golden 完全不在 Properties，详细 diff 在 editor、入口在 I/O output + Assets。）
- Should not own: raw trace JSON dumping; trace data interpretation belongs to Timeline/Trace.

### 原 Known Drift（迁移保留）
- Workflow says current Properties form is stale and must rebuild by node-type whitelist (`docs/studio/mvp1/01_workflows/02_authoring.md:02_authoring（L28）`).
- Workflow says selected-edge JSON dump should be cleaned up and dot trace moved to trace-observability (`docs/studio/mvp1/01_workflows/04_run-and-verify.md:04_run-and-verify（L99）`).

<a id="03-regions-settings"></a>

## 03_regions/settings

来源: [`baseline.md`](03_regions/settings/baseline.md)

### 原 Current Region Ownership / Coverage（迁移保留）
- Owns: Settings shell, General, API Keys, LLM Roles, Copilot settings UI, save/error/loading states.
- Does not own: chat panel UI, gateway internals, predict/run behavior.

### 原 Known Drift（迁移保留）
- Canonical six-state model is not implemented in UI or backend projection (`apps/studio/backend/app/services/llm_state_projection.py:llm_state_projection（L12）`).
- CopilotTab ignores save status/error and can rekey role ids incorrectly (`apps/studio/frontend/src/components/studio/settings/copilot/CopilotTab.tsx:CopilotTab（L70）`, `apps/studio/frontend/src/components/studio/settings/copilot/CopilotTab.tsx:selectModelGroup（L219）`).

<a id="03-regions-shell-layout"></a>

## 03_regions/shell-layout

来源: [`baseline.md`](03_regions/shell-layout/baseline.md)

### 原 Current Region Ownership / Coverage（迁移保留）
- Owns: shell grid, resizable panel placement, header, toolbar, settings overlay placement, copilot panel slot.
- Does not own: content inside each panel, graph canvas internals, settings form internals.

### 原 Known Drift（迁移保留）
- The shell should remain usable when sidecar-dependent features fail; RuntimeGate still has full-screen loading/error semantics (`apps/studio/frontend/src/components/RuntimeGate.tsx:cancelled（L31）`).
- Copilot panel may use stale skill context because Workspace passes `skillId` rather than `currentSkillId` (`apps/studio/frontend/src/components/studio/Workspace.tsx:currentCompileErrors（L554）`).

<a id="03-regions-timeline"></a>

## 03_regions/timeline

来源: [`baseline.md`](03_regions/timeline/baseline.md)

### 原 Current Region Ownership / Coverage（迁移保留）
- Owns: run history list, live trace stream, run-after full trace timeline, prompt inspector entry, selected-run summary.
- Current mounted code owns only run list.

### 原 Known Drift（迁移保留）
- Workflow says run starts should auto-open live trace; current Timeline is manual history only (`apps/studio/frontend/src/components/studio/panels/TimelinePanel.tsx:TimelinePanel（L71）`).
- TracePanel uses one-off hardcoded palette classes and needs design-system cleanup before mounting (`apps/studio/frontend/src/components/TracePanel.tsx:filter（L50）`).

<a id="03-regions-welcome"></a>

## 03_regions/welcome

来源: [`baseline.md`](03_regions/welcome/baseline.md)

### 原 Current Region Ownership / Coverage（迁移保留）
- Owns: Home/Recent grid, New Skill dialog entry, Import Skill entry, reveal/delete card menu, empty/error states.
- Does not own: graph editor internals, settings forms, publish result pages.

### 原 Known Drift（迁移保留）
- MVP1 wants open/import to accept arbitrary folders and let compile/copilot repair; current backend blocks import before entering the workspace (`apps/studio/backend/app/services/skills.py:create_new_skill（L512）`).
- Current button text says "Import skill"; target mental model may need "Open folder" for IDE/workspace framing (`apps/studio/frontend/src/components/welcome/WelcomePage.tsx:existingSkillId（L350）`).

<a id="04-platform-engine"></a>

## 04_platform/engine

来源: [`baseline.md`](04_platform/engine/baseline.md)

### 原 Current Coverage / 现状逻辑（迁移保留）
- live: compile, predict, run, trace file, run artifacts, error payloads, whole-run diff.
- target gaps: per-node golden model, trace transition payload schema, node-level checkpoint resume, dirty invalidation, HitL injection.

### 原 Known Drift / 待办（迁移保留）
- MVP1 wants per-node golden and predict mock-by-golden; current golden diff is whole-run final_state based (`apps/studio/backend/app/services/golden_diff.py:set_golden_baseline_for_run（L34）`).
- Debug resume requires node-level checkpoint validity; current Studio endpoint is 501 (`apps/studio/backend/app/routers/runs.py:resume_run（L69）`).

<a id="04-platform-gateway"></a>

## 04_platform/gateway

来源: [`baseline.md`](04_platform/gateway/baseline.md)

### 原 Current Coverage / 现状逻辑（迁移保留）
- live: registry schema, resolver, model adapter, chat fallback, role materializer, health/circuit store, HTTP routes.
- stale/target gap: canonical six-state projection, copilot SDK test path parity, clearer split between HTTP glue and gateway library.

### 原 Known Drift / 待办（迁移保留）
- Settings spec asks for canonical six-state model; current backend projection still emits `needs_setup` (`apps/studio/backend/app/services/llm_state_projection.py:llm_state_projection（L12）`).
- Copilot role tests have a distinct probe path from real Copilot chat runtime (`apps/studio/backend/app/routers/llm.py:_probe_copilot_sdk_tool_call（L2150）`, `apps/studio/backend/app/services/copilot.py:stream_query（L201）`).

<a id="04-platform-llm-copilot-http-api"></a>

## 04_platform/llm-copilot-http-api

来源: [`baseline.md`](04_platform/llm-copilot-http-api/baseline.md) · [`mvp1-alignment.md`](04_platform/llm-copilot-http-api/mvp1-alignment.md)

### 原 Current Coverage / 现状逻辑（迁移保留）
### 1. Registry 读取与 endpoint CRUD

> **判据标注**：本族里 **canonical 分组、lint、effective runtime settings 计算、base_url 按 protocol 归一化、endpoint 标准化拆分** = ③b 公共能力内核（见 [[03-orch-credentials-endpoints]]/[[02-orch-role-resolution]]）；router 留 **join + DTO 投影 + upsert + 落存储 + 删除引用清理**。当前 `put_registry_endpoints` 直接 upsert、base_url 原样透传（头号根因），MVP1 应在保存路径经 ③b 内核归一化。

1. `get_llm_registry` 读取 credentials 与 roles,再调用 `_registry_response` 输出 `RegistryResponse` (`routers/llm.py:312-318`)。
2. `_registry_response` 会先规范化响应中的 credentials、materialize roles,再按 `canonical_id` 建 groups,对每个 role 调 `lint_role_routes`,并附带 route/runtime settings 投影 (`routers/llm.py:1336-1384`)。
3. `get_registry_endpoint_secret` 只给本地设置 UI 返回某个 endpoint 的 API key 明文,未知 endpoint 抛 404 (`routers/llm.py:321-330`)。
4. `put_registry_endpoints` 调 `upsert_endpoints`,只覆盖请求里出现的 endpoint,不把缺席 endpoint 当删除 (`routers/llm.py:334-343`)。
5. `delete_registry_endpoint` 删除 endpoint 前先计算引用,如果 endpoint 下有 routes 且 roles 文件存在,会从 roles 中移除这些 route 引用,再调用 `delete_endpoint` (`routers/llm.py:346-360`)。

### 2. endpoint/model/route 探测

> **判据标注**：本族里 **probe 策略（批量短路·命中停·结构错短路）、route probe（1-token 真请求）、capability 归一化、错误分类** = ③b 公共能力内核（现散 router 内联 + `services/llm_route_capabilities.py` 等待下沉，见 [[05-orch-capabilities-and-models]]/[[07-orch-fallback-circuit-probe]]）；router 留 **job/进度/HTTP 包装 + 落存储**。

1. `start_endpoint_test_job` 只允许 official endpoint,同一 endpoint 已有 queued/running job 时返回原 job,否则创建 job 并后台启动 `_run_official_endpoint_test_job` (`routers/llm.py:363-393`)。
2. `test_endpoint` 对 endpoint 发最小 models-list 请求;成功拿到模型时调用 `_upsert_discovered_routes`,并把 observation 追加进 evidence library (`routers/llm.py:460-574`)。
3. `test_endpoint_models` 对用户指定模型 ID 做 probe。official provider 会先产出 `VerifiedProfile`,third-party provider 则跑 `_probe_model`;成功后写 verified route,失败时更新 endpoint/route 状态和 evidence (`routers/llm.py:581-780`)。
4. `probe_route` 对单条 route 更新 capability 标记;带 `force=true` 时委托 `_force_probe_route` 发真实请求并处理 health circuit (`routers/llm.py:782-818`)。
5. `_force_probe_route` 在 missing key 时直接把 route 写成 failed;真实 probe 成功时写 verified 并 clear circuit;timeout/rate/network 类失败时打开 route circuit;其他失败写入 route metadata (`routers/llm.py:1818-1887`)。

### 3. import draft 与 evidence library

> **判据标注**：**draft 知识库内核（记录/复用/合并探测证据）** = ③b 公共（现 `services/llm_import_drafts.py` 待下沉，见 [[08-orch-test-status-ssot]]）；router 留 **import/apply 工作流 + 远端源选择**（现硬编码 GitHub repo，应改可配置）= ③a 应用加工。

1. `sync_catalog` 拉远端 evidence library 并合并到本地 (`routers/llm.py:397-412`)。
2. `share_catalog` 导出本地 verified probe evidence,用于社区共享 (`routers/llm.py:415-445`)。
3. `post_import_draft` 创建 draft,`get_import_draft` 读取 draft,`probe_import_draft` 只把 draft 标记为 probed,`apply_import_draft` 显式把 draft merge/apply 到 active credentials (`routers/llm.py:856-880`)。

### 4. role 与 model profile

> **判据标注**：**materialize（角色→fallback 链）、6 态投影、route probe** = ③b 公共内核（见 [[02-orch-role-resolution]]/[[08-orch-test-status-ssot]]/[[07-orch-fallback-circuit-probe]]）；router 留 **HTTP CRUD + job 包装 + Copilot/Graph Agent 分流保护**（分流认 `copilot_` 前缀 = ③a 产品策略，绑 copilot 语义，留 ③a service 不下沉 ③b）。

1. `get_llm_roles` 返回 `_materialize_roles_for_response` 后的 route-backed roles (`routers/llm.py:899-901`)。
2. `put_llm_roles` 有 Copilot/Graph Agent 分流保护:保存 Graph Agent roles 时保留现有 Copilot roles,保存 Copilot roles 时保留现有 Graph Agent roles (`routers/llm.py:909-952`)。
3. `put_llm_role` 单 role replace;如果 request 有 `model_groups`,先调用 `materialize_role` 展开为 route chain (`routers/llm.py:964-981`)。
4. `test_llm_role` 与 `start_role_test_job` 都先 materialize role,再由 `_role_test_targets` 把 fallback_chain 转成 route+endpoint targets (`routers/llm.py:996-1037`,`:1046-1068`)。
5. `_role_test_provider_result` 先通过 `_provider_model_projection` 得到 UI state,再根据 admission 决策决定 block/untested/probe;Copilot role 调 `_probe_copilot_sdk_tool_call`,普通 role 调 `_probe_role_route` (`routers/llm.py:1889-1959`)。
6. `get_model_profiles/put_model_profiles` 读写 profile map,`delete_model_profile` 删除 profile 并在仍引用它的 roles 上留下 deleted snapshot,`apply_model_profile` 把 profile 的 fallback_chain snapshot 写入 role (`routers/llm.py:1222-1309`)。

### 5. route 投影与内部 helper

> **判据标注**：本族里 **materialize（角色→fallback 链编排）、`resolve_role`（effective runtime settings）、canonical 分组、capability 合并** = ③b 公共能力内核（现散 `services/llm_role_materializer.py` / `services/llm_model_groups.py` / `services/llm_route_capabilities.py` 待下沉，见 [[02-orch-role-resolution]]/[[05-orch-capabilities-and-models]]）；router 留 **DTO 投影 + schema_version 包装**。其中 `_materialize_role_for_response` 对 Copilot role 的"找 canonical model + 扩展同模型组 route" = ③a 产品兼容逻辑（绑 copilot 语义），留 ③a。

1. `_upsert_discovered_routes` 根据 endpoint+model_id 生成 route_id,新 route 调 `_provider_route`,老 route 按 verified/profile/probe attempts 更新 capabilities 与 metadata (`routers/llm.py:4381-4477`)。
2. `_provider_route` 负责构造 `ProviderRoute`:route_id、endpoint_id、provider_model_id、canonical_id、status、capabilities、verified_profiles、metadata (`routers/llm.py:4480-4534`)。
3. `_role_effective_runtime_settings` 把 roles+credentials 转 registry snapshot,逐 role 调 `resolve_role`,把每条 resolved route 的 effective settings 暴露给前端 (`routers/llm.py:4588-4603`)。
4. `_materialize_roles_for_response` 对 Copilot role 做兼容 route 扩展,对 model_groups 角色调用 materializer,最后把 schema_version 提到 3 (`routers/llm.py:4613-4642`)。
5. `_materialize_role_for_response` 对部分 Copilot role 先找 canonical model,再用 `find_compatible_route_ids_for_model` 扩展同模型组 route (`routers/llm.py:4682-4723`)。

### 6. Copilot router

1. `dispatch_copilot` 是未实现旧入口,当前返回 501 (`routers/copilot.py:23-31`)。
2. `copilot_ws` 是真实 websocket 入口,收到请求后调 `app.services.copilot:stream_query` (`routers/copilot.py:34-55`)。
3. `post_copilot_context` 只更新 view context 缓存,用于后续 prompt 拼接 (`routers/copilot.py:58-86`)。
4. `test_copilot_role_sdk` 是 Copilot role 测试入口,但内部调用 LLM router 的 `_probe_copilot_sdk_tool_call` (`routers/copilot.py:89-126`)。

### 原 Known Drift / 待办（迁移保留）
- `apps/studio/backend/app/routers/llm.py` 已达约 4960 行,把 API handler、job store、probe 策略、projection、evidence、role materialize 都放在一个文件里;MVP1 后续应拆成 endpoint registry、probe jobs、role/profile、import drafts、projection helpers 等模块。
- `test_copilot_role_sdk` 的测试实现走 `AsyncAnthropic`,而真实 Copilot 走 `ClaudeSDKClient`;这个"假测试"问题的修正归 studio copilot（[[copilot-assist]] + `../../01_workflows/00_settings-ux-spec.md` §3.4/§3.8）。
- `put_llm_roles` 中 Copilot/Graph Agent 分流属于产品保护逻辑,但现在写在 router handler 内 (`routers/llm.py:909-952`),后续最好下沉到 service 层以便复用和测试。

### 原 gaps / 已实现差异 / 代码索引（迁移保留）
- **待办（后续工程，非本轮）**：把 `routers/llm.py` 的非 HTTP glue 逻辑拆到 service 层，尤其是 official profile probe、role test job、registry response projection、import draft/evidence；其中能力内核继续下沉 ③b（gateway 包），studio 适配/工作流（job/进度/HTTP 包装、import-apply UI 工作流、远端源选择）留 ③a。
- **待办**：把 Copilot SDK test 改为真实 `ClaudeSDKClient` 路径，否则 API 层仍会给前端一个不可靠的"通过"信号；归 [[copilot-assist]]。
- **待办**：`put_llm_roles` 中 Copilot/Graph Agent 分流属于产品保护逻辑，但现在写在 router handler 内（`routers/llm.py:909-952`）；分流"认 `copilot_` 前缀"是 ③a 产品策略，后续最好下沉到 service 层以便复用和测试（注意：是 ③a service，不是 ③b——它绑死 copilot 语义）。
- **疑点**：`dispatch_copilot`（`routers/copilot.py:23`）保留旧 dispatch scaffold 当前直接 501，是否清理需主控确认。

<a id="04-platform-native-fs"></a>

## 04_platform/native-fs

来源: [`baseline.md`](04_platform/native-fs/baseline.md)

### 原 Current Coverage / 现状逻辑（迁移保留）
- live: sidecar lifecycle, config/token, directory picker, reveal/open helpers, CORS origin injection.
- stale: local write authority is still Python-sidecar code.
- target gap: Rust-native read/write/watch/MRU/runs/golden/artifacts orchestration.

### 原 Known Drift / 待办（迁移保留）
- D12 target is "local writes all Rust, only engine/gateway remain Python sidecars"; current file and graph writes go through FastAPI (`apps/studio/backend/app/services/skills.py:update_skill_file（L410）`).
- Some external IDE helpers may be outside the locked MVP1 shell model and need product confirmation (`apps/studio/tauri/src/lib.rs:spawn_tool（L70）`).

<a id="04-platform-state-engine"></a>

## 04_platform/state-engine

来源: [`baseline.md`](04_platform/state-engine/baseline.md)

### 原 Current Coverage / 现状逻辑（迁移保留）
- live: local Workspace state, SWR data, lint event bridge, run/copilot websockets, settings global event listener.
- missing: central event-to-node-state derivation, typed event bus, scoped sidecar failure model, run/debug state reducer.

### 原 Known Drift / 待办（迁移保留）
- Trace/debug require a shared event-to-node-state derivation; current node statuses are not driven from run events (`apps/studio/frontend/src/components/studio/Workspace.tsx:currentCompileErrors（L515）`).
- RuntimeGate can still full-screen block the app shell (`apps/studio/frontend/src/components/RuntimeGate.tsx:cancelled（L31）`).
