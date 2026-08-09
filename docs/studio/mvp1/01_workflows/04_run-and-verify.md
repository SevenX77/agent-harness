# 04 · 运行与验收(predict + run + trace + golden) — Workflow 节点

> **Tier**: workflow
> **旅程**: predict 试飞 → run 真跑 → trace 去黑盒 → golden 验收对比
> **上游** [03 compile](./03_compile.md)(绿灯解锁);**下游失败** → [05 debug](./05_debugging.md)。
> **走查完整记录**(全部 atom actions + 决策 + 原话 + 测试关键点)。

## 旅程脊柱
**predict(硬前提:验证逻辑+schema)→ run(真跑)→ trace(看)→ golden(验收 diff)**
- compile-pass 解锁 Predict;predict-pass 解锁 Run。
- **predict 是 run 的硬前提**;**golden 不是前提**(只决定 agent 节点用哪份 mock)。
- input / validate / batch 都是**节点/run 配置**,不是 predict 的独立议题。

---

## B. predict(试飞)
### Atom actions
| # | 动作 | 区域 | status |
|---|---|---|---|
| B1 | 点 [Predict] 触发试飞 | 动作条 | live(onPredict=handlePredict→postPredictRun;Workspace.tsx:2655 / 2115) |
| B2 | 选测试输入(节点自身 io 配置,含 G2「任意节点导入文件→注入黑板」) | i/o 面板 | (配置项) |
| B3 | validate 输入合 schema(predict 流程内一步,非独立) | — | backend live |
| B4 | logic 节点真跑(确定性、不烧 token) | canvas | backend live |
| B5 | agent 节点走 mock(无 golden→启发式占位 / 有 golden→吐 golden) | canvas | backend |
| B6 | 409 守卫:predict 来源 trace 不可晋升 golden | — | backend-only |
| B7 | stage 推进 predict-pass → 解锁 Run | 动作条 | live(predict-pass 已置位;Workspace.tsx:2137 / 2175,门控 handleRun:2156) |

### 决策
- **predict 是 run 硬前提**(P6);golden 非前提;mock 由 golden 状态自动决定(g-b),无手动选择器。
- input/validate/batch 是配置,非 predict 独立议题 → 撤回伪问题 3-1/3-2/3-5。
- predict 触发改"i/o 面板选已导入文件 → 直接 predict"(路径式),废弃 PredictInputDialog。

### 原话(留底)
> "predict是硬前提, 但是golden不是. predict的任务是把逻辑跑通, 确认逻辑、输入输出schema等等真的没问题, 才能进入run; 有没有golden的区别只在于predict在agent节点拿哪个mock数据输出而已"
> "input 和batch 都是节点配置问题, 和predict无关, predict和run就是按照配置来跑就行了"

### 测试关键点
- predict 不过 → run 被门控挡;logic 真跑 / agent 走 mock;mock 选择(无→占位/有→golden replay);409:predict trace 不能固化为 golden。

---

