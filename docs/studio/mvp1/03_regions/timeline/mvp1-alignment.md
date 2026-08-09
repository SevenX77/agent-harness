---
module: 03_regions/timeline
doc: mvp1-alignment
status: FROZEN（2026-08-07 viewed-run 决议落地:本区域三视图=运行列表/所查 run 的 Trace 视图/EdgeContext,由 Workspace viewedTrace 状态分流;run 结束可返回列表;predict 以 kind 判别入列。2026-08-09 D1 决议:区域改名 **Trace**（Toolbar 第4格,PanelKind 值 `trace`）,独立 `Full Trace` 文档面板删除——"Timeline"与"Full Trace"两个名词退役;D12:点击画布空白不再关闭本区域面板;D9:运行列表行改为「类型图标 / 完整 run_id / 状态徽章」三段(F1);D8:报告改为两个入口——Trace 末尾终结条目 + 列表行链接(新增 F7),身份条 `⋮` 的报告项删除;F3(Full Trace)已作废、F4(Prompt Inspector)已改址。决议:docs/design/2026-08-07-timeline-viewed-run-and-trace-ui-decision.md、docs/design/2026-08-09-trace-ia-and-streaming-overhaul-decision.md；目标结构已按 R4-R8 retrofit）
binds_baseline: ./baseline.md
units: [compile-lint-structured-error, trace-dot-blackboard, run-execution-node-status]
aligns_with: 01_workflows/04_run-and-verify.md（run history / trace）· 01_workflows/03_compile.md（compile drawer coordination）
---

# timeline — MVP1 Alignment

> **Tier**: region | **Owns**: `trace-dot-blackboard` inspector/trace 切面 + `run-execution-node-status` 历史/trace 显示 + `compile-lint-structured-error` 布局协调切面 | **现状**: viewed-run 模型已落地(2026-08-07):列表行点击进该 run 的 Trace 视图(历史一次性拉取,该 run 的所有读者共读同一事件源),live run 流式复用同一视图并带返回;predict 行以 `RunMetadata.kind` 判别、仅 icon 区分。2026-08-09 D1 起区域名为 **Trace**,不再有第二个 trace 面。 | **Related**: [baseline](./baseline.md)（双向）· `trace-observability` · `run-execution` · `compile-lint` · `golden-eval` · `copilot-assist`

## 1. 定义
本区域(Toolbar 第 4 格,名为 **Trace**)owns time-based runtime inspection: run/predict history, live trace stream, run-after replay of one run's full trace, model comparison tabs, and selected run summary. 自 2026-08-09 D1 起它是**唯一**的 trace 面——通读与定位由同一个视图承担,不再有独立的 `Full Trace` 文档面板。

Source workflow basis: `01_workflows/04_run-and-verify.md:75`, `01_workflows/04_run-and-verify.md:79`, `01_workflows/04_run-and-verify.md:83`.

## 2. 数据流 / 机制（设计细节）
### F1. Run/Predict History List

- 机制: list predict and run attempts with status, timing, token metrics, and detail entry。
  **行的形态自 2026-08-09 D9 起固定为三段**:
  1. **行首 = 类型标记**,只回答「这是 run 还是 predict」——run = `Play`,predict = `FlaskConical`,
     **中性色**,不随成败变色;
  2. **完整 `run_id`**,不截断(长 id 换行,不用省略号);
  3. **状态徽章**,与 Trace 顶条**同一套图标词表**(`utils/run-status-mark.ts` 的 `runStatusMark`,
     见 `trace-observability` F8),文字进 tooltip 与 aria-label。
  外加一行 `耗时 · token` 与相对时间,以及本次运行的**报告链接**(见 F7)。
- 决策: run-after review starts from a run_id row。三段形态的理由是**一个位置只回答一个问题**:
  旧行把类型与状态挤在同一个行首图标里——predict 用带状态色的烧瓶、run 直接用状态图标——
  于是同一个位置有时说「这是一次预演」、有时说「这次成功了」,读者无法只看一眼就分辨;
  `run_id` 又被截成 12 字符,而 D13 之后 id 本身就是「时间戳_uuid8」,截断恰好切掉了可读的那一半。
