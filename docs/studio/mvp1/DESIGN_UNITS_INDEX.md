---
doc: design-units-index
status: drafted（轴③ 设计单元索引 = R8 枢纽；PM 已审 decomposition/owner 2026-06-05：25→22 单元、四层 owner 改回 ③b；待逐档接 units）
aligns_with: ../../development/design-doc-standards/02-audit-standard.md（R8）· 01_workflows/INDEX.md（轴① 走查索引，不同物）
---

# Studio MVP1 设计单元索引（轴③ · R8 枢纽）

> **这是设计单元 INDEX**（横切单元 × 模块切面 × owner × binds_code × 锁），**不是** `01_workflows/INDEX.md`（那是轴① workflow 走查索引）。
> **职责**：只记**映射**，不重述实现 / 决策（实现 SSOT 在能力模块就近，决策原话就近 + workflow 留底）。
> **去重铁律**：每个**切面**只有一个 owner 模块写实现；别的模块写同切面 = 重复违规（扫本表「切面 × owner」即照出）。
> **锁**：`unit-lock ∈ {drafted, locked}`。`locked` = 该单元各切面审过 + 盖章；文件级 `FROZEN` = 文件承载的**所有**单元切面都 `locked`。**当前全部 `drafted`**（审计 R7：机器没装、没盖章，0 进 FROZEN）。
> **引擎拥有的切面**：studio 单元若依赖 engine 拥有的契约（子图 path 解析 / golden 落点 / skill 语法 / 错误码 / resolver 协议 / checkpoint），owner 标 `engine:<module>` 且 **只引用 `docs/engine/mvp1/` SSOT、不在 studio 复制**。
> **⚠️ 标记**：`binds_code` 里带 ⚠️ 的 = 已验真的 code↔design drift（现状 vs 目标冲突），按 decision-3 忠实落进对应 baseline + 警告。本表先收口，逐档 retrofit 时把 ⚠️ 同步到各 baseline 的「测试锚点」差异表。
> **状态**：spans / owner 为**首版判断**，逐档 retrofit 时按真实正文复核（标 †=owner 待复核）。

## 单元表