## C. run-execution(真跑)
### Atom actions
| # | 动作 | 区域 | status |
|---|---|---|---|
| C1 | 点 [Run] 触发真跑 | 动作条 | live(onRun=handleRun;Workspace.tsx:2656 / 2153) |
| C2 | 发起单次运行(startRun → POST /runs) | — | live(startRun 已被 handleRun 调用;Workspace.tsx:2165 → 后端 runs.py:37) |
| C3 | 后端 spawn run_skill 跑真引擎、落盘 final_state/metrics/trace | 后端 | live |
| C4 | 运行状态指示(运行中/暂停/失败/成功) | 动作条·画布 | live(阶段机 center-action-bar.tsx:10-71 + handleRun 置 running:2160;画布态 statusByNodeId) |
| C5 | 节点呼吸灯 + 红绿(随执行逐个亮) | 画布 | live(statusByNodeId=deriveNodeStatuses(runStream.events) 已传画布;Workspace.tsx:665 / 2608 → build-nodes.ts:270 / 375) |
| C6 | focus 自动跟随当前运行节点 | 画布 | target-design(G9) |
| C7 | Run 历史列表(run_id/状态/耗时/token;predict 行同列表、以 `RunMetadata.kind` 判别仅 icon 区分) | timeline | live(2026-08-07) |
| C8 | 命名正名:**区域=Trace**(Toolbar 第4格)/ 区域默认视图=运行列表 / 该次运行的踪迹视图=Trace。"Timeline"与"Full Trace"两个名词退役 | toolbar | target-design(D1 决议 2026-08-09,取代 2026-08-07 D3 的三段式命名) |
| C9 | 批量运行(选多个输入各跑一次) | i/o 面板 | orphan(后端 live) |
| C10 | 命名序列(chapter1/2…)建议自动批量 | i/o 面板 | target-design |
| C11 | 批量进度轮询(总数/完成/逐项状态) | i/o 面板 | orphan |
| C12 | 批量某项失败 → 显式上报不静默 | i/o 面板 | backend-only |
| C13 | 回看某次历史运行详情(行点击→完整 trace 只读回放,viewed-run 决议 2026-08-07)+ Replay 重跑 | timeline | 回看 live;Replay target-design |
| C14 | 成功运行后 autocommit + git_status | 后端 | backend-only(**归保存与发布**) |
| C15 | 运行到达终态弹结论 toast(成功/失败/中断 + 耗时 + token);归档 toast 语义不同,不互相替代 | 全局 | target-design(2026-08-09 D7) |
| C16 | 报告入口两处:Trace 末尾终结条目 + 运行列表每行(需 `RunMetadata.report_path`) | timeline | target-design(2026-08-09 D8,取代 2026-08-08 D5 的 `⋮` 菜单入口) |
| C17 | run/predict 目录布局:id = `[predict-]<本地时间戳>_<uuid8>`;删 `latest/`;predict 与 run 分目录存放但同列表显示 | 后端 | target-design(2026-08-09 D13) |

### 决策
- run 入口在 i/o 面板(单次=选一个,批量=选多个)。
- **batch/loop 是配置**(三处开关 + 图级/节点级/嵌套 + loop 状态机)→ **归引擎设计**;前端 UI 等引擎方案回来再做。
- autocommit 由 run 触发但**归保存与发布**;运行态节点边框动画 = settings role-test 边框动画(P1)。

### 原话(留底)
> "predict和run就是按照配置来跑就行了" · "单次Run和批量Run的入口 在io panel OK" · "运行时加线的动画(已有)和节点边框的动画(在setting里面的role test, 测试时的边框动画统一)" · "存档应该和发布分发放一起, 都是git的功能"
> batch/loop 完整原话(story-deconstruction + 三处开关 + 图级 range 例)→ 引擎契约 [`02-iterate`](../../../engine/mvp1/02-mechanism/04-run-outer/02-iterate/mvp1-alignment.md)。

### 测试关键点
- run 需 compile-pass 且 predict-pass;run_skill 真跑落盘;节点灯随真实 run 事件亮;成功 run → autocommit;批量某项失败显式上报。

---

## D. trace-observability(去黑盒)
### 核心概念:线上 dot = 节点间状态机转移点
dot = 两节点之间的"中间节点"(langgraph edge),代表**上节点 end 后、下节点 start 前的所有操作**(黑板 reduce/聚合、输入文件注入、输出落盘、截断/摘要/存储)。点 dot → ① 看该刻黑板内容 ② 看"上节点 end→下节点 start"的全部操作记录。并联线从 dot 出发 = 并联节点输入由此黑板统一筛选分发。
**dot 双态(PM 2026-07-02 扩充)**:未跑之前 dot 也要像 node 的 io 一样给出**静态黑板字段推断**("跑到这个 dot 时黑板上应该有哪些字段",逐边不同,随 io 声明/拓扑编辑即时更新);跑后切换为该 run 的真实快照/操作记录。原话与推导规则留底于 [`trace-observability` F4](../02_capabilities/trace-observability/mvp1-alignment.md)。

