# Trace 信息架构 + 步骤流式呈现 + run 目录布局(决议)

- 日期:2026-08-09
- 状态:已批准(PM 逐条给出 12 项 UI 指令 + 4 项补充,并对本文件 §2 的三条争议裁决明确回复「我接受」),本文件为落盘决议
- 权威设计源:`docs/studio/mvp1/01_workflows/04_run-and-verify.md` §C/§D、
  `docs/studio/mvp1/02_capabilities/trace-observability/mvp1-alignment.md`、
  `docs/studio/mvp1/03_regions/timeline/mvp1-alignment.md`、
  `packages/graph-agent/src/graph_agent/callbacks/events.py`(引擎事件契约)
- 前置决议:`docs/design/2026-08-07-timeline-viewed-run-and-trace-ui-decision.md`(viewed-run 模型,本决议保留其 D1/D2,改写其 D3,作废其 D4 的一部分)、
  `docs/design/2026-08-08-studio-color-language-and-trace-density-decision.md`(颜色语言与密度,本决议保留 D1/D2/D3,作废其 D4/D5 的一部分)

---

## 1. 背景:已核实的事实

以下每条都以代码坐标或设计源坐标坐实,不含推测。

### B1. 引擎有「LLM 步骤开始」信号,没有「工具步骤开始」信号

引擎事件契约共 36 种(`callbacks/events.py` 的 `CallbackEvent` 判别联合,`events.py:497-535`):

- `prompt_captured` 在**调用之前**发出 —— `core/tracing_proxy.py:80` 的 docstring 原文
  「Emit ``prompt_captured``, then delegate to the wrapped client」,`:88` 先
  `self._emit_prompt_captured(...)` 再委派。**这是 LLM 步骤的开始信号。**
- `llm_call` 带 `input_tokens` / `output_tokens` / `response_data`(`events.py:73-85`),
  是**完成后**事件。
- `tool_call` 带 `result` 与 `duration_ms`(`events.py:88-97`),**只有完成事件,没有开始事件**。
- LLM 调用链路上**不存在流式**:`stream=True` / `astream` / `.stream(` 在
  `packages/graph-agent/src/graph_agent/` 的 LLM 路径上无命中(唯一命中的
  `core/_predict_internal/interception.py:77` 是 predict 的拦截桩,不是真实 provider 流)。

结论:「每一步开始时出现、完成后折叠」对 LLM 步骤今天就可实现;对工具步骤必须由引擎补开始事件;
「模型逐 token 打字」今天没有任何数据来源。

### B2. Trace 顶条上的联动收窄,与「Trace 要能通读」互斥

顶条现有三个联动件:收窄提示 `→ <node> N / M`(`TracePanel.tsx:455-463`)、
link 开关(`:475-496`)、以及它们背后的过滤行为 —— `useTraceFilter(traceEvents, linkEnabled ? focusPhase : null)`(`:293`),
设计依据是 `TracePanel.tsx:41-45` 注释所引的 atom #17「focus decides trace granularity」。

PM 指令要求同时删掉提示(7.1)与开关(7.4)。若只删这两件而保留过滤行为,结果是
**一个看不见、也关不掉的过滤器**;同时 PM 指令 6 要求删掉 Full Trace 面板,而
Full Trace 承担的正是「不过滤、通读取证」(见 B3)。两者叠加使「保留过滤行为」不可能成立。

### B3. Full Trace 与 Trace 的分工,在做完步骤化改造后不再成立

`04_run-and-verify.md:83` 原文定义了二者分工:

> **两个面各司其职(决议 2026-08-08 D5)**:**Trace**(Timeline 区域内的视图)= 交互式事件时间线,
> 可过滤/搜索/展开单条/与画布节点联动,用途是**定位**;**Full Trace**(独立文档)= 同一次 run 的**全文**,
> 不过滤、按节点分组通读、长内容可展开到底,用途是**通读与取证**。