| 单元 | 源 workflow / atom action | spans（模块 × 切面 → owner） | binds_code 主符号（⚠️=已验真 drift） | unit-lock |
|---|---|---|---|---|
| `subgraph-path-inline-drilldown` | 02_authoring D7/G2/T5/T6 | path 解析→`engine:02-resolver`(引) · 语法→`engine:skill-syntax`(引) · 落点→`engine:physical-layout`(引) · inline 展开/下钻/面包屑→`canvas` · 新建子图/默认落点 UI→`graph-authoring` · 未解析导入→`assets` · 写盘→`native-fs` | `canvas-authoring.ts:defaultPhaseMarkdown` ⚠️写 `mode: subgraph` 旧格式(违 D7) · `SubgraphInline.tsx` ⚠️假数据 · `AssetsPanel.tsx` ⚠️读 `sub_skill_ref` 旧形态 | drafted |
| `compile-stage-gate` | 03_compile(owner=compile-lint，PM 已决) | gate 规则→`compile-lint`(owner) · 触发 UI→`center-action-bar` · gate 影响→`predict`/`run-execution`(消费、不重写) · 报错呈现→`compile-lint`(drawer) · 状态源→`state-engine` | `Workspace.tsx:onPredict/onRun` ⚠️console.info 桩 · `CompileErrorPanel` ⚠️底部浮层 vs drawer 决策(DEF-010) | drafted |
| `predict-execution` | 04_run-and-verify | predict 模式机制→`predict`(owner) · 入口 UI→`center-action-bar` · 干跑 mock→`engine:06-seam/01-models`(引) | `Workspace.tsx:onPredict` ⚠️未接 `postPredictRun` | drafted |
| `run-execution-node-status` | 04_run-and-verify | run 机制 + **批量/循环触发与展示**→`run-execution`(owner;循环原语→`engine:04-run-outer/02-iterate` 引) · 节点灯/边 UI→`canvas` · **事件→节点态投影**→`state-engine`(owner) · 事件源→`engine:02-observability`(引) | `Workspace.tsx:onRun` ⚠️桩 · `GraphCanvas:statusByNodeId` ⚠️非真实 run 态 · `build-nodes.ts:buildNodes` ⚠️默认首节点/假态 · WS bridge 未建 | drafted |
| `golden-per-agent-node` | 04_run-and-verify（golden-eval 段） | studio golden 编辑/diff→`golden-eval`(owner) · 落点→`engine:physical-layout`(.workspace/golden，引) · eval→`engine:05-run-inner/06-golden-eval`(引) · run 播种→`run-execution` · copilot bar→`copilot-assist` | `golden_diff.py:set_golden_baseline_for_run` ⚠️复制整次 final_state(违 per-node 目标) | drafted |
| `compile-lint-structured-error` | 03_compile(DEF-010) | drawer 呈现→`compile-lint`(owner) · 底部布局与 trace 协调→`timeline` | `Workspace.tsx:CompileErrorPanel` ⚠️底部浮层/toast vs drawer | drafted |
| `phase-field-whitelist` | 02_authoring | 字段白名单/Properties→`phase-editing`(owner) · 字段权威→`engine:skill-syntax`(引) | `phase-frontmatter.ts:parsePhaseForm` ⚠️读写 V2.x `mode/system_prompt/exit_contract/python_callable` 旧格式 · `PropertiesPanel.tsx` ⚠️stale phase form + edge JSON dump | drafted |
| `node-properties-role-test` | 00_settings-ux-spec §2.7（#11） | role 测试 / 状态投影机制→`studio-settings`(owner，复用 §2.5 测试 + §2.4 role-fit) · 节点 Properties UI(role 旁 Test 键 + 状态)→`phase-editing` / `properties`(落点) | 后端 `llm.py:POST /api/llm/roles/{name}/test`(live) · 前端 Properties role 行 Test+状态 ⚠️未建(DEF-013) | drafted |
| `conflict-overwrite-resolution` | 02_authoring | 冲突呈现→`conflict-overwrite`(owner) · 触发面→`canvas`/`editor`/`file-editing`(消费) | `canvas-authoring.ts:handleSaveConflict`(与顺序覆盖 overlay 两条 UX 未统一) | drafted |
| `debug-resume-checkpoint` | 05_debugging 场景C | 节点级 resume UI→`debug-resume`(owner) · checkpoint/resume→`engine:04-run-outer/03-checkpoint`(引) | `runs.py:resume_run` ⚠️501(DEF-005) | drafted |
| `trace-dot-blackboard` | 04_run-and-verify | dot/黑板语义→`trace-observability`(owner) · dot 渲染→`canvas` · inspector→`properties`/`timeline` · 只读消费→`editor`/`debug-resume` · 事件源→`engine:02-observability`(引) | `ContextEdge.tsx:getMockEdgeContext` ⚠️假黑板 · `TracePanel`/`useRunStream` ⚠️建了未挂载 | drafted |
| `native-rust-writer` | 全局 D12 | 唯一写者→`native-fs`(owner) · spans 所有本地写：`file-editing`/`editor`/`publish`/`skill-workspace`(消费) | `client.ts:writeSkillFile` ⚠️走 FastAPI 非 Rust · `artifact_registry.py:build_publish_package` ⚠️Py 打 zip · `tauri.ts:open_in_cursor/terminal/codex` ⚠️D3 死代码 | drafted |
| `workspace-open-folder-mru` | 01_workspace | 工作区/MRU/Remove→`skill-workspace`(owner) · 落盘→`native-fs` · Home UI→`welcome` | `skills.py:import_existing` ⚠️GRAPH/SKILL 门禁(违 D11/D2) · `skills.py:list_skill_summaries` ⚠️注册表聚合 · `WelcomePage.tsx` ⚠️读 `/skills` 注册表 | drafted |
| `io-panel-artifacts-test-inputs` | 02_authoring/04 | i/o 面板→`input`(owner) · 切面消费→`phase-editing`/`predict`/`run-execution` | `InputPanel.tsx:inputFiles` ⚠️假 `input/schema.json` · `test_inputs.py:create/delete_test_input` ⚠️501 | drafted |
| `publish-artifact-autocommit` | 06_eval | 发布/Artifact Registry→`publish`(owner) · 落盘→`native-fs` · 快照→`local-history` · 区分「发布≠git push，autocommit=本地存档」 | `skills.py:publish_skill` · `artifact_registry.py:build_publish_package` ⚠️Py zip | drafted |
| `local-history-snapshot` | 05_debugging | **快照列表/显示**→`local-history`(owner,只显示) · **快照写机制**→`publish-artifact-autocommit`/`native-fs`(引,非本单元) | `HistoryPanel.tsx` ⚠️仅 git snapshot，run detail/batch 未接 | drafted |
| `settings-six-state-provider-health` | 00_settings(`00_settings-ux-spec.md:255` 锁 6 态) | **6 态标准投影(内核)→`graph-agent-gateway`(③b,引)** · role-fit 消费 + UI 渲染→`studio-settings`/`settings`(③a) | `LlmRolesTab.tsx:roleTestStates`/`CopilotTab.tsx:routeStatusOverrides` ⚠️前端易失真相 · `llm.py:_role_test_jobs` ⚠️内存 job store · ⚠️`llm_state_projection.py` 6态投影该下沉 ③b | drafted |
| `model-group-role-materialization` | 00_settings §2 | **materialize 编排 + model group/endpoint 标准化(内核)→`graph-agent-gateway`(③b,引)** · UI 编辑角色/绑定 + 把角色结构交 ③b 物化→`studio-settings`/`settings`(③a) · HTTP 壳→`gateway` platform(③a 适配壳) | `llm.py:router` ⚠️巨型路由(HTTP glue+probe+materialize+draft 混,materialize/draft 内核该下沉 ③b) · `llm_import_drafts.py:sync_remote_evidence_library` ⚠️直接 `os.getenv` | drafted |
| `copilot-sdk-test-parity` | 00_settings §3 | copilot 测试=真实 SDK 调用→`copilot-assist`(③a,owner;拥有 SDK 运行时,测试须同路) · `copilot_chat` route 解析→`graph-agent-gateway`(③b,引) · HTTP 壳→`llm-copilot-http-api`(③a) | `llm.py:_probe_copilot_sdk_tool_call` ⚠️走 `AsyncAnthropic`，真实 chat 走 `ClaudeSDKClient`，测试路径不等价 | drafted |
| `copilot-session-persistence` | 03/copilot | session 持久化(D8)→`copilot-assist`(owner) · 消息渲染(含 ThinkingBlock 翻译/@mention)→`copilot-assist` · 安全写盘→`native-rust-writer`(引) · UI→`copilot` region | `copilotStore.ts:reset` ⚠️内存态，未满足 D8 持久化 · `copilot.py:_translate_sdk_message` ⚠️未翻 ThinkingBlock · Settings Copilot ⚠️仍依赖 `mock-copilot-data.ts` | drafted |
| `shell-runtime-gate` | 00_shell | 外壳即时渲染/sidecar(D10)→`shell-layout`(owner) · settings overlay/copilot slot | `App.tsx:RuntimeGate` ⚠️全屏 gate(违 D10 eager sidecar) | drafted |
| `i18n-error-code-ui-copy` | 04_platform/i18n(DEF-015) | i18n 架构(前端单权威)→`i18n`(owner) · 收编错误码→`studio-settings`/各 region 消费 | `llm-error-messages.ts:composeTestErrorMessage` ⚠️仅英文 catalog，react-i18next 骨架未落 | drafted |