- 原话/来源: `01_workflows/04_run-and-verify.md:52` lists run history; `01_workflows/04_run-and-verify.md:81` defines clicking a run to see summary;
  决策 `docs/design/2026-08-09-trace-ia-and-streaming-overhaul-decision.md` D9;
  PM 原话(2026-08-09):「主页上,run id给我显示全了,和里面一样,run id 加上后面的状态徽章。
  最前面不要把状态和run、predict徽章混在一起,predict和run的图标固定一个」。
- 测试: run row opens selected run summary; refresh updates rows; empty state is clear;
  完整 run_id 出现在行内且不含 `...`;失败 run 的类型标记仍为中性色;
  状态徽章的 aria-label 与顶条一致。
- Status: live(2026-08-07:行点击经 Workspace.handleSelectRun 打开该 run 的 Trace 视图;
  predict 行以 kind 判别入列;run 结束由 archive 效果把终态 metadata 投影回列表。
  2026-08-09 D9:三段形态落地,`RunTypeMark` / `RunStatusBadge` 取代旧 `RunRowIcon`)。
- 归属: region `timeline`; capability `run-execution`.

### F2. Live Trace Auto-open

- 机制: starting Run opens the timeline/trace panel and streams events.
- 决策: user should see tracing live while the graph runs.
- 原话/来源: `01_workflows/04_run-and-verify.md:79` and `01_workflows/04_run-and-verify.md:86` define live trace.
- 测试: Run opens panel; events append live; reconnection does not duplicate events.
- Status: live(gate started(predict 与 run 同权)→ follow-run + open-trace(gate-state.ts);流式列表贴底跟随走 message-scroller;返回按钮任何时刻可回列表——2026-08-07 viewed-run 决议修复「跑过一次后列表不可达」)。
- 归属: region `timeline`; capability `trace-observability`.

### F3. Full Trace Timeline And Editor（已作废）

- 机制: ~~from a run summary, open full timeline and formatted read-only editor document.~~
- 决策: **2026-08-09 D1 作废本条**。第二个 trace 面与本区域的 Trace 视图职责重复——
  本区域本来就该显示完整 trace,再开一个「完整版」等于承认主视图是删节版。
  `TraceDocumentPanel` 与 `trace-doc` 面板已删除。
- 原话/来源: 决策 `docs/design/2026-08-09-trace-ia-and-streaming-overhaul-decision.md` D1;
  PM 原话(2026-08-09):「full trace删掉,功能重复,本来就应该显示full tracing」。
- 测试: `TraceDocumentPanel` / `trace-doc` 在 `apps/studio/frontend/src` 中 grep 为 0 命中。
- Status: deleted(2026-08-09)。
- 归属: region `timeline`; capability `trace-observability`.

### F4. Prompt Inspector（已改址）

- 机制: ~~clicking an LLM call opens Template/Variables/Rendered prompt inspector.~~
  Template / Variables / Rendered 现在**就在 LLM 步骤条目内**展开,没有第二个入口。
- 决策: **2026-08-09 D5 删除独立组件**,能力改址到 `trace-observability` F5。
  步骤条目本来就要在开始时展示 prompt(同决议 D4/F9),再留一个「Inspect prompt」链接
  意味着同一份信息有两个家、两处要同步。
- 原话/来源: 决策 `docs/design/2026-08-09-trace-ia-and-streaming-overhaul-decision.md` D5;
  PM 原话(2026-08-09):「这个prompt inspect是什么东西?不要搞那么复杂,
  如果显示清楚每一步做了什么,就能直接从tracing里面看到具体的prompt,不用搞特殊化」。
- 测试: `PromptInspector` 在 `apps/studio/frontend/src` 中 grep 为 0 命中;
  prompt 三段可在步骤条目内读到(该断言归 `trace-observability` F5)。
- Status: relocated(2026-08-09 → `trace-observability` F5)。
- 归属: region `timeline`; capability `trace-observability`.

### F5. Golden And Compare Actions