Full Trace 的三项承诺是「不过滤 / 按节点分组 / 长内容展开到底」。本决议 D2(删过滤)、
D4(按节点分组的步骤条目)、D6(去固定高度框、长内容折叠而非截断)落地后,
Trace 自身同时满足这三项 —— 分工的前提消失。

### B4. Prompt Inspector 是同一信息的第二个入口

`components/PromptInspector.tsx` 是一个独立右侧抽屉(Template / Variables / Rendered 三 tab),
唯一入口是 trace 行内的「Inspect prompt」链接(`TraceEventRow.tsx:153-173`)。
它展示的内容正是 `prompt_captured` 事件的载荷 —— 而按 D4,该事件将成为「步骤开始」并在行内展开。

### B5. 搜索框的问题在共享封装被改过,不在业务组件

`TraceSearchBar` 用的是本地 shadcn 封装 `InputGroup`(`trace/TraceSearchBar.tsx:17-42`),**用法正确**。
封装本身 `components/ui/input-group.tsx` 的根容器高度是 `h-7`(28px),而
`InputGroupAddon` 的 variant 基类带 `py-2`(纵向内边距 16px)。一个 28px 高的容器内声明 16px 纵向内边距,
加上图标与输入控件,几何上无解。多轮在业务组件上调整无法收敛,因为病因不在业务组件。

### B6. 画布空白点击会关闭侧边面板

`GraphCanvas/GraphCanvas.tsx:2360-2369` 的 `handlePaneClick` 中:

```
// Clicking empty canvas clears the workspace: close the open side panel AND
// the file editor(s). It no longer opens the graph.md panel.
onPanelChange?.(null)
onCloseEditors?.()
```

### B7. run 目录布局的四个事实

- run id 用零时区铸造:`apps/studio/backend/app/services/run_manager.py:1412-1414`
  `datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%S")` + `uuid4().hex[:8]`。
- predict id 与 run **不同构**:`apps/studio/backend/app/services/predictor.py:94`
  `f"predict-{uuid.uuid4().hex}"` —— 纯 uuid,无时间戳,磁盘上无法按时间阅读。
- `latest/` 是**整目录复制**:`run_manager.py:1656-1661`
  `shutil.rmtree(latest_dir)` 后 `shutil.copytree(run_dir, latest_dir)` ——
  每次运行把整个 run 目录再存一份。`git_collab.py:230` 的 `LATEST_RUN_PATH` 判断依赖它。
- predict 与 run 同住 `.workspace/runs/`,由 id 前缀区分。

---

## 2. 决策

### D1 · 导航信息架构:区域改名 `Trace`,删除 `Full Trace` 面板

- Toolbar 第 4 格 label 由 `Timeline` 改为 **`Trace`**(`components/studio/Toolbar.tsx:20`)。
  用名词 `Trace`(一次运行的踪迹)而非动名词 `Tracing`(正在追踪这个行为):侧栏一格是**一个对象的入口**,不是一个进行中的动作。
- Toolbar 第 5 格 `Full Trace`(`Toolbar.tsx:21`)与 `TraceDocumentPanel` **整体删除**,
  `PanelKind` 中的 `"trace-doc"` 一并删除。按不向后兼容原则,同一改动里删干净,不留过渡入口。
- 区域内的三视图分流不变(`Panels.tsx:245-309`):选中边 → EdgeContextView > 所查 run → Trace 视图 > 兜底 → 运行列表。
- **命名口径**(取代 2026-08-07 D3 的三段式):**区域 = Trace**(Toolbar 第 4 格)/
  **列表视图 = 运行列表**(区域默认视图)/ **踪迹视图 = 该次运行的 Trace**。「Full Trace」这个名词退役。

### D2 · 画布聚焦不再过滤 Trace,改为滚动定位

- 删除 link 开关、删除收窄提示、**并删除过滤行为本身**:`useTraceFilter` 不再接受 `activePhase` 作为收窄条件。
- 取代行为:选中画布节点 → Trace **滚动定位**到该节点的分组标题并短暂高亮,列表内容一条不减。
- **本条作废 atom #17「focus decides trace granularity」的过滤语义**;
  「聚焦决定用户注意力落点」的意图由滚动定位承接。
