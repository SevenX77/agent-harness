---
module: 04_platform/engine
doc: mvp1-alignment
status: drafted（Studio 已消费 compile/predict/run/trace 部分 engine 能力；resume 仍 501，engine contract 应引用 `docs/engine/mvp1/` SSOT，不在 Studio 重写 ⚠️。；目标结构已按 R4-R8 retrofit）
binds_baseline: ./baseline.md
units: [compile-stage-gate, predict-execution, run-execution-node-status, trace-dot-blackboard, golden-per-agent-node, debug-resume-checkpoint, subgraph-path-inline-drilldown, phase-field-whitelist]
aligns_with: docs/engine/mvp1/（engine-owned contract SSOT）· 01_workflows/03_compile.md · 01_workflows/04_run-and-verify.md · 01_workflows/05_debugging.md
---

# engine — MVP1 Alignment

> **Tier**: platform | **Owns**: Studio 对 engine SSOT 的引用边界；engine 自身契约 owner 在 `docs/engine/mvp1/`，本档不复制 | **现状**: Studio 已消费 compile/predict/run/trace 部分 engine 能力；resume 仍 501，engine contract 应引用 `docs/engine/mvp1/` SSOT，不在 Studio 重写 ⚠️。 | **Related**: [baseline](./baseline.md)（双向）· `compile-lint` · `predict` · `run-execution` · `trace-observability` · `golden-eval` · `debug-resume` · `graph-authoring` · `phase-editing` · `docs/engine/mvp1/`

## 1. 定义
`engine` is the graph-agent Python sidecar platform block: compile/lint, predict, run, trace event production, run artifacts, golden/diff support, and future debug resume semantics.

Source workflow basis: `01_workflows/03_compile.md:22`, `01_workflows/04_run-and-verify.md:144`, `01_workflows/05_debugging.md:38`.

## 2. 数据流 / 机制（设计细节）
### F1. Compile/Lint Authority

- 机制: engine validates structure, fields, topology, IO data flow, mentions, and returns structured errors.
- 决策: Studio triggers and presents; it should not invent a parallel compiler.
- 原话/来源: `01_workflows/03_compile.md:22` lists engine compile checks; `01_workflows/03_compile.md:30` keeps error codes engine-owned.
- 测试: invalid graph returns file/line/field/severity enough for canvas/properties/editor markers.
- Status: live with metadata expansion likely needed.
- 归属: platform `engine`; capability `compile-lint`.

### F2. Predict Semantics

- 机制: predict validates schema, executes logic nodes, and mocks agent nodes without real token burn.
- 决策: predict is the hard precondition for run; golden only changes mock source.
- 原话/来源: `01_workflows/04_run-and-verify.md:23`, `01_workflows/04_run-and-verify.md:24`, and `01_workflows/04_run-and-verify.md:29` define semantics.
- 测试: logic runs real code; agent uses placeholder/golden; no provider route is called for mock.
- Status: partial live.
- 归属: platform `engine`; capability `predict`, `golden-eval`.

### F3. Run And Artifacts

- 机制: run executes real graph, writes final_state/metrics/trace/checkpoints/artifacts.
- 决策: run burns real tokens and is downstream of predict.
- 原话/来源: `01_workflows/04_run-and-verify.md:48` lists run artifacts; `01_workflows/04_run-and-verify.md:71` defines run tests.
- 测试: run artifacts exist; failed run records error payload; successful run can trigger autocommit.
- Status: live.
- 归属: platform `engine`; capability `run-execution`, `publish`.

### F4. Trace Event Schema

- 机制: emit enough structured runtime events for live stream, human-readable trace, dot transitions, prompt inspector, and node states.
- 决策: trace needs both node internals and between-node blackboard operations.
- 原话/来源: `01_workflows/04_run-and-verify.md:75` to `01_workflows/04_run-and-verify.md:81` define trace requirements; `01_workflows/04_run-and-verify.md:101` lists engine payload need.
- 测试: events include phase id/execution id, edge transition id, iteration/attempt/source where needed.
- Status: partial live; schema expansion needed.
- 归属: platform `engine`; capability `trace-observability`.

