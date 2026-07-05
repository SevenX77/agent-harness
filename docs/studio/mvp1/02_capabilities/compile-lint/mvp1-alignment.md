---
module: 02_capabilities/compile-lint
doc: mvp1-alignment
status: FROZEN（lint/compile 触发与 compile-pass stage live；错误仍是底部浮层/toast，drawer 与上下文标记未落 ⚠️。；目标结构已按 R4-R8 retrofit；2026-07-01 PM 增补 F6:触发语义扩画布拓扑改动 + lint 聚合完整性）
binds_baseline: ./baseline.md
units: [compile-stage-gate, compile-lint-structured-error]
aligns_with: 01_workflows/03_compile.md（lint / compile / stage gate）
---

# compile-lint — MVP1 Alignment

> **Tier**: capability | **Owns**: `compile-stage-gate`（gate 规则）+ `compile-lint-structured-error`（drawer 呈现） | **现状**: lint/compile 触发与 compile-pass stage live；错误仍是底部浮层/toast，drawer 与上下文标记未落 ⚠️。 | **Related**: [baseline](./baseline.md)（双向）· `center-action-bar` · `editor` · `properties` · `timeline` · `predict` · `run-execution` · `engine`

## 1. 定义
`compile-lint` owns real-time lint, manual compile, compile error display, and the Compile -> Predict -> Run stage gate.

Source workflow basis: `01_workflows/03_compile.md:7`, `01_workflows/03_compile.md:10`, `01_workflows/03_compile.md:26`.

## 2. 数据流 / 机制（设计细节）
### F1. Realtime Lint

- 机制: editor changes debounce, call lint, then publish status for the center action bar. Trigger semantics = **source truth mutation**: canvas topology writes (connect / disconnect / delete phase → GRAPH.md rewrite) trigger the same relint immediately after the write lands (see F6) — clearing stale projections without re-linting is a defect.
- 决策: real-time lint should mark context only, not flood the user with global panels while they are mid-edit.
- 原话/来源: `01_workflows/03_compile.md:13` defines the 800ms lint action; `01_workflows/03_compile.md:28` says real-time lint only marks context; 03_compile.md A13 + 决策(2026-07-01)define the canvas trigger.
- 测试: incomplete edit marks checking/failed without toast or drawer; empty content returns idle; canvas edge disconnect lights the island error on the node without opening the editor.
- Status: live mechanism, presentation target-design.
- 归属: capability `compile-lint`; region `editor`, `canvas`, `center-action-bar`.

### F2. Manual Compile Drawer

- 机制: clicking Compile runs full compile and opens a drawer with all errors, copyable details, and no sidebar coverage.
- 决策: keep the Compile button; change it from bottom floating panel to drawer.
- 原话/来源: `01_workflows/03_compile.md:18` defines the drawer; `01_workflows/03_compile.md:35` records the PM quote to remove the floating card.
- 测试: drawer lists every error with file/line/field/message; copy works; drawer does not cover side panels.
- Status: target-design. Current bottom panel must be removed.
- 归属: capability `compile-lint`; region `center-action-bar`; component target `Drawer`.

### F3. Contextual Error Locations

- 机制: compile errors map to canvas node badge, Properties/input field tooltip, and Monaco inline marker.
- 决策: errors should appear where the user can fix them.
- 原话/来源: `01_workflows/03_compile.md:15`, `01_workflows/03_compile.md:16`, and `01_workflows/03_compile.md:17` list the three locations; `01_workflows/03_compile.md:34` keeps the PM wording.
- 测试: the same engine error appears at its node, its field, and its file line when those surfaces are visible.
- Status: target-design.
- 归属: regions `canvas`, `properties`, `input`, `editor`; platform `engine`.

### F4. Stage Gate

- 机制: compile-pass unlocks Predict; predict-pass unlocks Run.
- 决策: run must be blocked until both structure and predict flight have passed.
- 原话/来源: `01_workflows/03_compile.md:20` defines the gate; `01_workflows/04_run-and-verify.md:10` repeats the spine.
- 测试: failing compile disables Predict and Run; passing compile enables Predict; failing predict keeps Run disabled.
- Status: compile gate live; predict-pass missing.
- 归属: capability `compile-lint`; capabilities `predict`, `run-execution`; region `center-action-bar`.

### F5. Engine Error Contract

2026-07-05 correction: blackboard data-gap diagnostics are engine compile/lint
diagnostics, not a Studio-only canvas projection. A phase input declared in
`io.inputs.properties` must be supplied by graph root input, upstream output,
`source:file`, or iterate/batch injection; otherwise engine emits
`[F-v3-graph-dataflow-source-missing]` with `field_path =
<phase>.io.inputs.properties.<field>`. Studio may still expose
`graph_topology[].field_supply` for Input-panel supply visualization, but must
not synthesize node compile errors from it.