- 理由见 B2:提示与开关都删掉后,保留过滤等于制造一个不可见、不可关的过滤器;
  且与 D1 删除 Full Trace 后 Trace 必须能通读直接冲突。

### D3 · Trace 顶条最终形态

自左至右,只有四件:

1. `←` 返回运行列表(保留;它是 2026-08-07 决议缺陷 A 的修复件,删掉则列表不可达)。
2. **完整 run_id**,等宽字体,不截断。
3. **状态图标徽章**:成功 ✓ / 失败 ✗ / 暂停 ⏸ / 取消,**不带文字**,文字进 tooltip;
   运行中保留脉冲点(「还在跑」是图标表达不了的持续态)。
4. `⋮` run 级动作菜单(Resume / Compare to golden / Promote to golden)。
   **报告入口从此菜单移出**,改由 D8 承接。

删除:`Trace` 标题(在两条挂载路径下 `runId` 恒有值,该分支永不渲染,属够不着的兜底)、
`Predict` 文字徽章(改图标,见 D9)、收窄提示、filter 按钮、link 开关。

### D4 · 事件行改为「步骤条目」:开始即出现,完成才折叠

Trace 的呈现单位从「一条事件一行」改为「**一个步骤一条**」,状态机为 `进行中 → 完成`:

- **LLM 步骤**:`prompt_captured`(开始)与 `llm_call`(完成)**合成同一条**。
  开始时该条**默认展开**,显示这次的模板 / 变量 / 渲染后 prompt;
  完成时就地转为「完成」并**自动折叠**为一行摘要(模型 / token / 耗时)。
- **工具步骤**:`tool_call_started`(开始,由 D14 的引擎改动提供)与 `tool_call`(完成)合成同一条,
  配对键为两者共同携带的 `tool_call_id`。开始时展示工具名与入参,完成时折叠为摘要。
- **无配对的事件**(`phase_start`/`phase_end`/`validation_*`/`retry*`/`run_*` 等)保持单条呈现,形态不变。
- 分组:相邻步骤属于同一节点时,只在该组首条上方标一次节点名(沿用 2026-08-08 D3)。

### D5 · 删除 Prompt Inspector,prompt 回到步骤条目内

- 删除 `components/PromptInspector.tsx` 及其入口链接、`promptIndex` 相关状态。
- 模板 / 变量 / 渲染后三段,作为 LLM 步骤条目展开态的三段内容就地呈现。
- 理由见 B4 + 「一个信息只有一个家」:D4 落地后,步骤开始时本就要展示 prompt,第二个入口即冗余。

### D6 · 中间结果不设固定高度框

- 删除 `TraceEventRow.tsx:292`(工具输入 `max-h-32 overflow-auto`)与
  `:325`(payload `max-h-40 overflow-auto`)的高度上限与内层滚动。
- 面板本身已有滚动;嵌套滚动是更差的交互。超长内容一律用**折叠/展开**(用户可控),
  不用固定高度截断(强加)。

### D7 · 运行结束必须有明确反馈

- 运行到达终态时弹一条 toast:成功 / 失败 / 中断三态,带耗时与 token 总数。
- 现有的「Auto-archived — revert from Local History.」(`hooks/useRunHistory.ts:186`)说的是 git 快照,
  不是运行结论,**不能替代**本条。两条语义不同,可同时存在。
- 附带缺陷:PM 报告「结束后仍显示 running」。节点状态由事件推导(`node-status.ts:106-110`,
  `phase_start`→running / `phase_end`→success,最后一条赢),而实测另一次运行三节点最终均为 Success,
  **说明并非所有情况都卡**。实施时必须先复现并定位到具体控件(节点胶囊 / Run 按钮 / 顶条徽章),
  在真正坏掉的那一层修;**未定位前不得声称已修**。

### D8 · 报告的两个入口

- **入口一**:运行结束后,Trace 末尾自然长出一条**终结条目**(结论 / 耗时 / token / **报告链接**)。
  报告是这次运行的产物,产物出现在过程末尾。
