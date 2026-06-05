# Studio MVP1 Claude Work Audit Report

日期: 2026-06-05

范围: 按 `docs/design/studio-mvp1-claude-work-audit-prompt.md` 对 Claude 本轮 `docs/studio/mvp1/` 修改做对抗式复核。裁决以 `docs/studio/mvp1/DESIGN_UNITS_INDEX.md` 为准, 不采信 `docs/design/studio-mvp1-decision-table-fix.md` 的自述。

## 总结论

- **A 单元归位: 未完全修净。** 旧的 11 个明显 Q3 漂移大多已改, 但仍有多处把 **消费/引用切面写成 owner 口吻**; 另有 frontmatter `units:` 把消费/引用单元混入, 造成 R8 归属污染。
- **B 动机真实性: 旧模板句未见残留。** `rg` 未发现“对齐 X 设计单元, 保证实现与测试可回扣”类句式; 存疑点主要是单元归属错误导致动机挂错 owner, 不是单独的套话。
- **C 6 个 P0: 5 个修净, 1 个未修净。** S-03 HitL 仍在 workflow 决策原话区保留“顶部问题框”残留。
- **D inline 忠实度: 未达“逐字原文”。** `_reorg` 全树零引用成立, 但 D7/G2/G3/D10/D12 多处是节选、压缩或转述, 不是忠实 inline 原话。
- **E migration 抽查: 8/8 未见真漏迁。** 抽样 drift 概念均能在 baseline 测试锚点或正文找到追踪。
- **F 新错误: 未发现机械 schema/链接/predict 改坏; 新问题集中在语义层。** 63 档 frontmatter 基础字段完整、无 `lock:`、相对链接 0 断、predict 当前无 diff。

## A. §5 单元归错 / 消费误标

### A1. 高可信归属问题

| 模块 / 行 | Claude 写法 | 正确裁决 | 依据 |
|---|---|---|---|
| `02_capabilities/file-editing/mvp1-alignment.md:78-79` | `FILE_EDITING-1/2` 写 `native-rust-writer` 且无消费标记 | file-editing 是本地写的**消费方**, 正确应标 `native-rust-writer`（消费）, 不应像 owner | `DESIGN_UNITS_INDEX.md:32` 写唯一写者 owner=`native-fs`, `file-editing` 在“所有本地写”中为消费 |
| `03_regions/editor/mvp1-alignment.md:77` | `EDITOR-1` 写 `native-rust-writer` 且无消费标记 | editor save 是 Rust 写者的消费 / 落点, owner 仍是 `native-fs` | `DESIGN_UNITS_INDEX.md:32` 明确 `editor` 属消费 |
| `02_capabilities/skill-workspace/mvp1-alignment.md:81` | `SKILL_WORKSPACE-3 子图 membership` 写 `subgraph-path-inline-drilldown` | `skill-workspace` 不在该 unit spans; 若讲 workspace membership, 应归 `workspace-open-folder-mru`; 若讲子图 path, 至多标 `subgraph-path-inline-drilldown`（消费/引用） | `DESIGN_UNITS_INDEX.md:21` 的 subgraph spans 无 `skill-workspace`; `:33` 才是 workspace owner |
| `02_capabilities/trace-observability/mvp1-alignment.md:89` | `TRACE_OBSERVABILITY-3 节点态` 写 `run-execution-node-status` | trace 只拥有 dot/黑板语义; 节点态投影 owner 是 `state-engine`, trace 这里只能消费 | `DESIGN_UNITS_INDEX.md:24` 写事件→节点态投影→`state-engine`; `:31` 写 trace owns dot/黑板语义 |
| `02_capabilities/studio-settings/mvp1-alignment.md:91` | `STUDIO_SETTINGS-3 Copilot test` 写 `copilot-sdk-test-parity` | settings 只是配置/触发面; `copilot-sdk-test-parity` owner 是 `copilot-assist`, HTTP 壳是 `llm-copilot-http-api` | `DESIGN_UNITS_INDEX.md:39` |
| `03_regions/settings/mvp1-alignment.md:88` | `SETTINGS-3 Copilot settings` 写 `copilot-sdk-test-parity` | settings region 是消费/配置 UI, 不是该 unit owner | `DESIGN_UNITS_INDEX.md:39` |
| `03_regions/timeline/mvp1-alignment.md:86` | `TIMELINE-2 run detail` 写 `run-execution-node-status` 且无消费标记 | timeline row/detail 是运行信息落点, 但 INDEX 未给 timeline 该 unit owner; 至少应标消费, 或先补 INDEX | `DESIGN_UNITS_INDEX.md:24` 仅列 `run-execution` / `canvas` / `state-engine` / engine |
| `03_regions/properties/mvp1-alignment.md:67` | `PROPERTIES-1 字段表单` 写 `phase-field-whitelist` 且无消费/落点标记 | `phase-field-whitelist` owner 是 `phase-editing`; properties 是 UI 落点, 不应自称 owner | `DESIGN_UNITS_INDEX.md:27` |
| `04_platform/state-engine/mvp1-alignment.md:76` | `STATE_ENGINE-1 状态源` 用 `run-execution-node-status` 覆盖 stage/node/provider/sidecar | 这一行把四类状态混成一个 unit: stage 应看 `compile-stage-gate`; node 才是 `run-execution-node-status`; provider 对应 settings/gateway; sidecar 对应 `shell-runtime-gate` | `DESIGN_UNITS_INDEX.md:22`, `:24`, `:37`, `:41` |