- 机制: trace/timeline can trigger compare and design-golden flows.
- 决策: golden prompts 有 trace-local 入口;**批量入口 = Copilot 分析 bar**(不在 timeline,归 `copilot-assist` F7),旧 sonner 批量已被取代。
- 原话/来源: `01_workflows/04_run-and-verify.md:124` and `01_workflows/04_run-and-verify.md:137` require trace and batch entries.
- 测试: trace-local button opens one copilot chat; compare uses correct backend route.
- Status: orphan/route mismatch.
- 归属: region `timeline`; capabilities `golden-eval`, `copilot-assist`.

### F6. Model Compare Tabs

- 机制: top tabs switch between different model results for comparison。**对比源 = 节点级候选的旁路单节点多跑**（不是整图按角色扇出）：focus 对比节点时，顶部 tab = 基准输出 + 该节点各候选的独立 run 输出；候选 = model group + route（`properties` F5 配置、Studio 后端按 skill+node 持久化）。
- 决策: P8 model comparison uses top tabs。**运行机制重定（PM 2026-07-02）**：主图用基准模型跑一次；Studio 抓对比节点在主 run 的 `InputDispatchEvent` 输入切片，把该单个 phase 物化成 `depends_on=input` 单节点临时 skill 变体 + 候选临时 roles，走现成 `run_artifact` 各跑一遍——独立单节点 run ⇒ 不改 engine 执行、永不写主黑板、per-candidate artifacts 分目录。**旧整图按角色扇出链（`CompareRunDialog` + `POST /runs/compare` fan-out + `run_compare.py`）删除**（实证坐实引擎跑不了图内并联，见 `00_settings-ux-spec.md §2.8`）。
- 原话/来源: `01_workflows/04_run-and-verify.md:98`、`01_workflows/04_run-and-verify.md:105`（顶部 tab）+ PM 2026-07-01/07-02 对比机制拍板。
- 测试: tabs preserve scroll/focus and show correct model result；对比运行产基准 + 各候选独立 run；候选 run 不改主 run final_state。
- Status: target-design（PR2 实现候选持久化 + 旁路单节点运行 + tab 接线）。
- 归属: region `timeline`; capabilities `trace-observability`、`run-execution`；候选配置 UI 归 `properties` F5。

### F7. 报告的两个入口

- 机制: 一次运行的 `report.md` 有且只有两个入口,都长在「读者本来就会看的地方」:
  1. **Trace 末尾的终结条目**——运行到达终态后,事件列表末尾长出一条非步骤条目,
     给出结论(成功 / 失败 / 中断)、耗时、token 总数与**报告链接**
     (`components/trace/TraceOutcomeRow.tsx`,数据由纯投影 `utils/trace-outcome.ts`
     的 `traceOutcomeEntry(events, metadata)` 合成);
  2. **运行列表每一行**——行内一个 `Report` 链接(`RunReportLink`),
     只在该次运行确实落了报告时出现。
- 数据来源: 后端把 `report_path` 从 `RunDetail` 提到**列表项 `RunMetadata`**
  (`apps/studio/backend/app/models/runs.py`),列表与详情两条读路都带它;
  `RunDetail.report_path` 这个平行字段**已删除**,读者一律读 `metadata.report_path`。
  该字段是**读时派生**(探测 `report.md` 是否存在),**绝不写进 `run_metadata.json`**——
  持久化路径会比它描述的文件活得久,文件一删记录就开始撒谎;
  持久化的窄形由 `RunMetadata.persisted_json()` 唯一决定。D8 要求的耗时实测已做:
  25 条运行的 `list_runs`(每条一次 `is_file()` 探测)在开发机上 **23ms**
  (回归下界 1s,见 `tests/services/test_run_report_in_list.py`),逐条探测不构成瓶颈,
  因此**不**采用备选的「seal 时把路径写进 run 元数据」方案——那会把派生值变成存储真相。
- 决策: 报告是这次运行的**产物**,产物出现在过程末尾;而要回看某次旧运行的报告时,
  读者的起点是运行列表的那一行。原先唯一的入口是身份条 `⋮` 菜单里的一项
  (2026-08-08 D5),读者得先知道那个菜单存在——**本条取代它,该菜单项已删除**。