- **入口二**:运行列表每一行带报告链接。
  这需要后端把 `report_path` 从 `RunDetail` 扩展到列表项 `RunMetadata`
  (`apps/studio/backend/app/models/runs.py:104-128` 现无此字段)。
  实施时须实测 20+ 条 run 时列表接口的耗时;若逐条 `is_file()` 探测成为瓶颈,
  改为 seal 时把路径写进 run 元数据。
- `report.md` 仍是纯投影,不因为有了入口而成为第四份真相(沿用 2026-08-08 D5 的这一句)。

### D9 · 运行列表行:类型图标 / 完整 run_id / 状态徽章

- 现状缺陷:`TimelinePanel.tsx:80-102` 的 `RunRowIcon` 把**类型与状态混在一个位置** ——
  predict 用烧瓶但烧瓶自带状态色,run 直接用状态图标;同一个位置有时说「这是 predict」,有时说「这跑成功了」。
  且 run_id 被截断为 `run.run_id.slice(0, 12) + "..."`(`:170-172`)。
- 改为:**行首固定为类型图标**(run = `Play`,predict = `FlaskConical`,中性色,不承载状态)→
  **完整 run_id** → **状态图标徽章**(与 D3 同一套)。与 Trace 顶条同构,两屏读法一致。
- **predict 图标全站统一**:任何表示 predict 的地方一律 `FlaskConical`,不再出现「此处文字徽章、彼处图标」两套。

### D10 · 搜索框恢复官方 shadcn 封装,不做本地修改

- 按官方 shadcn 源恢复 `components/ui/input-group.tsx`,业务侧照官方示例使用。
- 该文件是**共享封装**,改动影响所有使用者;按仓规此类共享文件不与其他任务并行改,并需逐一真机复核使用它的界面。

### D11 · 筛选跟随搜索框

- 搜索框获得焦点时,其下方展开**一行**筛选标签,超出横向滚动,带过渡动画;失去焦点时收起。
- 焦点判定用 `focus-within`(焦点在搜索框**或**标签区内都算),否则点击标签的瞬间即失焦、标签当场消失。
- 收起**不清空**已选条件;仍有筛选生效时在搜索框内以计数提示,不回到顶条。

### D12 · 画布空白点击不再关闭侧边面板

- 删除 `GraphCanvas.tsx:2367` 的 `onPanelChange?.(null)`。
- 仅删这一行:取消节点选中(`syncCanvasSelection(null)` / `onNodeDeselect`)是画布自身语义,保留;
  `onCloseEditors?.()` 不在本次指令范围内,保留。

### D13 · run 目录布局与命名

- **run id 用系统本地时间**铸造,不再用 UTC(`run_manager.py:1412-1414`)。
- **predict id 与 run 同构**,仅加前缀:`predict-<本地时间戳>_<uuid8>`(`predictor.py:94`)。
- **删除 `latest/`**(`run_manager.py:1656-1661` 的 rmtree + copytree,以及
  `git_collab.py:230` 依赖它的判断)。「最新一次」改由 UI 表达:运行目录按修改时间倒序,最新一条带 `latest` 小徽章。
- **predict 与 run 分目录存放**(predict 不再写进 `.workspace/runs/`)。
  磁盘分开,但 **UI 仍是一个列表** —— predict 行以 `RunMetadata.kind` 区分(04_run-and-verify.md C7 / 2026-08-07 D2 不变),
  因此 `list_runs` 必须同时扫描两个目录。
- 按不向后兼容原则:已存在的 run/predict 目录**直接丢弃**,不写迁移。

### D14 · 引擎补 `tool_call_started`(engine 侧契约)

落在 `packages/graph-agent`,由独立 PR 交付:

- 新增 `ToolCallStartedEvent`:`event_type="tool_call_started"`,字段
  `tool_call_id: str` / `phase_name: str` / `tool_name: str` / `args: dict` /
  `parent_node_id: str | None` / `node_type: str | None`;加入 `CallbackEvent` 判别联合与 `__all__`。