### 看 trace 两态(P2)
- **run 时**:自动开面板,事件流式进;**agent 输出流式 + 分类折叠摘要**(参考 agent IDE「Worked for ▾ / Explored ▾ / Thought ▾」,一行摘要点开看详情 + 末尾自然语言总结);节点灯随跑。
- **run 后**:predict/run 列表 → 点某次看 **run_id 概要**(focus 空白画布=全局)→ 点 button 看完整 trace timeline + **只读文档看完整 trace(人能读、轻度格式化)** → **focus 决定粒度**(空画布=run 概要 / 节点=该节点 trace + 文档跳该节点区块);节点间过程点线上 dot。
- **一个面同时承担定位与通读(决议 2026-08-09 D1/D2,作废 2026-08-08 D5 的两面分工)**:Trace 视图既要能**定位**(搜索 + 按需筛选 + 单条展开),也要能**通读取证**(不过滤、按节点分组、长内容折叠可展开到底、不设固定高度截断)。`Full Trace` 独立文档面板删除——它承诺的三件事在步骤化改造后由 Trace 自身满足,留着即是重复。
- **画布聚焦不再过滤 Trace(决议 2026-08-09 D2)**:选中画布节点使 Trace **滚动定位**到该节点的分组标题,列表内容一条不减。atom #17「focus decides trace granularity」的**过滤语义作废**;若既删收窄提示又删 link 开关却保留过滤,得到的是一个不可见、不可关的过滤器,并与本节「Trace 必须能通读」直接冲突。
- **呈现单位是"步骤"而非"事件"(决议 2026-08-09 D4)**:LLM 步骤由 `prompt_captured`(开始)与 `llm_call`(完成)合成一条,工具步骤由 `tool_call_started`(开始)与 `tool_call`(完成)按 `tool_call_id` 合成一条;开始时出现并展开,完成后自动折叠为摘要。**不含**模型逐 token 流式——引擎 LLM 调用链路当前不流式,那是独立排期件。

### Atom actions（04+05 去重）
| # | 动作 | status |
|---|---|---|
| D1 | run 时实时 trace 控制台:**步骤开始即出现并展开,完成后自动折叠为摘要** | live 挂载(TracePanel + useRunStream;Workspace.tsx:583 / Panels.tsx:237);步骤化呈现 target-design(2026-08-09 D4,工具步骤依赖引擎 `tool_call_started`) |
| D2 | run 后从列表回看某次完整 trace | live(viewed-run 决议 2026-08-07:Workspace viewedTrace 分流,run 结束可返回列表,历史事件与 Full Trace 文档/PromptInspector 共读同一缓存) |
| D3 | run 概要(focus 空画布=全局) | target-design |
| D4 | 看完整 trace:**单一 Trace 视图**(人读格式,按节点分组;长值折叠可展开、不截断、不设固定高度框) | target-design(2026-08-09 D1/D6:独立 Full Trace 文档面板删除,能力并入 Trace) |
| D5 | focus 某节点 → **滚动定位**到该节点分组 + 编辑器跳该节点范围 | target-design(2026-08-09 D2:过滤语义作废,改定位) |
| D6 | 点线上 dot → 双态:未跑=静态黑板字段推断;跑后=黑板状态机内容 + "上节点 end→下节点 start"操作记录 | live(双态已实现:未跑 staticEdgeInference + 跑后 edgeContextFromEvents;GraphCanvas.tsx:1429-1434,lib/edge-static-inference.ts:139) |
| D7 | 点状态 → 只读看完整黑板详情(深层可折叠) | 部分 live(2026-08-08:Full Trace 文档内每条状态的黑板/inputs/variables/prompt 完整内联、长值可展开;仍 target-design:从 trace 行单点跳到该状态) |
| D8 | Prompt 透视:模板/喂入变量/渲染后 三段,**就地呈现在 LLM 步骤条目的展开态**(步骤开始时本就要显示这次问什么) | target-design(2026-08-09 D5:独立 PromptInspector 抽屉删除,第二入口即冗余) |
| D9 | agent 节点 '+' 内联展开执行子树 | target-design |
| D10 | Validator 重试 Nudge:2/3 徽章 + 失败 Error Stack | target-design |
| D11 | 检索/筛选(事件类型 + 关键字):搜索框独占一行,筛选标签在其**聚焦时**于下方单行出现、可横向滚动、失焦收起且不清空条件 | target-design(2026-08-09 D11,取代 2026-08-08 D4 的"筛选挂身份条 Popover") |
| D12 | 失败节点亮红灯(Timeline 停 + Error Message) | placeholder |
| D13 | 模型对比:**顶部 tab** 切换看不同 llm 结果(P8);候选=节点级 model+route,运行=旁路单节点多跑(见决策) | target-design |
| D14 | 净化 PropertiesPanel(移除 selectedEdge JSON 倾倒,dot 改道本能力) | stale-code(清理) |
| D15 | 失败退路:空态 / payload 截断 / live→history 源切换以 runId 重置 | target-design |
| D16 | (引擎)推流运行态微观事件 Payload schema + 结构化前后态 diff(REQ-7) | target-design,依赖引擎 |

