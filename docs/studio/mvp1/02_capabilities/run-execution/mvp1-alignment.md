---
module: 02_capabilities/run-execution
doc: mvp1-alignment
status: FROZEN（后端 run manager live；前端 Run handler 仍是桩，predict-pass 不会置位，batch UI 未挂主路径 ⚠️。；目标结构已按 R4-R8 retrofit）
binds_baseline: ./baseline.md
units: [run-execution-node-status, golden-per-agent-node]
aligns_with: 01_workflows/04_run-and-verify.md（run / batch / node status）
---

# run-execution — MVP1 Alignment

> **Tier**: capability | **Owns**: `run-execution-node-status`（run 机制 + 批量/循环展示）+ `golden-per-agent-node` 的 run 播种切面 | **现状**: 后端 run manager live；前端 Run handler 仍是桩，predict-pass 不会置位，batch UI 未挂主路径 ⚠️。 | **Related**: [baseline](./baseline.md)（双向）· `predict` · `canvas` · `timeline` · `state-engine` · `golden-eval` · `engine` iterate/observability

## 1. 定义
`run-execution` owns true execution after predict-pass: start a real run, stream state, light nodes, persist final context/metrics/trace, show run history, and support batch execution once input configuration is ready.

Source workflow basis: `01_workflows/04_run-and-verify.md:42`, `01_workflows/04_run-and-verify.md:61`, `01_workflows/04_run-and-verify.md:70`.

## 2. 数据流 / 机制（设计细节）
### F1. Start Single Run

- 机制: clicking Run posts selected input to `/runs`; backend spawns `run_skill` and returns run metadata.
- 决策: run burns real tokens and must come after predict.
- 原话/来源: `01_workflows/04_run-and-verify.md:46` defines the action; `01_workflows/04_run-and-verify.md:67` keeps the PM quote that predict/run just run according to config.
- 测试: Run disabled until predict-pass; successful click creates a run_id and metadata row.
- Status: backend live, frontend stub.
- 归属: capability `run-execution`; region `center-action-bar`, `input`; platform `engine`.

### F1b. Run/Predict Id Shape And On-Disk Layout

- 机制: 一个 id 生产者铸造两种 id —— run 是 `<本地时间戳>_<uuid8>`,predict 是同一形状加 `predict-` 前缀。
  时间戳取**运行所在机器的本地墙钟**(naive),因为 id 的唯一读者是看文件夹列表的人;
  它从不参与计算,不承担时序语义。
  两种执行**分目录存放**:run 在 `<workspace>/runs/<run_id>`,predict 在 `<workspace>/predicts/<run_id>`。
  引擎的执行入口接收**宿主指定的 run 根目录**(`run_root`,必填,不设默认值),
  由知道自己在跑什么的那一层决定:`run_skill` / `resume_skill` / 编译产物 run 路径给 runs 根,
  `predict_skill` 给 predicts 根。Studio 侧由** id 前缀**决定根 —— Studio 是这两种 id 的唯一铸造者,
  所以它读得回自己写下的类型;引擎不做这件事,因为引擎收到的 id 不是它铸的。
- 决策(2026-08-09 D13): ① 不用 UTC —— UTC 戳对着文件树的人读起来就是错的时间;
  ② predict 与 run **同一形状**,由同一个函数产出,避免第二处 strftime 造成漂移
  (旧 predict id 是裸 uuid,排序无意义、信息为零);
  ③ 删除 `.workspace/runs/latest/` 镜像 —— 它是整个 run 目录的第二份拷贝,
  存在的唯一理由是给 team-save 一个固定路径可 force-add;git 需要的是路径而不是**固定**路径,
  所以改为直接 force-add **最新的那个 run 目录**(按目录 mtime 取)。
  ④ predict 与 run **分目录** —— 合在一起时,每个读者都要为这个区别付钱:
  列 run 要过滤掉排练、清排练要小心别删掉 run、"最新的那个目录"是哪种取决于最后跑的是哪种。
  分开只多一个名字,这些全部消失。**磁盘分开、UI 仍是一个列表**:`list_runs` 同时扫两个根,
  行的类型仍由 `RunMetadata.kind` 区分(C7 / 2026-08-07 D2 不变)。
  按不向后兼容原则,已存在的 run/predict 目录直接丢弃,不写迁移。
- 原话/来源: `01_workflows/04_run-and-verify.md` C17;决议
  `docs/design/2026-08-09-trace-ia-and-streaming-overhaul-decision.md` D13。
