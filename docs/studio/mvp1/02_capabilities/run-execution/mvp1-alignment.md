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
  「哪个是最新」这个问题**改由 UI 回答**:资产树里 `.workspace/runs` 与 `.workspace/predicts`
  两个目录的子项**按修改时间倒序**(最新在最上),首条挂一个 `latest` 小徽章
  (`components/studio/panels/run-directory-order.ts` 的 `orderRunDirectories` /
  `latestRunDirectory`,徽章走 `components/ui/badge` 的 `outline` variant)。
  时间来自 Rust native-fs:`WorkspaceDirEntry.modified_ms`,取自列目录时**本来就要做**的
  `metadata()` 调用,不多一次 syscall;取不到时退回按名字倒序——run id 以可排序的本地时间戳打头,
  所以名字倒序依然是时间倒序。**只有这两个目录这样排**:树里其余位置按字母序,
  因为读者是在找一个自己叫得出名字的文件,而 run 目录的名字是机器生成的时刻,没人按名字找它。
  ④ predict 与 run **分目录** —— 合在一起时,每个读者都要为这个区别付钱:
  列 run 要过滤掉排练、清排练要小心别删掉 run、"最新的那个目录"是哪种取决于最后跑的是哪种。
  分开只多一个名字,这些全部消失。**磁盘分开、UI 仍是一个列表**:`list_runs` 同时扫两个根,
  行的类型仍由 `RunMetadata.kind` 区分(C7 / 2026-08-07 D2 不变)。
  按不向后兼容原则,已存在的 run/predict 目录直接丢弃,不写迁移。
  ⑤ **(2026-08-20 落地)D13 的理由管的是读者,不是 run id**——所以它对**每一个人会读到的
  时刻**都成立:存的是带时区的 UTC 瞬间(那是代码用来算的东西,也是机器换时区后仍然正确的
  东西),**呈现一律换算成读者本机的墙钟**,换算只发生在"值变成给人看的文字"那一个边界上。
  没有这条规则时的实测(2026-08-20,真报告 `2026-08-19T06-58-15_179d1440/report.md`):
  同一份报告相隔两行写着 `| Run | 2026-08-19T06-58-15_179d1440 |` 与
  `| Started | 2026-08-19T13:58:15.556101Z |`——一个瞬间、两个读数、差七小时,
  而报告读者和文件树读者是同一个人。**三处落地**:后端报告的 `Started`
  (`services/run_report.py` 的 `_wall_clock`)、前端的唯一换算出口
  (`utils/wall-clock.ts`,收编了此前散在五处的读法,其中 Settings 真相源那处是把偏移量
  从字符串上抹掉、把 UTC 数字当本地显示)、导出文件名(`reportTimestamp` 改用同一个
  `fileStamp`,与 run 目录同形)。
  **两种读数格式不同是故意的**:报告里的 `2026-08-19 06:58:15 -07:00` 带偏移量,因为
  一个光秃秃的本地戳说不出自己是哪个时区(借 `git log` 的既有做法——它就是这样打印
  作者本地时间加偏移量的;偏移量写成 `-07:00` 而不是 git 的 `-0700`,是为了与本产品其它
  地方写偏移量的拼法一致);run id 不带,因为文件名塞不下冒号,这也正是 id 用短横线的原因。
  **不带时区的裸戳按本地读、不平移**:引擎处处写的是带时区的 UTC,所以真出现裸戳时,
  给它加一次偏移会把读数搬走整整一个时区,报出一个这次 run 根本没有过的时刻。
- 原话/来源: `01_workflows/04_run-and-verify.md` C17;决议
  `docs/design/2026-08-09-trace-ia-and-streaming-overhaul-decision.md` D13;
  2026-08-19 用户报障「run id/事件 UTC 与本地混用」(问题台账 E7)。
- 测试: 报告的 `Started` 行读作存储瞬间的本机墙钟并带偏移量、不出现 `Z`,裸戳不被平移
  (`tests/services/test_run_report_reads_in_local_time.py`);前端同一瞬间的三种写法
  (`Z` / `-07:00` / `+02:00`)渲染出同一段文字,`fileStamp` 与 run id 同形且不含冒号
  (`utils/wall-clock.test.ts`)。
  冻结本地时钟后 run/predict id 形状锁定且共享同一戳;两者都能通过 run-id 路径段校验;
  team-save force-add 的是最新 run 目录本身;predict 跑完后 trace 落在 predicts 根、
  `runs/` 根**根本不存在**;`list_runs` 在两个根各放一条时返回两条;
  `list_workspace_dir` 为每个条目报出 `modified_ms`;两个 run 根按 mtime 倒序、
  首个**目录**(不是文件)得 `latest`,其余目录路径一律无徽章;
  引擎的执行入口**缺少 `run_root` 直接 TypeError**(不给默认值,才不会有人默默继承错的根)。