- `ToolCallEvent` 新增**必填** `tool_call_id: str`。一次 agent 轮次可并发多个工具调用,
  只靠 `(phase_name, tool_name)` 无法正确配对,配对键必须显式。
  id 优先取 provider 自带的 tool call id,取不到再 mint `uuid4().hex`;同一次调用两事件必须相同。
  **必填不给默认值**(让非法状态不可表示);已落盘旧 run 因此无法反序列化,按不向后兼容原则直接丢。
- `args` 在两个事件上**都保留**。`ToolCallEvent` 必须独立可读 ——
  它被持久化、被回放、被不做事件配对的消费者(metrics / golden eval)读取;
  为消灭这点重复而强迫所有消费者 join 两个事件是错误的抽象。
- 三个发射点(`middleware/tracing.py:78`、`callbacks/tracing.py:259`、
  `core/graph_assembler.py:2148`)逐一审计:只在**真正先于执行**的发射点补开始事件,
  事后转换型的发射点不得伪造开始时刻;但 `tool_call_id` 三处都要填。
- 走现有 `on_event` 通道分发,不新增 `on_tool_call_started` 回调方法(YAGNI)。

---

## 3. 验收判据

因果验证,逐条要有可复核证据:

1. Toolbar 只剩 5 格,第 4 格 label 为 `Trace`,`trace-doc` 面板与 `TraceDocumentPanel` 在
   `apps/studio/frontend/src` 中 grep 为 0 命中。
2. 选中画布节点后,Trace 事件条数**不变**(收窄行为已删),且列表滚动到该节点分组。
3. Trace 顶条元素恰为四件(`←` / 完整 run_id / 状态图标徽章 / `⋮`),真机量测无截断。
4. 一次真实运行中,某个 LLM 步骤与某个工具步骤在**开始时**即出现于列表并处于展开态,
   在**完成后**自动折叠 —— 以真机录屏或分帧截图为证,不接受静态截图。
5. `PromptInspector` 在 `apps/studio/frontend/src` 中 grep 为 0 命中;
   prompt 三段可在步骤条目内读到。
6. `max-h-32` / `max-h-40` 及其内层 `overflow-auto` 在 `TraceEventRow.tsx` 中为 0 命中。
7. 运行结束弹出结论 toast;PM 报告的「结束后仍显示 running」已定位到具体控件并修复,
   报告中写明它原本坏在哪一层。
8. 运行列表任一行可直达该次报告;Trace 末尾有终结条目且含报告链接。
9. 运行列表行首图标只表达类型(不随状态变色),run_id 完整显示,状态由独立图标徽章表达。
10. `components/ui/input-group.tsx` 与官方 shadcn 源逐字一致(diff 为空);
    使用它的每一处界面真机复核无回归。
11. 搜索框聚焦时筛选标签单行出现、可横向滚动、点击标签不会使其消失;失焦收起且不清空条件。
12. 点击画布空白不再关闭侧边面板。
13. 新跑一次 run 与一次 predict:两者 id 均为 `[predict-]<本地时间戳>_<uuid8>`,
    时间戳与系统时钟一致;`.workspace/runs/` 下无 `latest/` 目录;predict 不在 `runs/` 下;
    UI 运行列表仍同时显示两者。
14. 引擎侧:一次工具调用产生成对的 `tool_call_started` → `tool_call`,`tool_call_id` 相同;
    开始事件先于工具体执行;`tool_call_id` 缺失时构造失败。三条引擎门禁全绿。

---

## 4. 明确不做

- **LLM 输出逐 token 流式**。引擎的 provider 调用链路当前完全不流式(B1)。
  要做需先打通 provider streaming、定义增量事件、处理传输与背压,属独立大件,另行排期。
  本决议交付的是「每一步何时开始 / 在做什么 / 何时完成」,**不是**模型逐字打字。
- **run 概要中间层**(04_run-and-verify.md D3 的 target-design)不在本轮范围。
- 批量运行 UI、模型对比机制:不碰。
- 不为旧 run/predict 目录写迁移或双读。

---