### 决策
- 完整 trace 文档 = **人能读、轻度格式化**(非原始 jsonl);agent 输出**流式 + 分类折叠摘要**(参考 agent IDE)。**承载形态 = 面板内的排版文档,不是编辑器**(PM 2026-08-08:panel 里不要用编辑器的样式);文档内容必须**完整**,长值折叠可展开,不做不可恢复的截断。
- **dot = 节点间状态机转移点**;P8 模型对比 = **顶部 tab**;概要=run_id 概要,focus 空画布=全局 / focus 节点=该节点 trace。
- **P8 对比运行机制(PM 2026-07-02 重定)**:候选在**节点 Properties 面板**配置(只选 model group + route,不做 role/bundle),Studio 后端按 skill+node 持久化。对比在真 run 时跑,但**不往图里注入并联节点**(实证坐实当前引擎跑不了任意"两节点同超步并联",`WorkflowState.data` 无 reducer)——改为**旁路单节点多跑**:主图用基准模型照常跑一次;Studio 抓对比节点在主 run 的 `InputDispatchEvent` 输入切片,对每个候选把**该单个 phase** 物化成 `depends_on=input` 单节点临时 skill 变体 + 候选临时 roles,走现成 `run_artifact` 各跑一遍。独立单节点 run ⇒ 不改 engine 执行、永不写主黑板、per-candidate artifacts 各自分目录。旧整图按角色扇出链(`CompareRunDialog` + `POST /runs/compare` fan-out + `run_compare.py`)删除。细节见 `00_settings-ux-spec.md §2.8` + `03_regions/properties` F5 + `03_regions/timeline` F6。
- Q4:"事件→节点态"派生器归 **trace**(run 节点灯 + debug 红灯共用)。

### 原话(留底)
> "1. 当然是人能读的, 简单调整一下格式 / 3. dot就是langgraph的中间节点(我不知道怎么描述它), 在进入一个节点之前以及从一个节点出来后的所有操作, 主要围绕状态机黑板, 还有输入文件、输出文件, 还有一些状态机操作比如截断摘要存储等等. 所以点dot看黑板状态机当时的内容, 并联线从dot出发是因为所有并联节点的输入是由这里的状态机统一筛选的; 点击dot, trace timeline显示从上个节点end, 到下个节点start之间的所有操作记录 / 4. 顶部tab吧 / 5. 概要是这一次run_id 的概要, focus在空画布意味着全局,整个graph,而不是某个节点, 如果focus在某个节点就直接显示这个节点的trace了"
> P2: "run行时自动打开这个panel, 实时看到tracing的返回结果(流式输出, agent也需要流式输出, 输出内容为摘要折叠, 点开可以看具体内容, 就和所有的copilot输出一样)…点击一个node, tracing变成该node(start-->end)最近的一次trace timeline记录, 编辑器文档直接跳到该node范围(node中间的过程点击线中间的dot)"
> agent 折叠渲染参考图 = agent IDE「Worked for ▾ / Explored ▾ / Thought ▾」可折叠分类摘要 + 末尾自然语言总结。

### 测试关键点
- run 时 trace 流式;agent 输出折叠/可展开;focus 切换(空画布→概要/节点→该节点 trace + 编辑器跳);点 dot → 黑板内容 + 节点间操作记录;trace 文档人能读;payload 截断不 OOM;源切换以 runId 重置。

---