- 测试: 冻结本地时钟后 run/predict id 形状锁定且共享同一戳;两者都能通过 run-id 路径段校验;
  team-save force-add 的是最新 run 目录本身;predict 跑完后 trace 落在 predicts 根、
  `runs/` 根**根本不存在**;`list_runs` 在两个根各放一条时返回两条;
  引擎的执行入口**缺少 `run_root` 直接 TypeError**(不给默认值,才不会有人默默继承错的根)。
- Status: live(2026-08-09)。
- 归属: capability `run-execution`; platform `engine`(run 根由宿主指定的契约)。

### F2. Live Run State And Node Lights

- 机制: run websocket events derive graph node statuses, edge animation, and current focus.
- 决策: run animation should reuse the role-test style for consistency.
- 原话/来源: `01_workflows/04_run-and-verify.md:49` and `01_workflows/04_run-and-verify.md:50` list status and node lights; `01_workflows/04_run-and-verify.md:67` records the PM animation decision.
- 测试: each node lights running/success/error from real events; failed node becomes red and stops focus.
- Status: placeholder.
- 归属: capability `run-execution`; capability `trace-observability`; region `canvas`; platform `state-engine`.

### F3. Run History And Detail

- 机制: list past runs, show status/duration/token summaries, and open a run detail/replay view.
- 决策: run aftercare belongs in the timeline/history area, not in the graph authoring form.
- 原话/来源: `01_workflows/04_run-and-verify.md:52` and `01_workflows/04_run-and-verify.md:58` list history and detail actions.
- 测试: completed/failed runs appear; detail drawer can replay with same input; delete removes a run row.
- Status: history live, detail drawer orphan.
- 归属: region `timeline`, `local-history`; capability `run-execution`.

### F4. Batch Run

- 机制: i/o panel selects multiple inputs, backend starts a batch, frontend polls progress and reports per-item failure.
- 决策: batch is input/run configuration, not an independent predict concept.
- 原话/来源: `01_workflows/04_run-and-verify.md:54` to `01_workflows/04_run-and-verify.md:57` list batch actions; `01_workflows/04_run-and-verify.md:62` places run entry in i/o panel.
- 测试: each input gets a run result; one failed item is visible and does not silently disappear.
- Status: backend live, frontend orphan.
- 归属: capability `run-execution`; region `input`; platform `engine`.

### F5. Successful Run Autocommit

- 机制: successful run triggers local git autocommit and stores status.
- 决策: autocommit is triggered by run but owned by save/publish.
- 原话/来源: `01_workflows/04_run-and-verify.md:59` marks autocommit backend-only; `01_workflows/04_run-and-verify.md:64` assigns it to save/publish.
- 测试: successful run commits; failed or interrupted run does not commit.
- Status: backend-only live.
- 归属: capability `publish`; platform `native-fs`.

### F6. Run Report

- 机制: 每次 run 结束(成功或失败)后,在该 run 目录写出一份 `report.md`——把这次 run
  "花了多久 / 花了多少 token / 每个节点做了什么 / 用的哪个模型 / 读了哪些输入文件 /
  产出了哪些 artifact / 哪里报错"汇成一页可读的账,并用相对链接指向同目录里的原始记录。
- 决策 RUN_EXECUTION-5(报告 = 投影,不是第四份真相): report.md 由一个**纯函数**从该 run
  **已封存**的输入生成(`run_metadata.json` / `metrics.json` / `trace.jsonl` /
  `runtime_config.snapshot.json` / `artifacts/` 目录),不新增任何只存在于报告里的数据。
  因此它随时可以被重新生成,删掉不丢信息;它也**不得**成为任何读者的事实来源——
  需要精确数值的消费者读原始文件,报告只负责"人能一眼看懂"。
  **为什么**:底座一(config/run truth 单一所有权)不允许再立一份并行真相;而用户要的是
  "一次 run 到底发生了什么"的可读汇总,这恰好是投影而不是新事实。