## 5. 本决议取代/作废的既有记录

| 既有记录 | 处置 |
|---|---|
| 2026-08-08 决议 D5「Trace 定位 / Full Trace 通读取证 两个面各司其职」(`04_run-and-verify.md:83`) | **作废分工**;Full Trace 面板删除,Trace 一个面同时承担。D5 中「report.md 仍是纯投影」一句保留 |
| 2026-08-08 决议 D5「report.md 入口在身份条 `⋮` 菜单」 | **改址**至本决议 D8 的两个入口 |
| 2026-08-08 决议 D4「筛选按需 Popover 挂在身份条」 | **改址**至本决议 D11(筛选跟随搜索框) |
| 2026-08-07 决议 D3 三段式命名「区域=Timeline / 视图=Trace / 文档=Full Trace」 | **改写**为本决议 D1 的两段式(区域=Trace / 运行列表 + 该次运行的 Trace) |
| 2026-08-07 决议 D4「`Link views` 换 Switch」 | **作废**;link 开关整体删除(本决议 D2) |
| atom #17「focus decides trace granularity」的**过滤语义** | **作废**;改为滚动定位(本决议 D2) |
| `04_run-and-verify.md` D8「Prompt 透视(PromptInspector)」 | **改址**至步骤条目内(本决议 D5) |

`04_run-and-verify.md` 的 C7(predict 同列表、以 `kind` 判别)、
2026-08-07 D1(viewed-run 状态模型)、D2(`RunMetadata.kind`)、
2026-08-08 D1(`--primary` 不做文字色)/ D2(颜色只表达严重度)/ D3(无边框 ghost 行)
**全部保持有效,不受本决议影响**。

---

## 6. 实施切分,以及每个 PR 必须同步更新的设计源

一个 PR 一件事;`docs/studio/mvp1/02_capabilities/trace-observability/mvp1-alignment.md`
与 `docs/studio/mvp1/03_regions/timeline/mvp1-alignment.md` 受哈希锁保护
(`docs/studio/mvp1/_audited-ready-hashes.json`,校验器 `apps/studio/backend/tests/test_doc_hash_lock.py`),
**改动它们的 PR 必须在同一个 PR 里重钉哈希**。

| PR | 内容 | 必须同步更新的设计源 |
|---|---|---|
| 0 | 本决议文件 + `04_run-and-verify.md` 的 C8 / D 段落改写 | `01_workflows/04_run-and-verify.md`(未上锁) |
| A | D1(改名 + 删 Full Trace)· D12(画布点击不关面板) | `03_regions/timeline/mvp1-alignment.md`(重钉哈希) |
| B | D2(删联动收窄,改滚动定位)· D3(顶条)· D9 的 predict 图标统一部分 | `02_capabilities/trace-observability/mvp1-alignment.md`(重钉哈希) |
| C | D10(恢复官方 InputGroup)· D11(筛选跟随搜索) | `docs/development/FRONTEND_UI_SPEC.md`(共享封装不得本地魔改的规则) |
| D | D4 的前端部分(步骤条目 pending→done)· D5(删 PromptInspector)· D6(去固定高度框) | `02_capabilities/trace-observability/mvp1-alignment.md`(重钉哈希) |
| E | D14(引擎 `tool_call_started`) | `docs/engine/mvp1/` 对应机制档 |
| F | D7(结束 toast + 定位「仍显示 running」) | — |
| G | D8(报告两入口,含后端 `RunMetadata.report_path`)· D9(列表行重排) | `03_regions/timeline/mvp1-alignment.md`(重钉哈希) |
| H | D13(run 目录布局与命名) | `02_capabilities/run-execution/mvp1-alignment.md`(如上锁则重钉哈希) |

PR-E 合并后必须重建 vendor 快照
(`uv run python apps/studio/backend/scripts/build_vendor.py` + `compileall` 预热),
否则桌面 app 的 sidecar 仍从冻结快照 import 旧引擎,新事件被 `extra_forbidden` 拒绝
(AGENTS.md「Workflow Pipeline」第 7 条)。