- Status: live(2026-08-09)。
- 归属: capability `run-execution`; platform `engine`(run 根由宿主指定的契约)、
  `native-fs`(`modified_ms`)、region `assets`(排序与徽章)。

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
- 决策(被看的那次 run 拥有它旁边的每个动作): trace 能显示的 run 有两种——正在跑的那次,和从历史里点开的那次。**旁边的动作一律作用在「此刻显示的这次」上**:Compare to golden、Promote、节点 model compare、四条 Resume(整跑 / HITL 应答 / 边上下文 / 从某节点)全部读同一个来源。**Pause 与 Stop 是例外,并且例外有理由**:它们作用的是**还在跑的那个 worker**,而只有 live run 有 worker,所以它们问的本来就是另一个问题。分开之前,「我在看哪次 run」有两个答案:一个是 trace 自己算出来的,一个是「哪次 run 是活的」;于是看着旧 run 按 Resume 会去续**另一次** run,Compare to golden 量的是**另一次** run,而节点 compare 直接拒绝说「先跑一次」——明明屏幕上就摆着一次跑完的 run。
- 决策(候选页签属于 compare 组,不属于它下面那条 trace): 一个节点的 Compare LLMs 会为每个候选各起一次单节点 side-run,读者靠**候选页签**在它们之间移动。这排页签的前提只有一句——**存在一个 compare 组**——句子里没有「有一次 live run」,所以它由 **trace 区域**渲染,live trace / 历史 trace / 运行历史列表三种主体之上各一次。此前它住在 live 那一支里,于是上面那条决策刚打开的路当场又被堵死:**从历史 run 发起的对比跑完了,却一个页签都没有**,组存在而不可达。这与 CP4 的 `Design golden` 是同一条规则的两次发作,通则已固化在 `FRONTEND_UI_SPEC.md` §2.9b。**页签本身不区分候选跑完没跑完**:side-run 一被派出去页签就在,读者可以在某个候选还空着的时候切过去看。
- 决策(标记一个候选为当前 = 显示它,是同一个动作): 页签排上「哪个候选是当前」和 trace 区域「正在放哪条 run」必须由**同一次调用**同时写下。二者可分开写的时候它们就分开了:对比一发起,组里第一个候选的页签被标成当前,而下面的 trace 还停在**基线那条 run** 上,读者点一下这个「已经选中」的页签,屏幕才换内容——「我在看哪个候选」有了两个答案(问题台账 L2③,2026-08-21 真机走查实测)。修法不是在发起处补一句「顺便也换 trace」,那只是把两条写法凑巧对齐;而是让**只存在一个写入口**(`Workspace.tsx::showCandidate`),标记而不显示从此不可表示。它接收的候选清单由调用方传入而不是从 state 里读——发起对比的那一次,React 还没提交这批 side-run。
- 决策(候选选的是一条 route,所以下拉里每一行必须指得出是哪一条): `Add compare LLM` 的 Endpoint
  下拉是**执行面**——挑中的那一行就是这次候选 side-run 要跑的路由。所以它的标签规则不是本文档自己
  的一条,而是 `01_workflows/00_settings-ux-spec.md` §2.1 那条(2026-08-21 补记「同一条规则适用于
  任何『把 route 列出来让人挑』的界面」)在这一屏的应用:标签取自同一处投影
  `lib/route-labels.ts::distinguishingRouteLabels`,**这里不另立一套写法**。实测起因见问题台账 L6:
  一个模型 17 个选项、`Qiniu` 出现 7 次,选哪一行是掷骰子。
- 测试: completed/failed runs appear; detail drawer can replay with same input; delete removes a run row;从历史点开一次 run 之后,golden diff 绑定的是它、节点 compare 发给后端的 base run 是它、Resume 续的是它(`Workspace.test.tsx` 三条,均在修复前实证会红);候选页签在**历史 trace 之上**、在**运行历史列表之上**、在 live trace 之上都出现,没有 compare 组时一个都不出现(`Panels.trace-mount.test.tsx` 四条,前两条在修复前实证会红——**打在区域上而不是组件上**,组件级的三条另在 `CompareCandidateTabs.test.tsx`)。
- Status: history live, detail drawer orphan;被看的 run 拥有旁边动作 = live;候选页签归 compare 组 = live。
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
  产出了哪些 artifact / **重复跑了多少次、每次各花了什么、哪一次没成** / 哪里报错"
  汇成一页可读的账,并用相对链接指向同目录里的原始记录。
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
- 决策 RUN_EXECUTION-8(重复要逐次记账,不许求和了事;2026-08-20 立,问题台账 R1②③): 一个节点
  **跑了几次**与它**一次里想了几轮**是两件事,报告必须分开说,而且都要说。
  - **逐次执行**:`iterate` 的每个 item、以及任何被重复执行的节点,各自是一次执行
    (engine 用 `phase_execution_id` 区分)。Nodes 表里那一行是**求和**,它能回答"这个节点一共
    花了多少",但**回答不了**"哪个 item 慢、哪个 item 挂了"——而对一次 40 章的 iterate,
    后者才是唯一值得问的。所以逐次执行另起一节列出:每次的耗时 / token / 工具次数 / 成败。
  - **`agent turns` 不叫 loop iterations**:`agent_loop_iteration` 数的是**一次执行内部**
    ReAct 循环的轮数(模型想了几轮),从前它顶着 `loop iterations` 这个列名,读起来像"这个节点
    跑了 3 次",实际是"跑了 1 次、想了 3 轮"。名字改成 `agent turns`,与上面的执行次数并列。
  - **parallel_map 扇出按组记账**:引擎本来就发 `parallel_map_group_started/ended`
    (item 数 / 并发度 / 成败数 / 墙钟),报告从前一个都不读。扇出的墙钟脱离并发度无法解读,
    所以两者同排。
  - **节点状态入表**:每行必须说这个节点**怎么结束的**——`ok` / `failed` / `interrupted` /
    `unfinished`。`unfinished` 指"开了没关",即 run 结束时它还开着:它既不是成功也不是失败,
    把它算进任何一边都是在编造事实。节点状态取其各次执行里**最差**的那个。
- 决策 RUN_EXECUTION-9(区分"出错"与"纠正";2026-08-20 立,问题台账 R1④): 报告里
  **Failure 只列"机器拒绝或放弃了被要求做的事"**——`protocol_violation`(违反框架契约、
  循环即将被切断)、`finish_task_verdict` 被拒、`loop_detected`(转圈被切)、
  `builtin_subagent_fallback`(**跑完了,但走的是比配置更次的路**——这条不报就没有任何地方
  会报)。而 `nudge` / `tool_error_handled` / `tool_history_repaired` 是**纠正**:机器改变了
  run 的走向而 run 继续往前,它们**只计数**(进 Nodes 表的 `corrections` 列),不进 Failure。
  **为什么**:Failure 是"哪里出问题了"的清单,把每一次 nudge 塞进去会让真正的失败淹没在噪声里;
  而完全不记又会丢掉"这个节点被推了六次"这条值得看一眼的事实。引擎对 `tool_error_handled`
  早就是这个判断(它把异常变成了模型读得懂的反馈),这里只是把同一条判据说全。
  **凡是报告自己没写的那句话,一律先过同一道处理**(2026-08-20 补全,问题台账 R3):
  截到 200 字符、折成一行;进表格单元格的还要转义 `|`。
  - **为什么截断**:实测一条 `protocol_violation` 消息几千字,原样打印会把同一节里其他失败
    全部压到屏幕外;全文就在报告已经链接着的 `trace.jsonl` 里,报告欠读者的是"认得出是哪个
    失败",不是一份逐字誊本。
  - **为什么"凡是"**:这条规则原先只落在 Failure 节的 `message` 上,于是同一份报告里另外三处
    照样原样打印——Routes 表的决策 reason、未满足设置表的 reason、Failure 节的 `errors` 列表
    (被拒的 `finish_task_verdict` 正是从这里来)。实测 run `2026-08-20T10-27-18_a98f6ba5`:
    一次 `dropped_rejected_settings` 把 provider 的 400 原文当 reason,Routes 表原样印出,
    **单个单元格 263,241 字符,整份报告 529 KB——而这次 run 只发了 3 次模型调用**。
    所以判据不是"哪一节要截断",而是**"这句话是不是报告自己写的"**:不是,就走这道处理。
  - **长度不是唯一的破坏方式**:markdown 表格行以 `|` 分列、以换行结束。一条含 `|` 的
    provider 消息会**悄悄把自己那行劈成多列**,此后每个单元格都排到错的表头下——
    一张悄悄错了的表比一张明显被截断的表更坏;含换行的消息则直接把行提前截断。