- 决策 RUN_EXECUTION-6(token 与模型只认事件流): 报告的 token 合计与逐节点 token 由
  `trace.jsonl` 的 `llm_call` 事件聚合得出,模型名取同一事件的 `resolved_model`。
  **为什么**:一个 role 通过 fallback chain 解析,"这次用了哪个模型"只有逐次调用才为真;
  而 `metrics.json` 是引擎侧的汇总,两者必须能对上——对不上就是引擎缺陷(2026-08-08 修复:
  agent 节点此前不把 token 折进 run metrics,见 engine `02-observability` §8 #1)。
- 决策 RUN_EXECUTION-7(格式 = 单份 markdown): 只写 `report.md`,不并写 `report.json`。
  **为什么**:结构化真相已经在 `trace.jsonl` / `metrics.json` 里;再存一份 JSON 投影
  等于第三份副本(违 KISS/YAGNI 与 SSOT),而 markdown 在文件管理器、编辑器和 Studio 里
  都能直接读,相对链接也能直接点开。
- 原话/来源: PM 2026-08-08 "每一次run结束要出一个报告放在run id文件夹,展示这一次run的
  整体情况、内容细节、文件给链接,花费时间、token;每一个节点时间,token,什么模型;
  batch/loop 详细情况;llm vs 结果链接;input files链接;artifacts结果链接;每个节点报错详情"。
- 测试: 报告纯函数对同一份封存输入产出稳定结果;失败 run 的报告写出失败原因;
  逐节点 token 合计等于 `llm_call` 事件之和;没有任何一节引用 run 目录之外的绝对路径。
- Status: target-design。
- 归属: capability `run-execution`(owner);数据来源 `engine:02-observability`(引)。

## 3. 接口契约
- Entry: Run is enabled only after compile-pass and predict-pass.
- Input: i/o panel supplies single or batch input selection.
- Backend: run manager owns process lifecycle, run artifacts, websocket stream, and history.
- Trace/golden consumers read run outputs after completion.
- Region links: `center-action-bar`, `input`, `canvas`, `timeline`, `local-history`.
- Platform links: `engine`, `state-engine`, `native-fs`.

## 4. 设计决策基础（PM 原话）
- Replay 先放 **Timeline**;Local History **只做 git**(不吸收 RunDetailDrawer/BatchSummary);batch 输入范围命名随实现定。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| RUN_EXECUTION-1 | Run 入口 | 单元 `run-execution-node-status`；**为什么**：onRun 现仅日志，要真调 startRun 带选中 input/settings |
| RUN_EXECUTION-2 | 节点态 | 单元 `run-execution-node-status`；**为什么**：run events 经 state-engine 投到节点灯/边，非画布默认假态 |
| RUN_EXECUTION-3 | batch | 单元 `run-execution-node-status`；**为什么**：后端 batch 与 hook 已存在但未挂 Workspace，批量/循环入口要可用 |
| RUN_EXECUTION-4 | golden seed | 单元 `golden-per-agent-node`；**为什么**：run 真实输出可做 golden 默认种子，predict 假数据不可(409) |
| RUN_EXECUTION-5 | run 报告 = 已封存产物的纯投影 | F6；**为什么**：用户要一页可读的 run 总账，但底座一不允许再立一份并行真相——投影可重生成、删了不丢信息 |
| RUN_EXECUTION-6 | 报告的 token / 模型只认 `llm_call` 事件 | F6；**为什么**：role 走 fallback chain，"这次用了哪个模型"只有逐次调用才为真；与 `metrics.json` 对不上即引擎缺陷 |
| RUN_EXECUTION-7 | 只写 `report.md`，不并写 `report.json` | F6；**为什么**：结构化真相已在 trace/metrics 里，再存一份 JSON 投影是第三份副本 |

## 6. 测试关键点
1. Run 入口: baseline 现状为 `onRun` 只日志 ⚠️；目标为 Run 真调用 `startRun`，携带选中 input/settings。
2. 节点态: baseline 现状为 GraphCanvas 默认/假态 ⚠️；目标为 run events 经 state-engine 投到节点灯/边。
3. batch: baseline 现状为 后端与 hook 存在但未挂 Workspace ⚠️；目标为 批量/循环入口与结果展示可用。
4. golden seed: baseline 现状为 run final output 可做 golden 默认种子；目标为 predict fake trace 不可做 golden。
5. run 报告: 目标为 每次 run 结束在 run 目录写出 `report.md`；判据为 (a) 纯函数、同输入同输出；(b) 失败 run 写出失败原因；(c) 逐节点 token 合计 == `llm_call` 事件之和；(d) 全部链接为 run 目录内相对路径。

## 7. 涉及 region / platform
`predict` · `canvas` · `timeline` · `state-engine` · `golden-eval` · `engine` iterate/observability

## 8. gaps / 报警
- 🚨 Run 入口: `onRun` 只日志 ⚠️；目标 Run 真调用 `startRun`，携带选中 input/settings。
- 🚨 节点态: GraphCanvas 默认/假态 ⚠️；目标 run events 经 state-engine 投到节点灯/边。
- 🚨 batch: 后端与 hook 存在但未挂 Workspace ⚠️；目标 批量/循环入口与结果展示可用。

## 交叉引用（链接, 不复制）
[baseline](./baseline.md)（现状,双向）· `predict` · `canvas` · `timeline` · `state-engine` · `golden-eval` · `engine` iterate/observability