## E. golden-eval(验收)
### Atom actions
| # | 动作 | 区域 | status |
|---|---|---|---|
| E1 | agent 节点 golden 状态机:🔘未测试 → 🟡逻辑OK → 🟢有golden | canvas | target-design |
| E2 | mock 由 golden 状态自动决定(无→占位 / 有→golden_case) | — | target-design |
| E3 | golden 创建路A(copilot 协作):入口①trace 内占位节点旁按钮 ②**predict/run 跑完 copilot 输入框上方分析 bar 弹窗**(确认→无 golden 节点自动写 golden;细化自旧 sonner 批量,见 [`copilot-assist`](../02_capabilities/copilot-assist/mvp1-alignment.md) F7) | trace/copilot | target-design |
| E4 | golden 创建路B(手动):按 io.outputs schema 自动生成空模版 json,i/o 面板手填 | i/o 面板 | target-design |
| E5 | golden 设置/文件归 i/o 面板 | i/o 面板 | target-design |
| E6 | golden 失效:改 prompt/agent 内部不失效;**仅改 output schema 致缺字段 → 编译错误,必须补才能 predict** | — | target-design |
| E7 | run 后 实际输出 vs golden **字段级 diff**(详细 diff 在 editor 分屏,**不在 properties**) | editor | target-design(useGoldenDiff orphan) |
| E8 | 409 守卫:golden 作者定/手填,非从 predict trace 捕获 | — | backend-only |

### 决策
- **g-a 取代**:golden = 逐节点作者期望值,取代现后端整次快照。
- g-b mock 自动;g-c logic 不参与;g-d 失效条件(只绑 output schema);g-e 两提示入口;g-f predict 增量价值。

### 原话(留底)
> "设计完compile没问题,第一次点击predict, 测试逻辑链路跑通没问题, agent node 状态从未测试变成逻辑OK…agent节点需要一个新状态标签, 有没有golden? 有的情况下predict按照golden输出走; golden相关设置放在i/o 面板…没有golden时,会根据输出schema自动创建一个符合schema的golden模版…一旦golden有数据了, 状态自动切换到golden, predict按照golden输出运行. run运行后可以进行实际结果和golden的diff对比."
> "g-a 取代; g-b对; g-c不用; g-d 看改什么, 改prompt、改agent内部设置都没事, 只有改输出schema后golden字段缺失需要的字段, 需要弹警告⚠️触发编译错误, 必须补上才能跑predict; g-e 两者都要(trace内按钮 + sonner批量); g-f OK"

### 测试关键点
- 状态机三态;mock 自动选;logic 不参与;失效(仅 output schema 改缺字段→编译错误);409;run 后字段级 diff;创建两路。

---

## 引擎需求(已抛出)
1. **batch/loop**(C 配置)→ 引擎 [`02-iterate`](../../../engine/mvp1/02-mechanism/04-run-outer/02-iterate/mvp1-alignment.md)。
2. **predict + golden + run 后端**→ 引擎 [`06-golden-eval`](../../../engine/mvp1/02-mechanism/05-run-inner/06-golden-eval/mvp1-alignment.md) + `07-runtime`:golden 逐节点模型 + mock-by-golden + 逐节点 diff + 失效校验。
3. **trace 后端**→ 引擎 [`02-observability`](../../../engine/mvp1/02-mechanism/06-seam/02-observability/mvp1-alignment.md):节点间操作事件 + 嵌套链路 + reducer diff。

## 整层定性
**（2026-07 对账更新)** 旧定性「后端实 / 前端虚 · 全套已建却零挂载」已过时:predict→run→trace→golden 主脊已接线(2026-06/07 PR 批量落地)——动作条 Compile/Predict/Run 阶段机 + onPredict/onRun 真处理器(Workspace.tsx:2091-2181)、startRun 真调用(2165)、predict-pass 门控真置位(2137/2156)、statusByNodeId 真跑态派生并传画布(665 / 2608 → build-nodes.ts:270/375)、useRunStream + TracePanel live 挂载(583 / Panels.tsx:237)、PromptInspector(2688)、useGoldenDiff(701)、dot 双态(GraphCanvas.tsx:1429-1434) 均已挂载。**剩余工程 = target-design 细化件(agent 分类折叠摘要 / run 概要 + 只读编辑器粒度 / 模型对比顶部 tab / 批量运行 UI / RunDetailDrawer 回看详情)+ 引擎补缺口。**
