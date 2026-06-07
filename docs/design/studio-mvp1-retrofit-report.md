# Studio MVP1 Retrofit Report

> Generated after R4-R8 retrofit on `docs/studio/mvp1/` axis-2 module docs. Current pinned code: `0d9fbaf`. No code files were edited by this retrofit.

## Batch Summary

| Batch | Scope | Result |
|---|---|---|
| capabilities | `02_capabilities/*` except `predict` | 13 baseline/alignment pairs retrofitted; `predict` kept as golden sample |
| regions | `03_regions/*` | 12 baseline/alignment pairs retrofitted |
| platform | `04_platform/{engine,gateway,llm-copilot-http-api,native-fs,state-engine}` + `i18n.md` | 5 baseline/alignment pairs retrofitted; `i18n.md` got frontmatter/units/cross-links while preserving its structure |

## Retrofitted Modules And Units

### capabilities

| Module | Units | Notes |
|---|---|---|
| `docs/studio/mvp1/02_capabilities/compile-lint` | `[compile-stage-gate, compile-lint-structured-error]` | drafted（现状对齐 pinned 代码 0d9fbaf；lint/compile 触发与 compile-pass stage live；错误仍是底部浮层/toast，drawer 与上下文标记未落 ⚠️。） |
| `docs/studio/mvp1/02_capabilities/conflict-overwrite` | `[conflict-overwrite-resolution]` | drafted（现状对齐 pinned 代码 0d9fbaf；顺序覆盖与文件保存冲突都有实现痕迹，但还是两套 UX，没有统一冲突呈现 ⚠️。） |
| `docs/studio/mvp1/02_capabilities/copilot-assist` | `[copilot-sdk-test-parity, copilot-session-persistence]` | drafted（现状对齐 pinned 代码 0d9fbaf；SDK 对话 live，但仍直写、session 内存态、ThinkingBlock 未翻译，Settings 里的 SDK 测试路径与真实 chat 不等价 ⚠️。） |
| `docs/studio/mvp1/02_capabilities/debug-resume` | `[debug-resume-checkpoint]` | drafted（现状对齐 pinned 代码 0d9fbaf；Studio resume route 存在但直接 501，节点级 Resume 主路径不可用 ⚠️。） |
| `docs/studio/mvp1/02_capabilities/file-editing` | `[native-rust-writer]` | drafted（现状对齐 pinned 代码 0d9fbaf；Monaco 编辑与 FastAPI 写文件 live；MVP1 D12 要求 Rust 唯一写者，当前写路径仍走 FastAPI ⚠️。） |
| `docs/studio/mvp1/02_capabilities/golden-eval` | `[golden-per-agent-node]` | drafted（现状对齐 pinned 代码 0d9fbaf；后端 golden 以整次 run final_state 复制为 baseline；per-agent-node golden 目标未落 ⚠️。） |
| `docs/studio/mvp1/02_capabilities/graph-authoring` | `[subgraph-path-inline-drilldown]` | drafted（现状对齐 pinned 代码 0d9fbaf；画布主拓扑 live；新建 phase 和 subgraph 仍混旧字段，inline subgraph 是 mock ⚠️。） |
| `docs/studio/mvp1/02_capabilities/phase-editing` | `[phase-field-whitelist, node-properties-role-test, io-panel-artifacts-test-inputs]` | drafted（现状对齐 pinned 代码 0d9fbaf；Properties/phase parser 仍读写旧 `mode/system_prompt/exit_contract/python_callable/target_skill` 字段 ⚠️。） |
| `docs/studio/mvp1/02_capabilities/publish` | `[publish-artifact-autocommit]` | drafted（现状对齐 pinned 代码 0d9fbaf；Artifact Registry zip 发布路径 live；zip 构建仍在 Python 后端，D12 Rust 写者未收口 ⚠️。） |
| `docs/studio/mvp1/02_capabilities/run-execution` | `[run-execution-node-status, golden-per-agent-node]` | drafted（现状对齐 pinned 代码 0d9fbaf；后端 run manager live；前端 Run handler 仍是桩，predict-pass 不会置位，batch UI 未挂主路径 ⚠️。） |
| `docs/studio/mvp1/02_capabilities/skill-workspace` | `[workspace-open-folder-mru, subgraph-path-inline-drilldown]` | drafted（现状对齐 pinned 代码 0d9fbaf；Welcome 仍读 `/skills` 注册表聚合，import 仍要求 GRAPH/SKILL 门禁；MVP1 IDE-folder 模型未落 ⚠️。） |
| `docs/studio/mvp1/02_capabilities/studio-settings` | `[settings-six-state-provider-health, model-group-role-materialization, node-properties-role-test, copilot-sdk-test-parity]` | drafted（现状对齐 pinned 代码 0d9fbaf；Settings UI/API 大体 live；6 态仍是旧 5 态/`needs_setup`，部分 ③b 内核逻辑还在 Studio 后端巨型路由中 ⚠️。） |
| `docs/studio/mvp1/02_capabilities/trace-observability` | `[trace-dot-blackboard, run-execution-node-status]` | drafted（现状对齐 pinned 代码 0d9fbaf；TracePanel/useRunStream/PromptInspector 存在但未挂主 Studio 流；edge dot 仍是假黑板 JSON ⚠️。） |