### F5. Per-node Golden And Diff

- 机制: maintain per-agent-node expected outputs and compare real output fields after run.
- 决策: replace whole-run captured snapshots.
- 原话/来源: `01_workflows/04_run-and-verify.md:131` and `01_workflows/04_run-and-verify.md:132` define the replacement.
- 测试: per-node golden storage; output schema invalidation; field diff by node.
- Status: target-design.
- 归属: platform `engine`; capability `golden-eval`.

### F6. Node-level Debug Resume

- 机制: resume from node/dot using valid upstream checkpoints, injected HitL answer, or tampered context.
- 决策: core difficulty belongs in engine.
- 原话/来源: `01_workflows/05_debugging.md:26` and `01_workflows/05_debugging.md:38` assign checkpoint/resume to engine.
- 测试: node X resume does not rerun upstream; dirty upstream invalidates downstream resume; HitL answer resumes.
- Status: target-design.
- 归属: platform `engine`; capability `debug-resume`.

## 3. 接口契约
- Compile returns structured errors for Studio contextual display.
- Predict runs logic and mocks agent nodes according to golden state.
- Run performs true execution and emits events/artifacts.
- Trace events must support node, edge/dot, loop/retry/batch grouping.
- Debug resume needs checkpoint and validity APIs.
- Capability links: `compile-lint`, `predict`, `run-execution`, `trace-observability`, `golden-eval`, `debug-resume`.

## 4. 设计决策基础（PM 原话）
- 核心方向无 PM 决策缺口。engine **内部设计细节**(编译机制、trace 事件 schema、checkpoint/resume API、golden→`.workspace` 落点等)在 **engine 自己的 mvp1 文档** `docs/engine/mvp1/`(contract + mechanism)——本 studio 侧文档只写 studio↔engine 契约,细节交叉引用过去、不在此重复(避免两份漂移)。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| ENGINE-1 | resume | 单元 `debug-resume-checkpoint`（引擎契约）；**为什么**：节点级 checkpoint/resume 归 engine `04-run-outer/03-checkpoint`，Studio 只引用 |
| ENGINE-2 | engine SSOT | 引用 `docs/engine/mvp1/` 各契约 SSOT(compile/run/golden/trace)；**为什么**：engine 是格式/错误码/机制权威，Studio 平台只消费不重定义(R1) |
| ENGINE-3 | golden/path/schema | 单元 `golden-per-agent-node`（引擎契约）；**为什么**：golden 落点/per-node 模型/失效校验归 engine `physical-layout`+`golden-eval`，Studio 引用 |

## 6. 测试关键点
1. resume: baseline 现状为 Studio `resume_run` 仍 501 ⚠️；目标为 节点级 resume 引用 engine checkpoint/resume contract 并接 Studio 适配。
2. engine SSOT: baseline 现状为 旧文/旧 prompt 容易被当 engine 需求 ⚠️；目标为 只引用 `docs/engine/mvp1/` 具体 contract/mechanism。
3. golden/path/schema: baseline 现状为 Studio 文档多处消费 engine-owned 契约；目标为 只写消费边界，落点/skill syntax/resolver 不复制。

## 7. 涉及 region / platform
`compile-lint` · `predict` · `run-execution` · `trace-observability` · `golden-eval` · `debug-resume` · `graph-authoring` · `phase-editing` · `docs/engine/mvp1/`

## 8. gaps / 报警
- 🚨 resume: Studio `resume_run` 仍 501 ⚠️；目标 节点级 resume 引用 engine checkpoint/resume contract 并接 Studio 适配。
- 🚨 engine SSOT: 旧文/旧 prompt 容易被当 engine 需求 ⚠️；目标 只引用 `docs/engine/mvp1/` 具体 contract/mechanism。

## 交叉引用（链接, 不复制）
[baseline](./baseline.md)（现状,双向）· `compile-lint` · `predict` · `run-execution` · `trace-observability` · `golden-eval` · `debug-resume` · `graph-authoring` · `phase-editing` · `docs/engine/mvp1/`