### A2. frontmatter `units:` 污染 / §5 落点不完整

- `04_platform/native-fs/mvp1-alignment.md:6` 把 `local-history-snapshot`、`copilot-session-persistence` 等引用/消费单元放进 `units:`; §5 只落了 native writer / publish / shell gate。INDEX 中 local history owner 是 `local-history`, copilot session owner 是 `copilot-assist` / `copilot` region。证据: `DESIGN_UNITS_INDEX.md:36`, `:40`。
- `04_platform/engine/mvp1-alignment.md:6` 把 8 个 engine 相关 unit 全塞进 `units:`; §5 只有 resume、engine SSOT、golden/path/schema 三行。INDEX `:13` 要求 engine-owned 契约只引用 `docs/engine/mvp1/` SSOT, 不在 Studio 复制。
- `03_regions/timeline/mvp1-alignment.md:6` 有 `compile-lint-structured-error`, 但 §5 没有对应行; 正文 `:12` 声称 owns 布局协调。若按 INDEX `:26`, timeline 的确有底部布局/trace 协调切面, §5 应单独落。
- `03_regions/editor/mvp1-alignment.md:6` 有 `trace-dot-blackboard`, 但 §5 没有 trace 行; INDEX `:31` 写 editor 是 trace 的只读消费。
- `03_regions/settings/mvp1-alignment.md:6` 有 `i18n-error-code-ui-copy`, 但 §5 没有 i18n 行; INDEX `:42` 写 i18n owner=`i18n`, settings/regions 消费。
- `02_capabilities/phase-editing/mvp1-alignment.md:6` 有 `io-panel-artifacts-test-inputs`, 但 §5 没有该 unit; INDEX `:34` 写 phase-editing 是消费。
- `02_capabilities/predict/mvp1-alignment.md:34-39` 仍是旧 gold 范例写法, §5 没有 `predict-execution` 单元名。该文件当前无 diff, 不算 Claude 本轮新增错误, 但按 A.3 仍是 unit 在 §5 不落的问题。

## B. 动机真实性

`rg` 未发现以下旧套话残留: `对齐.*设计单元`、`保证.*可回扣`、`可回扣`。抽查 compile-lint、golden-eval、debug-resume、local-history、shell-layout、studio-settings、state-engine、timeline、native-fs、properties 后, 动机大多能解释具体决策。

存疑项:

- `04_platform/state-engine/mvp1-alignment.md:76`: “stage/node/provider/sidecar 状态要有清晰单源”是真动机, 但挂到单一 `run-execution-node-status` 与决策实质不一致。
- `03_regions/timeline/mvp1-alignment.md:86`: “run 历史归 timeline”符合 UI 直觉, 但 INDEX 没给 timeline `run-execution-node-status` owner, 应标消费或补 INDEX。
- `03_regions/copilot/mvp1-alignment.md:82`: “analysis bar”被挂到 `copilot-session-persistence`; 若指 golden/诊断入口, INDEX 更接近 `golden-per-agent-node` 的 copilot bar 或 `copilot-assist` 能力切面。证据: `DESIGN_UNITS_INDEX.md:25`, `:40`。

## C. 6 个 P0 复验

| ID | 结论 | 证据 |
|---|---|---|
| S-01 predict Kiro SSOT 泄漏 | **PASS** | `rg kiro` 在 predict alignment 无命中; 全树仅 README / workflow 把 `.kiro` 标为历史参考、不作 SSOT。证据: `docs/studio/mvp1/README.md:4`, `01_workflows/02_authoring.md:5` |
| S-02 golden-eval/properties 正向 link | **PASS** | golden-eval 写 `properties` 不在入口: `02_capabilities/golden-eval/mvp1-alignment.md:63`, `:79`, `:90`; properties 明确负向: `03_regions/properties/mvp1-alignment.md:49-52`, `:57`, `:59`, `:62`, `:69` |
| S-03 HitL 顶栏残留 | **FAIL 未修净** | debug-resume 已改: `02_capabilities/debug-resume/mvp1-alignment.md:40`, `:73`; workflow F4 已改: `01_workflows/05_debugging.md:17`; 但同 workflow 决策区仍写“顶部问题框”: `01_workflows/05_debugging.md:34` |
| S-04 local-history aligns_with | **PASS** | frontmatter 已对齐 `06_eval` + `04_run-and-verify`, 不再挂 `05_debugging`: `03_regions/local-history/mvp1-alignment.md:7` |
| S-05 properties golden optional summary | **PASS** | inputs / capability link / §5 都为负向边界, 未见 `optional golden diff summary`: `03_regions/properties/mvp1-alignment.md:57`, `:59`, `:62`, `:69` |
| S-06 shell-layout Header breadcrumb | **PASS** | Header 测试只留 Back Home/Release; breadcrumb 归 canvas: `03_regions/shell-layout/mvp1-alignment.md:31-34`; canvas 左上角: `03_regions/canvas/mvp1-alignment.md:53-54` |