- 机制: engine returns structured compile errors; Studio should not invent separate validation rules when engine can own them.
- 决策: compile check content and error codes stay engine-owned.
- 原话/来源: `01_workflows/03_compile.md:22` lists engine checks; `01_workflows/03_compile.md:30` says do not create Studio-only compile codes.
- 测试: engine errors survive through API to UI without losing file/line/field/severity.
- Status: backend live; some location metadata may need engine expansion.
- 归属: platform `engine`; capability `compile-lint`.

### F6. Lint Completeness (Full Aggregated Diagnostics)

- 机制: one lint/compile pass surfaces the engine's **entire aggregated defect set** for that pass — the engine collects per stage ("同阶段尽量聚合", engine compile-rules §2.1) and exposes the full set on the exception seam (`compile_result.issues`, each issue carrying explicit source_path/line/field_path axes); Studio's lint path expands every issue into `LintResult.errors`, exactly like the manual Compile drawer does. There is no "single-error consumer": realtime lint, drawer, node badges, field tooltips, and editor markers all project the same complete list.
- 决策: fixing one defect must not "reveal" the next defect of the same stage; independent defects (multiple islands, multiple unknown deps, multiple nodes missing blocks) appear together in one pass.
- 原话/来源: 2026-07-01 PM:"明明有问题的地方不弹报错……我把一个节点的线断开,没有报错""编译总是只弹个别错误,不完整……将role补上,goal的报错才出现"→ 定为触发语义 + 聚合完整性两条设计(03_compile.md 决策段 2026-07-01)。
- 测试: a graph with two islands + a node missing `<goal>` lints all three errors in one response; the lint surface and the Compile drawer show the same set.
- Status: target-design(本轮实现).
- 归属: platform `engine`(阶段内聚合 + issues 轴); capability `compile-lint`(lint 展开); regions `canvas` `properties` `editor`(投影)。

## 3. 接口契约
- Frontend lint sends changed markdown and receives pass/fail/error payload; `LintResult.errors` carries the full aggregated defect list of the pass (F6), never just the first error.
- Canvas topology writes (GRAPH.md rewrite) trigger the same lint call with the serialized content and replace all three projections with the new result (F1/F6).
- Manual compile calls engine-backed compile and receives structured errors with file, line, field, severity, and message.
- Center action bar gates Predict on compile-pass and Run on predict-pass.
- Region links: `center-action-bar`, `canvas`, `properties`, `editor`, `input`.
- Platform link: `engine`.

## 4. 设计决策基础（PM 原话）
- 编译 **warning 级不阻塞 Predict**(只 error 阻塞);warning 仅标记/提示,不挡试飞。
- 报错呈现 = 底部 drawer(只盖画布、一键复制 Copilot,自动弹;见 `center-action-bar`),标题/文案随实现定。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| COMPILE_LINT-1 | 错误呈现(drawer) | 单元 `compile-lint-structured-error`；**为什么**：错误要可一键复制喂 Copilot + 只盖画布不挡侧栏，底部 drawer 自动弹比 toast/浮层更可操作 |
| COMPILE_LINT-2 | 上下文定位 | 单元 `compile-lint-structured-error`；**为什么**：错误要出现在能改它的地方(canvas 节点 / Properties·input 字段 / Monaco 行)，而非只在中心按钮变色 |
| COMPILE_LINT-3 | stage gate | 单元 `compile-stage-gate`；**为什么**：warning 不阻塞 Predict、只 error 阻塞；Run 必须 structure + predict 双过才解锁，防跑废 |

## 6. 测试关键点
1. 错误呈现: baseline 现状为 `CompileErrorPanel` 仍是底部浮层/toast ⚠️；目标为 Compile drawer 自动弹出、可复制、只盖画布。
2. 上下文定位: baseline 现状为 主要只有按钮颜色/toast/浮层 ⚠️；目标为 同一错误投到 canvas 节点、Properties/input 字段、Monaco 行。
3. stage gate: baseline 现状为 compile-pass 可驱动 Predict；predict-pass 未置位导致 Run 链路断 ⚠️；目标为 warning 不阻塞 Predict；error 阻塞；predict-pass 解锁 Run。

## 7. 涉及 region / platform
`center-action-bar` · `canvas` · `editor` · `properties` · `input` · `timeline` · `predict` · `run-execution` · `engine`

## 8. gaps / 报警
- 🚨 错误呈现: `CompileErrorPanel` 仍是底部浮层/toast ⚠️；目标 Compile drawer 自动弹出、可复制、只盖画布。
- 🚨 上下文定位: 主要只有按钮颜色/toast/浮层 ⚠️；目标 同一错误投到 canvas 节点、Properties/input 字段、Monaco 行。
- 🚨 stage gate: compile-pass 可驱动 Predict；predict-pass 未置位导致 Run 链路断 ⚠️；目标 warning 不阻塞 Predict；error 阻塞；predict-pass 解锁 Run。

## 交叉引用（链接, 不复制）
[baseline](./baseline.md)（现状,双向）· `center-action-bar` · `editor` · `properties` · `timeline` · `predict` · `run-execution` · `engine`