### regions

| Module | Units | Notes |
|---|---|---|
| `docs/studio/mvp1/03_regions/assets` | `[subgraph-path-inline-drilldown]` | drafted（现状对齐 pinned 代码 0d9fbaf；文件树 live；subgraph 检测仍读旧 `mode/target_skill/sub_skill_ref`，且有本地假缓存/假 fallback 行 ⚠️。） |
| `docs/studio/mvp1/03_regions/canvas` | `[subgraph-path-inline-drilldown, run-execution-node-status, trace-dot-blackboard]` | drafted（现状对齐 pinned 代码 0d9fbaf；React Flow 画布 live；node status 仍非真实 run 态，edge dot 用 mock 黑板，inline subgraph 用 mock rows ⚠️。） |
| `docs/studio/mvp1/03_regions/center-action-bar` | `[compile-stage-gate, predict-execution]` | drafted（现状对齐 pinned 代码 0d9fbaf；Compile 入口 live；Predict/Run handler 仍是 `console.info` 桩，compile error 仍底部浮层 ⚠️。） |
| `docs/studio/mvp1/03_regions/copilot` | `[copilot-session-persistence, copilot-sdk-test-parity]` | drafted（现状对齐 pinned 代码 0d9fbaf；面板与 WS live；session 仍易丢，ThinkingBlock/@mention/analysis bar 未落，且 Workspace 传 outer `skillId` 有下钻风险 ⚠️。） |
| `docs/studio/mvp1/03_regions/editor` | `[native-rust-writer, trace-dot-blackboard, golden-per-agent-node]` | drafted（现状对齐 pinned 代码 0d9fbaf；Monaco autosave live；写文件仍走 FastAPI，trace 只读文档未接，golden 详细 diff 归属曾残留 Properties 口径 ⚠️。） |
| `docs/studio/mvp1/03_regions/input` | `[io-panel-artifacts-test-inputs, golden-per-agent-node]` | drafted（现状对齐 pinned 代码 0d9fbaf；InputPanel 仍投影固定 `input/sample.json`/`input/schema.json`，schema inference 无写回，Predict/Run 不消费选中输入 ⚠️。） |
| `docs/studio/mvp1/03_regions/local-history` | `[local-history-snapshot]` | drafted（现状对齐 pinned 代码 0d9fbaf；HistoryPanel 只显示 git snapshot；RunDetailDrawer/BatchSummary 存在但未挂，这与最新归属一致但旧 alignment 曾留未决口径 ⚠️。） |
| `docs/studio/mvp1/03_regions/properties` | `[phase-field-whitelist, node-properties-role-test, trace-dot-blackboard]` | drafted（现状对齐 pinned 代码 0d9fbaf；Properties 仍用旧 phase 字段和 raw Connection Trace JSON；golden 完全不在 Properties 的新决策需保持 ⚠️。） |
| `docs/studio/mvp1/03_regions/settings` | `[settings-six-state-provider-health, model-group-role-materialization, copilot-sdk-test-parity, i18n-error-code-ui-copy]` | drafted（现状对齐 pinned 代码 0d9fbaf；Settings shell live；前后端/界面仍有旧 `needs_setup` 与局部易失状态，Copilot tab 还有保存/role-key drift ⚠️。） |
| `docs/studio/mvp1/03_regions/shell-layout` | `[shell-runtime-gate]` | drafted（现状对齐 pinned 代码 0d9fbaf；Workspace shell live；RuntimeGate 仍可全屏 gate，copilot prop 用 outer skillId 有下钻风险 ⚠️。） |
| `docs/studio/mvp1/03_regions/timeline` | `[compile-lint-structured-error, trace-dot-blackboard, run-execution-node-status]` | drafted（现状对齐 pinned 代码 0d9fbaf；TimelinePanel 只列历史 run；TracePanel/PromptInspector/RunDetailDrawer/useRunStream 都存在但未挂主流程 ⚠️。） |
| `docs/studio/mvp1/03_regions/welcome` | `[workspace-open-folder-mru]` | drafted（现状对齐 pinned 代码 0d9fbaf；Welcome 仍从 `/skills` 注册表聚合，import 仍走 backend 门禁；MVP1 open-folder IDE 模型未落 ⚠️。） |