## D. `_reorg` inline 忠实度

### D1. 零引用

`rg "_reorg|alignment-notes|alignment notes" docs/studio/mvp1 -S` 无命中, 所以 **mvp1 全树零引用 `_reorg` / `alignment-notes` 成立**。

### D2. inline 失真 / 有损压缩

| 位置 | 问题 | 原文依据 |
|---|---|---|
| `01_workflows/02_authoring.md:38` D7 | 用省略号压缩原话, 且引号里漏掉 “唯一要注意的是 copilot 的工作目录范围要把 subgraph 的子图 path 加进去” 这个关键约束 | `_reorg/alignment-notes.md:57-61` |
| `01_workflows/02_authoring.md:39` G2 | 把 G2 原话压成“父子图 io 不绑死 + 任意 i/o 导入 + 时机=a”; 结论方向对, 但不是逐字原文, 且 a 是后续锁定, 不是 G2 原句本身 | `_reorg/alignment-notes.md:251-255`, `:274-276` |
| `01_workflows/02_authoring.md:40` G3 | 直接转述为规则, 未 inline 原话; 漏掉“黑板肯定都得进”“落盘是并行需求不影响状态机”“一 schema 多文件/多 schema 多文件”等动机与边界 | `_reorg/alignment-notes.md:256-260` |
| `04_platform/native-fs/mvp1-alignment.md:72` D10 | 引号内写 `gateway... python sidecar`, 属明显节选; 漏掉 studio backend llm gateway 并入 gateway、前两块是引擎真跑调用服务、以及“判断是否可行/不需要 bootstrap”等上下文 | `_reorg/alignment-notes.md:72-80`, `:90-97` |
| `04_platform/native-fs/mvp1-alignment.md:73` D12 | 只摘了核心短句, 后半“skill 源文件 / .workspace / copilot patch...”是 notes 的解释性 bullet, 不是同一句 PM 原话; 作为摘要可读, 但不满足“逐字原文 inline” | `_reorg/alignment-notes.md:202-209` |

D3/D6/D9 在 `01_workflows/01_init.md:41-43` 与 `_reorg/alignment-notes.md:25-38`, `:68-70` 基本一致, 未见实质曲解。

## E. migration drift 抽查

抽查 8 个 drift 概念, 未见真漏迁:

| drift 概念 | 是否追踪 | 证据 |
|---|---|---|
| `SchemaInferPanel` / schema infer 只读 | PASS | `03_regions/input/baseline.md:21`, `:33`; `02_capabilities/phase-editing/baseline.md:29` |
| `SubgraphInline` mock rows | PASS | `02_capabilities/graph-authoring/baseline.md:29`, `:43`; `03_regions/canvas/baseline.md:25`, `:53` |
| `useGoldenDiff` route mismatch | PASS | `02_capabilities/golden-eval/baseline.md:22`, `:32` |
| `TracePanel` / `useRunStream` orphan | PASS | `02_capabilities/trace-observability/baseline.md:21-22`, `:43`; `03_regions/timeline/baseline.md:23`, `:26`, `:51` |
| `RuntimeGate` full-screen gate | PASS | `03_regions/shell-layout/baseline.md:26`, `:51`; `04_platform/state-engine/baseline.md:18`, `:54` |
| `build_publish_package` Python zip | PASS | `02_capabilities/publish/baseline.md:29`, `:42`; `04_platform/native-fs/baseline.md:58` |
| `test_inputs` create/delete 501 | PASS | `03_regions/input/baseline.md:52`; alignment 也落到 `03_regions/input/mvp1-alignment.md:89`, `:94` |
| `resume_run` 501 | PASS | `02_capabilities/debug-resume/baseline.md:30`, `:43`; `04_platform/engine/baseline.md:49` |

结论: Claude 的 “58 个 drift 符号无真漏迁” 在本次 8 项抽样中成立; 本报告未全量复算 58/58。

## F. 新错误 / 机械检查

- frontmatter schema: **PASS**。脚本检查 63 档 baseline/alignment/i18n, 均有 `units:`; baseline 均有 `binds_alignment` + `binds_code`; alignment 均有 `binds_baseline`。
- `lock:` 字段: **PASS**。`rg "^lock:" docs/studio/mvp1` 无命中。
- 相对链接: **PASS**。脚本解析 markdown 相对链接, broken=0。
- predict gold: **PASS**。`git diff --name-only -- docs/studio/mvp1/02_capabilities/predict...` 无输出, 当前工作树未改 predict gold。

新增问题不是机械 schema, 而是:

1. frontmatter `units:` 把消费/引用单元混入 owner 列表, 见 A2。
2. HitL workflow 残留“顶部问题框”, 见 C/S-03。
3. `_reorg` 原话 inline 多处有损压缩, 见 D2。