## 重复 owner 风险（待 retrofit 时按本表「切面 × owner」消解）
- **stage gate**：`compile-lint` / `center-action-bar` / `predict` / `run-execution` / `state-engine` 都描述 Compile→Predict→Run 链 → owner=`compile-lint`(gate 规则)，其余消费、不重写。
- **6 态 / materialize(内核归 ③b)**：**6 态标准投影 + materialize 编排 + endpoint 标准化 = ③b `graph-agent-gateway`**(公共内核,studio 只引不复制);`studio-settings`/`settings`(③a)只做 UI 编辑 + 消费投影;`gateway` platform = ③a HTTP 壳。**(2026-06-05 改回四层反转:内核归 ③b,不挂 studio-settings)**
- **trace dot / 节点态**：`trace-observability`(语义) / `state-engine`(事件→态) / `canvas`(渲染) 各占一切面，勿混。
- **D12 本地写**：唯一 owner=`native-fs`，所有写者引它。
- **golden**：`golden-eval`(studio 编辑/diff) vs `engine:physical-layout`(落点) vs `engine:06-golden-eval`(eval) 切清。

## 真空 / 债
- 当前所有单元 `binds_code` 多为 ⚠️ drift（现状 ≠ 目标）；按 decision-3 忠实落进各 baseline + 警告，**不改代码**。
- 所有 `unit-lock=drafted`：INDEX 在、机器(units/binds/status/哈希锁)未接 → 任何横切单元都不能宣称 locked。
- `†` 标的 owner 待 retrofit 时按真实正文复核。