- 决策 RUN_EXECUTION-10(报告点了名就要能点开;2026-08-20 立,问题台账 R1①③): 报告里凡是
  **指名道姓提到的东西**——输入文件、被比较的那次 run——都必须是**能点开的相对链接**,
  而不是一段代码字体的路径。链接**从实际目录推出来**,不写死 `../..`:
  - **输入文件**:绑定路径相对于 skill 的 `.workspace`,而 run 目录在 `<workspace>/runs/<run id>`,
    所以文件正好在上两级。若这份报告不在那个位置(布局不同、被拷走),**就不给链接、只给路径**——
    **点不开的链接比纯文本更坏**,它引诱一次注定失败的点击。
  - **输入文件要报两种来源**:快照 `runtime_config.snapshot.json` 说的是**启动时声明**读哪些文件;
    引擎的 `input_file_injected` 事件说的是**跑的过程中真的送进去了什么**(它挂在一条边上,
    所以"送给了哪个节点"是这条事实的一部分,不是修饰)。只报前者,答案在 run 开始时为真、
    到结束就过期了。
  - **compare 候选**:一次候选 side-run 只有摆在**它对照的那次 run** 旁边才有意义,所以报告
    链到那次 run 的 `report.md`(同级目录上一层)。这一条同时是**数据缺口**而不只是渲染缺口:
    side-run 此前**根本没记**自己是对着哪次 run 跑的,`RunMetadata.compare_base_run_id` 本次补上。
    没记到 base 的候选**照实说"没记录"**,不猜 run id。
  - **基准 run 那一侧仍然没有 compare 节**,而且**在报告可重生成之前也不可能有**:compare 发生在
    基准 run 结束**之后**,而报告是在 run 终态写一次的纯投影。要么让报告可重生成(见下面的
    已知缺口),要么去 UI 的 compare 面板看——不能让报告去扫兄弟目录,那会让"这份报告说什么"
    取决于此后又跑了什么。
- 决策 RUN_EXECUTION-11(报告在**被打开时**重新生成;2026-08-20 立,问题台账 R1 收尾):
  RUN_EXECUTION-5 早就把报告定为"随时可以被重新生成"的纯投影,但产品里**没有任何一处能
  重新生成它**——`report.md` 只在 run 封存那一刻写一次。于是每一份历史报告永远停在写它
  那天的渲染逻辑上:渲染器每改进一次,只有此后的新 run 受益,旧 run 的报告变成一座过时
  版本的博物馆。
  - **重生成的时机 = 有人要读它**:`POST /api/skills/{skill}/runs/{run}/report` 重渲染
    `report.md` 并返回这次 run 的规范快照。run 列表行的 Report 入口与 Trace 末尾的
    "Open run report" 都先调它,再把返回的 `report_path` 交给编辑器打开——两个入口共用
    同一个打开动作,不能一个新一个旧。投影是纯的,所以重复渲染幂等;按"打开"计费是
    每次用户动作 O(1) 次写,而按"列出 run"计费会变成每次列表 O(runs) 次写。
  - **明确拒绝渲染器版本号**:另一条路是在报告里盖一个渲染器版本、读时比对再决定要不要
    重渲。本仓已经有一个"改了源码还要记得再做一步"的机制——桌面 app 的 vendor 快照——
    而它留下的教训正是这类步骤会被忘掉(`AGENTS.md` Workflow Pipeline 第 7 条)。
    所以不引入第二个需要人记得同步 bump 的数字。
  - **没结束的 run 一律拒绝**(`RUN_NOT_CONCLUDED`,409):`report_path` 是从"报告文件
    在不在"推出来的,给一个还在跑的 run 写报告,会让 run 列表**给一个正在跑的 run 挂上
    报告入口**,而那份报告的内容几分钟后就自相矛盾。`paused` 同样算没结束——它在等着被继续。
  - **重渲染失败仍然打开已有的那一份**:读者问的是"这次 run 发生了什么",上个月的渲染
    回答得了这个问题,什么都不显示回答不了;但失败要明说(toast),不静默吞掉——渲染器
    跑不起来是故障,不是偏好。
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

### F7. 一次运行的两个未来,任何时候都摆在台面上

- 机制: 中央动作条按 run 的阶段给按钮,**在飞和已暂停给的是同一对**:
  - `running` → **Pause + Stop**(Pause 高亮为当前主动作)
  - `paused` → **Resume + Stop**
  - 其余阶段 → `Run`(按编译/预测门禁决定可用性)
- 决策:
  - **"我要它停"不该绕道经过一个用户没要的状态。** 从前 `running` 只给 Pause,
    想结束就得先暂停再停止——两步,中间那一步是 UI 自己发明的。后端从来不需要它:
    `POST /runs/{id}/stop` 对在飞的 run 一步到位
    (`apps/studio/backend/tests/test_run_pause_stop.py::test_stopping_a_run_in_flight_skips_the_pause`
    断言直接返回 `cancelled`)。
  - **Pause 与 Stop 不互相蕴含,所以都写出来。** Pause 保留 checkpoint(引擎只在 run
    自己跑完时才清),Stop 就地结束;这与 `paused` 那一对是同一条理由,只是方向相反。
  - **禁用的 Run 按钮不是回答。** 它说"等着",却不说怎么才能不等——这正是本条要消除的
    沉默。
- 原话/来源: PM 2026-08-04③「run 运行中按钮至少变成可停止」。
- 测试: `center-action-bar.test.tsx`(`running` 同时给出 Pause 与 Stop 且不出现 Resume;
  `paused` 给出 Resume 与 Stop 且不出现 Pause)。
- Status: target-design(2026-08-20 立)。
- 归属: capability `run-execution`; region `canvas`.

### F8. 一个 run 说自己在跑,就得说得出是谁在跑它