- 原话/来源: 决策 `docs/design/2026-08-09-trace-ia-and-streaming-overhaul-decision.md` D8
  (含 §5「2026-08-08 决议 D5『report.md 入口在身份条 `⋮` 菜单』→ **改址**至本决议 D8 的两个入口」);
  PM 原话(2026-08-09):「报告在哪显示:1) tracing的最后应该有输出报告的一个步骤,
  自然会有报告链接 2) 回到主页,run&predict列表,报告链接显示在每一个run/predict的组件里」。
- 测试: 终结条目在最后一条步骤**之后**渲染,含结论 / 耗时 / token / 报告链接;
  运行未结束时不渲染;运行没落报告时不渲染链接;
  列表中只有带报告的行出现 `Report`;`traceRunActions` 不再返回 `report` 动作。
- Status: live(2026-08-09)。
- 归属: region `timeline`; capability `trace-observability`、`run-execution`;
  platform `studio-backend`(`RunMetadata.report_path`)。

## 3. 接口契约
- Inputs: current skill id, selected run id, live websocket events, persisted trace.
- Outputs: selected run/focus changes, compare/golden actions, prompt inspector open, editor trace document open.
- Capability links: `run-execution`, `trace-observability`, `golden-eval`, `debug-resume`.

## 4. 设计决策基础（PM 原话）
- predict 历史行**仅用 icon 与真实 run 行区分**,其余样式一致。
- 2026-08-09:「主页上,run id给我显示全了,和里面一样,run id 加上后面的状态徽章。
  最前面不要把状态和run、predict徽章混在一起,predict和run的图标固定一个」(F1)。
- 2026-08-09:「报告在哪显示:1) tracing的最后应该有输出报告的一个步骤,自然会有报告链接
  2) 回到主页,run&predict列表,报告链接显示在每一个run/predict的组件里」(F7)。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| TIMELINE-1 | live trace | 单元 `trace-dot-blackboard`；**为什么**：live trace 流挂 TimelinePanel，竖向时间轴(LangSmith 式) |
| TIMELINE-2 | run detail | 单元 `run-execution-node-status`（消费/落点；owner=run-execution/state-engine）；**为什么**：run row 开 RunDetailDrawer，run 历史归 timeline |
| TIMELINE-3 | golden actions | 单元 `golden-per-agent-node`（消费；owner=golden-eval）；**为什么**：golden 相关动作入口/分析在 copilot bar，timeline 消费 |

## 6. 测试关键点
1. live trace: baseline 现状为 TracePanel/useRunStream 未挂主流程 ⚠️；目标为 run/predict 时 Timeline 自动打开 live trace。
2. run detail: baseline 现状为 RunDetailDrawer 不由 row 打开 ⚠️；目标为 row 可开 detail/replay/compare/export。
3. golden actions: baseline 现状为 旧 sonner/batch copilot 入口残留 ⚠️；目标为 golden analysis 入口为 Copilot analysis bar，Timeline 只提供 compare/detail。

## 7. 涉及 region / platform
`trace-observability` · `run-execution` · `compile-lint` · `golden-eval` · `copilot-assist`

## 8. gaps / 报警
- ✅ live trace 已挂主流程(2026-08-07 清除旧报警):run/predict started 自动开面板并 follow 流;run 结束可返回列表(viewed-run 决议)。
- ✅ run detail 回看已 live(行点击 → 该 run 完整 Trace 视图,只读回放)。仍缺:Replay 重跑、detail/export 动作。
  (旧条目里的「run_id 概要层(F3)」不再是缺口:F3 已被 D1 作废,Trace 视图本身就是完整 trace。)
- 🚨 golden actions: 旧 sonner/batch copilot 入口残留 ⚠️；目标 golden analysis 入口为 Copilot analysis bar，Timeline 只提供 compare/detail。

## 交叉引用（链接, 不复制）
[baseline](./baseline.md)（现状,双向）· `trace-observability` · `run-execution` · `compile-lint` · `golden-eval` · `copilot-assist`