### platform

| Module | Units | Notes |
|---|---|---|
| `docs/studio/mvp1/04_platform/engine` | `[compile-stage-gate, predict-execution, run-execution-node-status, trace-dot-blackboard, golden-per-agent-node, debug-resume-checkpoint, subgraph-path-inline-drilldown, phase-field-whitelist]` | drafted（现状对齐 pinned 代码 0d9fbaf；Studio 已消费 compile/predict/run/trace 部分 engine 能力；resume 仍 501，engine contract 应引用 `docs/engine/mvp1/` SSOT，不在 Studio 重写 ⚠️。） |
| `docs/studio/mvp1/04_platform/gateway` | `[settings-six-state-provider-health, model-group-role-materialization, copilot-sdk-test-parity]` | drafted（现状对齐 pinned 代码 0d9fbaf；Gateway ③b 包已有 schema/resolver/fallback 代码；Studio 侧仍有 5 态投影、materializer、health/draft 等内核散在后端 ⚠️。） |
| `docs/studio/mvp1/04_platform/llm-copilot-http-api` | `[settings-six-state-provider-health, model-group-role-materialization, copilot-sdk-test-parity]` | drafted（现状对齐 pinned 代码 0d9fbaf；`routers/llm.py` 是巨型 router，HTTP glue 与 probe/materialize/draft/6态内核混在一起；Copilot SDK test 仍走假路径 ⚠️。） |
| `docs/studio/mvp1/04_platform/native-fs` | `[native-rust-writer, workspace-open-folder-mru, subgraph-path-inline-drilldown, publish-artifact-autocommit, local-history-snapshot, copilot-session-persistence]` | drafted（现状对齐 pinned 代码 0d9fbaf；Tauri sidecar/picker/reveal live；实际 skill/graph/package 写入仍经 FastAPI/Python，多处未收敛到 Rust 唯一写者 ⚠️。） |
| `docs/studio/mvp1/04_platform/state-engine` | `[shell-runtime-gate, compile-stage-gate, run-execution-node-status, trace-dot-blackboard, settings-six-state-provider-health]` | drafted（现状对齐 pinned 代码 0d9fbaf；状态分散在 Workspace/sessionStorage/SWR/copilotStore/settings hooks；run stream 与 global events 存在但未形成单一 state-engine/WS bridge ⚠️。） |
| `docs/studio/mvp1/04_platform/i18n.md` | `[i18n-error-code-ui-copy]` | drafted（target-design；react-i18next 骨架未落，后端/Copilot 中文残留已按内容审计标为多处 ⚠️） |

## Explicitly Skipped

- `docs/studio/mvp1/02_capabilities/predict/baseline.md` and `mvp1-alignment.md`: already served as the approved golden sample, so they were not modified.

## Checks Run

- Structure check: every retrofitted baseline has frontmatter, `binds_alignment`, `binds_code`, `units`, UI/logic/API/state sections, test-anchor diff table, code path hints, and cross-links.
- Structure check: every retrofitted alignment has frontmatter, `binds_baseline`, `units`, `aligns_with`, §1-§8, and cross-links.
- `i18n.md` special-case check: frontmatter + `units` + cross-links added; existing numbered structure preserved.
- `binds_code` verification: all bound files exist and all bound symbols are present after correction (`missing_count=0`).
- Scope check: changed files are Studio MVP1 docs plus this report; no source-code file was written by the retrofit scripts.

## Issues / Notes

- No missing INDEX unit blocked the retrofit. Units were copied from `DESIGN_UNITS_INDEX.md`; engine/gateway-owned internals are treated as references, not copied Studio SSOT.
- Initial symbol audit found stale idealized names such as `parsePhaseForm`, `run_ws`, `write_skill_file`, and `start_sidecar`; these were corrected to the current symbols before finalizing.
- Existing code drift remains intentionally documented in baseline test anchors with `⚠️`; no code was changed. Examples include Predict/Run stubs, old 5-state provider projection, mock edge blackboard, whole-run golden baseline, and FastAPI/Python write paths that should move behind native/Rust or gateway/engine owners.
- `i18n.md` remains a single-file platform note per the task: it now has `units: [i18n-error-code-ui-copy]` and bidirectional cross-reference text, while its original sections remain intact.