- 机制: 执行一次 run 的 worker 进程,在它**整个生命周期内**持有该 run 自己目录下
  `worker.lock` 的独占 OS 锁(`apps/studio/backend/app/services/run_liveness.py`)。
  任何后来者要问"这个 run 还在跑吗",就去抢那把锁:抢不到 = 有活着的持有者,
  抢得到 = 没人在跑。RunManager 在 `list_runs` 与 `_metadata_for` 两个读出口上做
  **对账**:记录说 `running`、且该 run 不在本进程的内存注册表里、且锁没人持有,
  就把记录改写成新状态 `abandoned` 并返回改写后的记录。
  **对账只查 `running` 一种状态**(2026-08-21 订正):`paused` 不是一句关于 worker 的
  声明——`pause_run` 是**故意**把 worker 结束掉并留下 checkpoint 的,所以"没人持锁"
  对每一个 paused run 都恒真。把它一并对账,等于把用户自己按下的暂停改写成
  "app 在它跑着的时候关掉了",而那句话不是事实(台账 C1 ④)。
- 决策:
  - **"在跑"是一句声明,声明必须可被核对。** sidecar 只把在飞的 run 放在内存里,
    所以换一个 sidecar 起来,注册表是空的而磁盘记录还写着 `running`。同一个问题因此
    有两个答案:run 列表答"在跑"(读记录),`pause_run` 答 `RUN_NOT_RUNNING` 409
    (读注册表)。徽章会一直转到用户重装数据为止。**一个问题两个答案,本身就是缺陷。**
  - **借鉴对象与取舍**:PostgreSQL 在 `postmaster.pid` 旁边锁住数据目录,systemd 处理
    `PIDFile` 时同样把"锁还在不在"当作存活事实、而不是把那个数字当事实。理由相同:
    **持有者无论怎么死,OS 都会释放锁**,包括来不及跑任何清理的 kill。
  - **拒绝 pid 探测**(`os.kill(pid, 0)`):pid 会被复用,一个被回收的 pid 会让死掉的 run
    读起来还活着——那正是这里要消灭的谎言,换个地方重新长出来。
  - **拒绝心跳时间戳**:心跳需要一个"多久算过期"的阈值,而一个正在等慢速 LLM 调用的
    相位,和一个已经死掉的 worker,在阈值面前长得一模一样。
  - **参考对象在本仓不成立的部分**:PostgreSQL 可以假设一个众所周知的数据目录和一个
    比机器上一切都活得久的 supervisor。本仓没有守护进程——sidecar 随 app 窗口一起死——
    所以既没有那个统一的落锁点,也没有可以问的 supervisor。锁因此落在**每个 run 自己的
    目录里**,靠遍历 run 找到,而不是去一个中心位置看。
  - **`abandoned`,不是 `interrupted`**:引擎已经把 `interrupted` 用在"停下来问人"上
    (`RunEndedEvent.status="interrupted"`,紧跟一个 `InterruptedEvent` 发出),那是
    **有人会回来**的情形,和这里正好相反。一个词只能指一样东西。
  - **`abandoned` 也不是 `failed` 或 `cancelled`**:run 本身没有失败,也没有人要求结束它。
    它是**没人选的那种结束**——执行它的东西走了。
  - **pid 仍然记在锁旁边**,但它不是存活答案;它是"父进程句柄丢了以后还想停掉这个
    worker"时唯一能用的把手。
- UI 投影: `abandoned` 在三处落地,共用同一套读法——run 列表与 Trace 顶条的徽章
  (`runStatusMark`:拔掉插头的图标 + warning 色 + "Run abandoned — the app closed while
  it was going")、画布节点的收尾表(`NODE_STATUS_AT_RUN_END` → `paused`)、边的收尾表
  (`EDGE_STATUS_AT_RUN_END` → `paused`)。收 `paused` 而不是红色错误:节点没有失败,
  它只是停在了它停下的地方。
- 原话/来源: 用户 2026-08-19「运行时观测」模块拆解(台账 C1);缺陷 2026-08-21 实测复现。
- 测试: `apps/studio/backend/tests/services/test_a_run_says_who_is_running_it.py`
  (锁没人持有 = worker 不在;worker 不清理地死掉照样释放;新 sidecar 不再把没人跑的 run
  报成在跑;worker 还握着锁的 run 不被动)。前端:`run-status-projection.test.ts`
  (`abandoned` 传得穿投影,且与引擎的 `interrupted` 分得开)、`run-status-mark.test.ts`
  (`abandoned` 有自己的徽章)、`edge-status-projection.test.ts`(收尾表覆盖它)。
- Status: target-design(2026-08-21 立)。
- 归属: capability `run-execution`(owner);region `timeline` · `canvas`(引)。

### F9. 正在跑的那次 run 属于 skill,不属于打开它的那扇窗

- 机制: Workspace 打开一个 skill 时,从**该 skill 的 run 列表**(`GET
  /skills/{id}/runs`,与 Timeline 共用同一个 SWR key)冷载一次,取其中状态为
  `running` 或 `paused` 的最新一条,作为本次会话的 live run:置 `runId`(trace 流
  因此重新订阅到它,后端把事件日志整段重放,画布的灯与 Trace 面板一起回来)、置
  live 记录、把底栏 stage 置成 `running` / `paused`(于是 Pause / Stop / Resume
  重新可点)。规则本体是纯函数 `nextAdoptedLiveRun`(`hooks/useRunHistory.ts`)。
- 决策:
  - **"哪次 run 是活的"从前只有窗口的记忆回答得出。** `runId` 只在**本窗口亲自发起**
    run 时被写入,并在每次切换 skill 时清空。于是刷新一次 app、或者切走再切回来,
    worker 还在跑而按钮全没了——除了关掉整个 app,没有第二种把它停下来的办法
    (台账 C1 ④)。
  - **服务端本来就知道,而且从 F8 起知道得可靠。** `running` 那一行在返回之前已经
    对着 worker 的锁核对过,所以它不是一句会过期的旧话。冷载的是**已有的真相**,
    不是新造一个问题去问。
  - **`paused` 同样要认领。** 它不是关于 worker 的声明,但它**就是这个 skill 当前的
    那次 run**——Resume 与 Stop 说的是它,画布上该显示的也是它。
  - **一个 skill 只问一次,此后不再问。** 面板挂载、窗口聚焦、WebSocket 重连都不是
    数据变化(SSOT 读取原则),再问就成了轮询。本会话已经有 live run 时直接记为
    "问过了、无需认领",免得列表晚到一步把用户刚发起的 run 顶掉。
  - **它没有让请求变多。** Workspace 与 Timeline 共用同一个 key,SWR 去重;从前
    Timeline 打开时会发的那一次请求,现在提前到打开 skill 时发,**总数仍是每个 skill
    一次**。这一点也是 `STUDIO_REQUEST_AUDIT.md` 里那条"Workspace 不订阅 run 列表"
    的裁决被改写的理由:它当初挡的是**重复拉取**,而不是"永远不许读这份列表",
    而如今 Workspace 有了一个真实的、只此一个的读取理由。
  - **已知窗口(接受并写明)**:列表返回之后、客户端渲染之前的那几毫秒里 run 恰好
    结束,则底栏会短暂停在 `running`。gate 订阅从挂载起就在,所以更早或更晚结束的
    run 都会被正常收尾;这个窗口只能靠再引入一次读取来消除,不值得。
- 原话/来源: 用户 2026-08-19「运行时观测」模块拆解(台账 C1 ④)。
- 测试: `hooks/useRunHistory.test.ts`(`nextAdoptedLiveRun`:认领 running / 认领
  paused / 全都结束了就不认领 / 列表没加载完不当作"没有" / 不顶掉本会话刚起的 run /
  一个 skill 只问一次)、`components/studio/Workspace.test.tsx`(客户端渲染三条:
  服务端说 running 则底栏为 `running`、说 paused 则为 `paused`、全结束则仍为 `idle`;
  前两条在修复前实测为 `idle`)。
- Status: target-design(2026-08-21 立)。
- 归属: capability `run-execution`(owner);region `center-action-bar` · `canvas` ·
  `timeline`(引)。

### F10. 一次 run 可以停在你指定的相位之前

- 机制:
  - **断点是「跑到这个相位之前先停下」**,由用户在画布上对某个相位设下,存在**该 skill 的
    工作区**(`.workspace/runtime_config.json`)里,跨多次 run 存活。
  - **让图停下来的是引擎**:`assemble_graph(..., pause_before=frozenset[str])` 把这些相位名
    交给 LangGraph 的 `builder.compile(interrupt_before=[...])`。
  - **停下来时的现场**(2026-08-21 实测):`graph.invoke(...)` 返回,
    `graph.get_state(config).next` 是 `("b",)`——即它**将要执行而还没执行**的那个相位;
    而 `state.interrupts` 是**空的**。再 `graph.invoke(None, config)` 一次,那个相位执行、
    `next` 变空、run 跑完。
  - **run 的结局是 `paused`**:它有 checkpoint、能续、还没产出最终输出。
  - **断点命中时,那个相位一次都还没跑**——`interrupt_before` 停在进入之前,所以画布上
    该亮的是「停在这里」,不是「这一步做完了」。
- 决策 RUN_EXECUTION-16(一次 run 的结局里必须有「停住了,还能接着跑」这一档;
  2026-08-21 立,问题台账 C1 ③):
  - **引擎的 run 结果今天只有成功与失败两档,于是每一种「停」都被归档成「完」。**
    HITL 那条路已经把这个洞暴露过:`runner.py` 检出 HITL 中断后返回的字典里**没有
    `success` 键**,而宿主的 `_result_success`(`run_manager.py`)注释写着「Absent →
    treat as success」,于是一次**正在等人回答**的 run 被记成 `success`。断点会踩进
    同一个洞。所以这条决策的主语不是断点,是**结局的词表**:加上「停住了,还能接着跑」
    这一档,断点与 HITL 都落在它上面。
  - **两条执行路径都要判,不是只判首跑。** 首跑与 resume 在 `graph.invoke` 之后**都是
    无条件**走「成功收尾」的,所以 resume 撞上同一个断点也会被记成跑完。判据统一成一句:
    **`get_state(config).next` 非空 = 这一次没跑到头**;非空且带 `__interrupt__` 载荷 =
    在等人回答,非空且没有载荷 = 停在断点上。
  - **借 LangGraph 的静态中断,拒绝在相位内部塞动态 `interrupt()`。** 后者要求每个相位
    自己去查一遍「我是不是断点」,于是**断点的存在与否改变了被观察者的代码路径**——
    而断点是外部观察手段,不该改变它观察的东西。代价照实写:`interrupt_before` 是
    **编译期**参数,所以 run 起飞之后新设的断点对**这一次**不生效,下一次才生效;
    这一点要让用户看得见,不能让他对着一个不生效的断点等。
  - **引擎收的是一个显式参数,不是去 `runtime_config` 里翻键。** `assemble_graph` 已经
    收着 `runtime_config`,让它顺手读一个 `breakpoints` 键更省事——但那等于把 Studio 的
    存储格式焊进引擎契约。引擎该知道的只有「这些相位之前停下」(显式优于隐式)。
  - **复用 `InterruptedEvent`,并让它说出停下来的**理由**。** 它已经带着这次停顿需要的
    全部字段(`phase_name` + checkpoint 三件套 + 可选 `question`),另造一个平行事件会让
    每一个消费者把同一件事处理两遍。但**不能靠「`question` 是空的」来区分**:那既可能是
    断点,也可能是一次问题没提取出来的 HITL,而这两者对用户的要求完全不同(一个要**回答**,
    一个只要**继续**)。所以补一个显式的 `reason`(`awaiting_human` / `breakpoint`),
    让「该做什么」是读出来的,不是猜出来的。
  - **run 的状态沿用 `paused`,不新造一个。** 它与 Pause 按钮造出来的那个 `paused` 是
    同一件事:有 checkpoint、能续、没产出。F7 给 `paused` 定的按钮对(Resume + Stop)
    因此直接适用,不必发明第三对。
  - **断点存在 skill 的工作区,不存在某一次 run 里。** 设断点发生在「还没跑」的时候,
    而它要影响的是「接下来每一次跑」;存进 run 就意味着每跑一次重设一次。落点选
    `.workspace/runtime_config.json`,因为那正是「Studio 知道而 skill 文件不知道」的
    东西的既有归属(compare 候选、node params 已经住在那里)。
  - **断点只有写接口,没有自己的读接口。** `PUT` / `DELETE
    /api/skills/{id}/nodes/{node_id}/breakpoint`,两者都回**整份清单**(调用方不必
    自己算集合变成了什么);读断点就是读 `runtime_config`——画布**本来就握着**那份
    文档(`Workspace` 的 `/skills/{id}/runtime-config` SWR),而且它已经在这两个写接口
    发出的 `runtime_config_changed` 上重新取数。再给这份文档的一个字段开一个读接口,
    等于给同一份真相开第二个副本,而两个副本可以互相矛盾(SSOT 读取原则)。
    注:`node-llm-params` / `compare-candidates` 确实各有一个 scoped 读接口,但它们的
    消费者是 Properties 面板——**手上没有那份文档**;画布有,所以同样的形状在这里
    只剩代价。
  - **「设了断点」与「这次停在这里」是两件事,节点上分开表达。** 前者是对 skill 的
    **常驻选择**:没有任何 run 时它也成立,一次 run 结束后它继续成立;后者是**这一次**
    run 的结局。所以节点数据里是两个字段:`hasBreakpoint`(常驻标记,画布上一枚
    实心点——`CircleDot`,沿用 gdb 前端以降每个调试器的画法,不需要图例;只用字形
    不用颜色,画布上颜色留给严重程度,决策 2026-08-08 D2)与 `status: 'breakpoint'`
    (这次停在这里,由 `InterruptedEvent.reason` 投影而来)。合成一个的话,一块空板子上
    就没法看出下一次会停在哪。
  - **停在断点上的 run 不封盘。** 封盘的含义是「这个 run 不会再被写了」,而它正要被
    继续写;auto-commit 与 report 都挂在封盘后面,都是在描述一个跑完的 run。所以它走
    的是 Pause 按钮那条路的同一个出口(`_record_paused_run`:写 metadata、存档、发
    `paused` gate,不封盘),两种暂停留下的现场因此完全一样——区别只在**谁喊的停**。
  - **续跑要重新被告知断点,而且要能再停一次。**(2026-08-22 真机走查补)resume 是
    **重新编译一次图**,`interrupt_before` 是编译期参数,所以不把断点集合再传一遍,
    续跑就是一张**没有任何断点**的图,会一路冲过剩下每一个断点。同理,续跑撞上下一个
    断点时,它的结局仍然是「停住了,还能接着跑」——而 Studio 这一侧原本在出口处把
    引擎的三档又压回两档(`"success" if res.success else "failed"`),于是那种停被记成
    **失败**。这和 worker 那个洞是同一个形状,修法也一样:出口先问「停在哪」,再问成败。
  - **断点是「顺便问一下」,不是「必须问到」。**(2026-08-22 CI 补)续跑要被告知断点,
    而断点住在 skill 的工作区里,于是读它先得把 skill id 变成一个目录——**而这台 Studio
    可能没有那个目录**:skill 关掉了,或者这次续跑发生在从没打开过它的 sidecar 里。
    run 是从**它自己的冻结 artifact 与 runtime-state 快照**续起来的,不是从活的 skill
    目录续起来的,所以"没打开"不是一次失败:没人打开过的 skill 上不可能有人设过断点,
    答「没有」就是全部真相。先前拿会抛 404 的 `resolve_skill_dir` 去读,把每一次这样的
    续跑变成 `SKILL_NOT_FOUND`,还盖掉了调用方真正该看到的 `state.*` 运行时状态错误。
    因此同一次查找按调用方的需要出两种形状:`resolve_skill_dir`(请求是**关于**这个
    skill 的,没有目录就进行不下去,抛)与 `opened_skill_dir`(请求只是**顺便问问**,
    没有目录也是一个成立的答案,返回 `None`)。
  - **停住期间新设的断点,在续跑时生效。** 这一条照搬每一个成熟调试器的取舍(gdb 的
    `break` 之后 `continue`、浏览器 devtools、PyCharm):**程序停着的时候设的断点,
    继续跑时算数**,否则用户为了多停一处就得重跑整个 run。它与上面「run 起飞之后新设的
    断点对这一次不生效」不矛盾——那句说的是**正在跑**的图没法重编译;而续跑本来就要
    重新编译一次图,所以读的是**当下**的断点集合,代价为零。
  - **续跑必须被看见:它的事件要送到看的人手上,它的结束要广播。**(2026-08-22 真机
    走查补)首跑跑在 worker 里,事件经进程队列送到 run 的实时流;**续跑跑在 HTTP 请求
    里**,原本既没有 event subscriber(事件只落进 trace 文件),`record_resume_result`
    也从不发那条 run gate。于是按下 Resume 之后,磁盘上的 run 已经跑完,而画布还停在
    它停下来那一刻的样子,直到你重开 app。实时视图是**由事件搭出来的**,所以一段不发
    事件的执行无论跑得多正确都是不可见的。修法:resume 端点向 run 记录要一个 sink
    (`observe_resumed_run`),把这段的事件塞进同一条实时流;结束时按结局走
    `_record_paused_run` 或 `_finalize_terminal_run`,两者都会发 gate。**代价照实写**:
    引擎调用同步跑在事件循环上,所以这些事件是**请求返回时一次性到达**,不是边跑边到;
    要边跑边到就得把这次调用挪出事件循环,那是另一件事、另一份风险,这里不做。
  - **停在断点上不是「有人在问你问题」。**(2026-08-22 真机走查补)`hitl-prompt.ts` 原本
    见到任何 `interrupted` 就当作 HITL,取不到 `question` 就自己补一句 "Run paused for
    human input.",于是断点停下来时画布弹出「HUMAN INPUT REQUIRED」和一个答题框,
    而根本没有问题可答——**正是本决策加 `reason` 要防的那件事**。判据只认显式的
    `reason === "breakpoint"`;**没写 reason 的旧 trace 仍然按 HITL 处理**,因为两种错
    不对称:把断点当问题只是多一个没人用的框,把真问题当断点会让人永远等不到那个框。
  - **停住的 run 谁来接手:谁续跑它、谁看着它,谁就在这里持有它。**(2026-08-22 真机走查补)
    上一条(「一次停顿不结束这个 run 的事件流」)保住的是**内存里那条记录**的流,而记录只
    活在起这个 run 的那个进程里,进程一没它就没了。**关掉 app 再打开、对着一个停住的 run
    按 Resume**,走的就是另一条路:磁盘上这个 run 往前跑了一个相位、正确地结束了,而屏幕上
    什么都没动,直到再重开一次 app。原因是 `observe_resumed_run` 找不到记录就返回 `None`
    (事件无处可送),`record_resume_result` 也因为没有记录而不发 gate(结束无人知晓)。
    **`stop_run` 早就学会了只凭 run 目录结束一个本 sidecar 没起过的 run**(台账 C1 ④),
    因为**结束是一次写**;而**续跑不是**——它会**产出**:跑的时候有事件,结束时有结局,
    而「一个 run 的流和它的观众」正是记录这个东西存在的意义。所以续跑或观看一个停住的 run
    时,本 sidecar **从那份持久产物把记录重建出来接手它**——借的是进程监督器(systemd /
    容器运行时)**重新接管一个不是自己拉起来的服务**、而不是再起一个的做法;**拒绝**照搬
    的部分是「连 worker 一起接管」:这里根本没有 worker 可接(续跑就跑在这次请求里),
    所以记录里那两个进程槽位**留空**,而不是塞一个能被误当成进程去发信号的替身。只有
    `paused` 会被接手:跑完的 run 不会再写一个字,`running` 的属于正握着它的那一方。
  - **「这个 run 会不会归档 skill」跟着 run 走,不跟着 sidecar 走。** 接手时这件事必须
    有答案,而它原本只存在内存记录里,于是接手方只能猜——**两个猜法都会错在某个人身上**:
    把一次旁路实验当正式 run 去归档,会把用户在它跑的时候改的东西一并提交;把正式 run 当
    旁路,快照就悄悄不出现。它本来就是「这个 run **是什么**」的属性(旧注释原话:a
    property of what the run IS),所以**写进 run 自己的 metadata**,默认取**不归档**那
    一侧(错向这边只是少一份快照,错向另一边会动用户的工作区),由 `start_run` 这唯一一处
    普通 run 显式声明 `auto_commit=True`。记录里那份重复的同名字段一并删掉——同一个事实
    只留一个权威(SSOT)。
  - **「顺便问一下」的查找要有总答案,run 这一侧同样适用。**(2026-08-22 CI 补)接手前
    得先问「这里有没有这个 run、它是不是停着的」,而 `_metadata_for` / `run_dir_for` 都是
    **会抛 404 的**查找(skill 没打开就 `SKILL_NOT_FOUND`,run 不在就
    `RESUME_CHECKPOINT_NOT_FOUND`)。拿它们去问,等于让**顺便问的一句**把整个 resume 端点
    变成 404,盖掉调用方真正该看到的 `state.*` 运行时状态错误——和 `opened_skill_dir` 那条
    是同一个错误的第二次。所以同一次查找在这里也出两种形状:`_metadata_for` /
    `run_dir_for` 给「请求是**关于**这个 run 的」调用方,`_recorded_metadata` /
    `_run_dir_if_here` 给「只是**问问**有没有」的调用方。
  - **「停住了」不等于「在问你」,`status` 字段说的是前者。**(2026-08-22 真机走查补)
    上一条(「停在断点上不是有人在问你问题」)按 `reason` 排掉了断点停顿,而弹出答题框的
    根本不是那个停顿事件——是续跑写进同一条流里的**审计记录**
    (`resume_applied`,payload 带着这次续跑的结果 `status: "paused"`),
    而判据的最后一行是 `status === 'paused'`。**那个字段说的是 run 的状态**(没有东西在
    执行、还能继续),「被人问住了」只是通向这个状态的其中一条路;拿它当「有人在问你」,
    等于任何一条捎带这个状态的记录都会变成一个问题。所以判据里删掉它:只有**事件自己说
    它在问**才算——hitl 类事件类型,或 `status === 'waiting_for_human'`(这一条是用词说的,
    不是推断的)。**这不与「不许靠 question 为空来判断」冲突**:那条讲的是**真问句缺失时
    不能反推**,这条讲的是**运行状态不能正推**,两条都指向同一句话——问不问人,只认显式的说法。
  - **一次停顿不结束这个 run 的事件流。**(2026-08-22 真机走查补,C1 ③ 收官)上一条
    (「续跑必须被看见」)给续跑装了事件出口,而**出口接的是一条已经关掉的管道**:worker
    在停顿时退出,drain 循环随之结束,并像收尾一个跑完的 run 那样往流里塞终止哨兵、清空
    所有订阅者。可是**续跑写的是同一个 run 的后文**——同一个 run id、同一批看的人。
    在停顿处结束事件流,和把停顿归档成跑完是同一个错误换到下一层:**流属于 run,而 run
    还没结束**。判据因此和结局的词表对齐:只有终局(成功/失败/被取消/worker 无声死亡)
    才关流;停顿保持打开,等下一段。
  - **`run_ended` 得读它的 `status`,不能只看事件名。** 引擎在 `graph.invoke` 返回时发
    `run_ended`,而一个停住的 run **也会返回**,所以光凭事件名分不出「结束了」和「停住了」。
    引擎本来就说清了:`RunEndedEvent.status` 是 `completed | crashed | interrupted`
    (`callbacks/events.py`),前端 `RUN_ENDED_EVENT_VERDICT` 也早把 `interrupted` 映成
    `paused`——只是**判断「这个 run 完了吗」的那两处根本没去读**(`useRunStream` 的终局
    闸门、F7 copilot 分析条)。于是停住的 run 被判成跑完:socket 不再重连,分析条邀请你
    分析一段还没跑的活。修法是把这个判断收成**一处**(`endsTheRun`),走与 verdict 同一张
    表,两边不可能再各说各话。**没写 status 的旧 `run_ended` 算结束**:把停顿误判成结束会
    冻住实时视图,把结束误判成停顿会让 socket 无限重连重放整份日志,而停顿从字段存在起
    就一直写着 `interrupted`。
  - **边界节点不能带「断点」这个词。**(2026-08-22 真机走查补)Output 端点按「产出它的
    相位里最坏的那个」取状态,于是继承了 `breakpoint`,屏幕上写着 Output 是个断点——
    可断点是设在**相位**上的,端点不是相位,谁也没法在它上面设断点。端点上成立的是
    底下那句更一般的话:**没有东西到达,也没有东西在执行**,那就是 `paused`。边的状态
    表早就这么收(`buildEdges` 的 `breakpoint: 'paused'`),这一步只是让同一条规则走到
    边所通向的那个端点。
  - **整图 iterate 的 skill 直接拒绝断点。** graph 级 `iterate` 是「整张图每个 item 跑
    一遍」,而且那些轮次是由 iterate wrapper 自己驱动的:停在某一轮里既报不出去也
    续不回来,而「停在相位 X 之前」也说不清是哪个 item 的 X。`assemble_graph` 在收到
    非空 `pause_before` 且 manifest 带 graph 级 iterate 时**当场报错**——交回一个
    永远不会触发的断点比报错更坏(fail fast,在边界校验)。相位级 iterate 不受影响:
    那是一个节点内部循环,停在它**之前**含义明确。
- 原话/来源: 用户 2026-08-19「运行时观测」模块拆解(台账 C1 ③「节点级暂停缺」)。
- 测试: 引擎——`packages/graph-agent/tests/core/test_a_graph_stops_before_the_phases_you_named.py`
  (`pause_before` 落到 `interrupt_before`、再 invoke 一次能跨过去、没点名就一路跑完、
  整图 iterate 拒绝断点)+ `tests/runner/test_a_run_can_stop_where_you_asked.py`
  (`paused_at` 说出停在哪与为什么、停住的 run 不能同时自称跑完、中断事件说出是哪一种);
  宿主——`apps/studio/backend/tests/services/test_a_run_can_stop_where_you_asked.py`
  (带 `paused_at` 的结果不再被读成成功、worker 报 `paused` 且带上停在哪个节点、
  停住的 run 不封盘、gate 说 `paused`、断点读写落在 `runtime_config`、传给引擎的是
  排好序的节点名)+ `tests/routers/test_a_breakpoint_is_something_you_set_on_a_node.py`
  (写接口回整份清单、清一个没设过的不算错、越界节点名被拒、变了才广播);
  前端——`src/utils/a-run-that-stopped-says-where.test.ts`(reason 决定节点是
  `breakpoint` 还是 `paused`,收尾判据不覆盖已停住的节点)、
  `src/components/nodes/a-node-carrying-a-breakpoint-shows-it.test.tsx`(空板子上也带标记)、
  `src/components/GraphCanvas.test.tsx`(节点菜单一条目双向、非节点右键不出现)、
  `src/api/a-breakpoint-write-answers-with-the-whole-list.test.ts`(只写不读)。
  底栏 Resume + Stop 由 F7 既有实现直接覆盖(`center-action-bar.tsx` 的 `paused` 分支)。
  **续跑一侧(2026-08-22 补)**:`apps/studio/backend/tests/services/test_a_resume_goes_on_visibly.py`
  (续跑结束会广播 gate、再撞上断点报 `paused` 而不是通过、这段的事件到得了看的人手上、
  没有本地记录时没人可送、再停一次不封盘、三档结局在出引擎时不被压回两档、
  没打开的 skill 上「没有断点」而不是报错、读断点读不到也不许盖掉运行时状态错误);
  `apps/studio/backend/tests/services/test_a_pause_does_not_end_the_story.py`
  (停住的 run 不关流、不清空看的人、下一段事件送得到同一批看的人、终局仍然关流、
  worker 无声死亡也关流、再停一次还是不关);
  `apps/studio/backend/tests/services/test_a_paused_run_can_be_taken_over.py`
  (没起过的停住 run 被接手、接手后的结束会广播、跑完的不接手、归档与否从 metadata 读、
  看一个停住的 run 不会被告知「没了」、看一个跑完的仍然收尾);
  前端 `src/utils/a-stop-is-not-an-ending.test.ts`(`run_ended` 按 status 判终局,
  没写 status 的算终局)、
  `src/components/studio/a-breakpoint-is-not-a-question.test.ts`(断点停不弹答题框、
  不遮住更早的真问题、真问题即使问句为空仍然是问题、没写 reason 的旧 trace 仍按问题处理)、
  `src/components/studio/a-record-of-a-resume-is-not-a-question.test.ts`
  (续跑的审计记录三种结局都不弹答题框、不遮住更早的真问题、`status: paused` 不算问、
  `waiting_for_human` 仍算问)、
  `src/utils/a-boundary-cannot-carry-a-breakpoint.test.ts`(端点说 `paused` 不说 `breakpoint`)。
- Status: target-design(2026-08-21 立)。
- 归属: capability `run-execution`(owner);platform `engine`(停顿机制);
  region `canvas` · `center-action-bar`(引)。

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
| RUN_EXECUTION-12 | 被看的那次 run 拥有它旁边的动作 | F3；**为什么**：trace 可以显示历史 run,而动作若问「哪次 run 是活的」就会作用在别的 run 上——Resume 续错 run、golden 量错 run、节点 compare 在有 run 的情况下拒绝执行;Pause / Stop 仍问 live,因为它们作用的是 worker 而不是记录 |
| RUN_EXECUTION-14 | 候选页签属于 compare 组,由 trace 区域渲染 | F3；**为什么**：页签的前提是「存在一个 compare 组」,句子里没有 live run，把它挂在 live 分支里，就让「从历史 run 发起对比」这条刚打开的路当场又堵死——side-run 跑完了而一个页签都没有，组存在却不可达；与 CP4 的 `Design golden` 同规则，通则见 `FRONTEND_UI_SPEC.md` §2.9b |
| RUN_EXECUTION-15 | 标记候选为当前与显示它是同一个动作,只有一个写入口 | F3；**为什么**：两者能分开写，就会分开——对比一发起，第一个候选的页签被标成当前而 trace 仍停在基线 run，点一下「已经选中」的页签才换内容，「我在看哪个候选」于是有两个答案。写入口收敛到 `showCandidate` 后，标记而不显示不可表示；候选清单由调用方传入，因为发起对比那一刻 React 尚未提交它们 |
| RUN_EXECUTION-13 | run 的 worker 用一把 OS 锁给"我在跑"作证,没人持锁的 run 结束为 `abandoned` | F8；**为什么**：sidecar 只在内存里记在飞的 run，换一个 sidecar 起来，同一个问题就有两个答案——列表答「在跑」、`pause_run` 答 `RUN_NOT_RUNNING`；锁是唯一一个持有者怎么死都会被释放的凭据，pid 会复用、心跳分不清慢 LLM 与死进程 |
| RUN_EXECUTION-11 | 报告在被打开时重新生成 | F6；**为什么**：RUN_EXECUTION-5 说它可随时重生,却没有任何入口,历史报告永远停在写它那天的渲染逻辑上;按"打开"重生是每次用户动作 O(1) 次写,且不必再引入一个要人记得 bump 的渲染器版本号 |
| RUN_EXECUTION-10 | 点了名的东西要能点开 | F6；**为什么**：输入文件与被对照的 run 从前只是文本；链接从实际目录推出,推不出就不给,点不开的链接比纯文本更坏 |
| RUN_EXECUTION-8 | 重复逐次记账 + 节点状态入表 | F6；**为什么**：求和行回答不了「哪个 item 慢/挂了」，而「跑了几次」与「一次里想了几轮」是两件事 |
| RUN_EXECUTION-9 | Failure 只收「拒绝或放弃」，纠正只计数；**报告自己没写的每一句话都过同一道截断/折行/转义** | F6；**为什么**：把每次 nudge 塞进 Failure 会淹没真失败，完全不记又丢掉「这个节点被推了六次」 |
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
