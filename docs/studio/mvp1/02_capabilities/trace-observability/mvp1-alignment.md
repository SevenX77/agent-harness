---
module: 02_capabilities/trace-observability
doc: mvp1-alignment
status: FROZEN（2026-07-02 按代码核对:TracePanel 已挂 timeline 主路径(active run 流式)、EdgeContextView 已挂 selectedEdge、edge dot 数据 = edgeContextFromEvents 真实事件派生(假黑板已删);2026-07 对账:未跑时 dot 静态字段推断已落地(staticEdgeInference,GraphCanvas.tsx:1429-1434),双态齐备;2026-07 深核:F1 agent 折叠摘要(ToolCallSubtree/~2KB,TraceEventRow.tsx:220-280)与 F5 PromptInspector 三视图(Workspace.tsx:2688/TimelinePanel.tsx:153)均已 live,旧 orphan 过时。；目标结构已按 R4-R8 retrofit；2026-07-16 增补:F7 LLM fallback 可见性落地(纯前端消费 gateway llm_fallback 事件,PM 排队单第一优先)；2026-08-09 决议改写:F3 聚焦语义由「过滤收窄」改为「滚动定位」(D2 作废原过滤语义)、F2 删除 Full Trace 独立文档面(D1)、新增 F8 顶条形态(D3/D9)；2026-08-09 第二轮:呈现单位改为步骤(新增 F9,D4/D6)、F5 由独立 Prompt Inspector 改为步骤内三段(D5 删除该组件)、F1 补上「开始即可见」的时机契约）
binds_baseline: ./baseline.md
units: [trace-dot-blackboard, run-execution-node-status]
aligns_with: 01_workflows/04_run-and-verify.md（trace / run observability）· 01_workflows/05_debugging.md（debug trace）
---

# trace-observability — MVP1 Alignment

> **Tier**: capability | **Owns**: `trace-dot-blackboard`（dot/黑板语义）+ `run-execution-node-status` 的事件消费切面 | **现状**: TracePanel 已挂 timeline 主路径(Panels.tsx:active run→TracePanel/无 run→TimelinePanel),EdgeContextView 已挂 selectedEdge 分支;dot 数据真实事件派生;2026-07 对账:未跑时 dot 静态字段推断已落地(staticEdgeInference,GraphCanvas.tsx:1429-1434),双态齐备。 | **Related**: [baseline](./baseline.md)（双向）· `canvas` · `timeline` · `properties` · `debug-resume` · `state-engine` · `engine` observability

## 1. 定义
`trace-observability` owns making a graph run inspectable: live trace stream, run-after timeline, human-readable trace document, node-focused trace, edge-dot blackboard transitions, prompt inspection, and the shared event-to-node-state derivation.

Source workflow basis: `01_workflows/04_run-and-verify.md:75`, `01_workflows/04_run-and-verify.md:83`, `01_workflows/05_debugging.md:23`.

## 2. 数据流 / 机制（设计细节）
### F1. Live Trace While Run Is Running

- 机制: starting a run opens the trace panel and streams events。呈现单位是**步骤**而不是事件行(见 F9):
  一步在**开始时就出现并默认展开**,显示这一步在做什么(LLM 步骤显示模板/变量/渲染后 prompt,
  工具步骤显示工具名与入参);**完成后就地转为完成态并自动折叠**为一行摘要(模型 / token / 耗时 / 结果)。
- 决策: agent output should feel like copilot output —— PM 原话「running的时候…要把每一步具体做了什么都流式的显示出来,
  就和copilot一样。不要直接显示折叠结果,而是和copilot一样,等完成后再折叠」(2026-08-09)。
  关键在**时机**不在信息量:一次 LLM 调用是一次运行里最慢的一段,而它期间面板此前一个字都不说,
  等结束才打印一条完成摘要——看起来就是死的。**注意本轮不做 token 级流式**(引擎的 LLM 调用路径没有
  token 流,见决议 §4「明确不做」);做到的是「开始即可见」,不是逐字打字机。
- 原话/来源: `01_workflows/04_run-and-verify.md:79` and `01_workflows/04_run-and-verify.md:86` define live trace; `01_workflows/04_run-and-verify.md:110` keeps the PM quote.
- 测试: live events append without duplication; agent chunks collapse/expand; source switch resets by run_id.
- Status: live(2026-07 对账:TracePanel 已挂 live 路径,`handleRun`→`setActivePanel("timeline")`(Workspace.tsx:2172);agent 输出折叠已实现——tool_call 按语义 verb 分类 + args→result 子树(ToolCallSubtree,TraceEventRow.tsx:220-243),长 payload 默认折叠 ~2KB head 带展开钮(GenericPayload,TraceEventRow.tsx:255-280 / `TRACE_PAYLOAD_AUTO_EXPAND_BYTES=2048` utils/trace.ts:119);旧 orphan 已过时)。
- 归属: capability `trace-observability`; regions `timeline`, `canvas`.

### F2. Run-after Summary And Full Trace

- 机制: clicking a past predict/run shows run_id summary; a button opens the full timeline and a read-only formatted trace document.
- 决策: 运行记录必须人类可读,不是裸 jsonl;必须**完整**——长值折叠可展开,不做不可恢复的截断。
  2026-08-08 曾把职责拆成两个面(Trace 定位 / Full Trace 通读),**2026-08-09 决议 D1 撤销该拆分并删除 Full Trace**:
  两个面读的是同一份事件,拆开只是同一件事做了两遍,且「哪个面是真相」不可判定。
  定位与通读现由**同一个 Trace 视图**同时承担——搜索与筛选是用户主动的取景,聚焦只滚动不删减(见 F3)。
- 原话/来源: `01_workflows/04_run-and-verify.md:81` defines run-after behavior; `01_workflows/04_run-and-verify.md:104` records the readable-doc decision.
- 测试: summary appears for selected run; full trace opens as a grouped read-only document (no editor chrome); an oversized value is kept whole and expandable rather than truncated.
- Status: 部分 live(2026-08-07 viewed-run 决议:列表点某次 → 该 run 完整 trace 视图(一次性拉取,与 Full Trace 文档/PromptInspector 共读同一事件缓存,修复「Full Trace 永远读实时流」的脱钩);predict 行以 RunMetadata.kind 判别。2026-08-08 决议:Full Trace 去 Monaco 化为按节点分块的排版文档、删除 1200 字符硬截断(长值折叠可展开);predict 与已完成 run 的事件流由 `stream_run` 从该 run 目录回放,不再因内存 record 消失而失联。仍 target-design:run_id 概要中间层、从 trace 行跳到文档对应状态)。
- 归属: regions `timeline`, `editor`; platform `engine`.

### F3. 选中即范围(2026-08-13 决议 D6,推翻 2026-08-09 D2)

- 机制: **画布选中态 = trace 显示范围**。选中节点 → 只显示该节点的事件(边事件按 `to_phase`
  归属);选中边 → 只显示该边的边操作事件(见 F4);选中 Input → 离开输入边界的派发事件;
  选中 Output → 到达输出边界的事件;**点空白 = 全量**。范围过滤的唯一实现是
  `utils/trace-scope.ts` 的 `eventInScope`;trace 面板头部显示当前范围 chip
  (`data-trace-scope`,文案 = `scopeLabel`,与画布命名一致)并带**一键清除**按钮,
  清除 = 与点空白同一条 `handleNodeDeselect`(全部选中态一起清)。
  **run 级派生按它长在哪里分两类**(2026-08-20 修订,见下「决策」第三条):
  - **顶条那一份不受范围影响**——`run_id` 与状态徽章回答的是「这是哪一次运行、它现在
    怎么样」(F8),那是运行的身份,与读者此刻取了哪一景无关。
  - **长在列表里的、以及承诺「点开就能看到」的可操作计数,一律跟随范围**——结局行
    (`TraceOutcomeRow`)排在步骤序列末尾,它说的「Run succeeded」是对**这一串**的收尾;
    降级计数 chip(`route issues`)点下去是往这份列表里搜,数目对不上可见的黄块就是
    一句做不到的承诺。
- 决策: 本条**推翻** 2026-08-09 D2 的「聚焦只定位不过滤」,且当年的反对理由被正面化解:
  「不可见」→ 过滤严格绑定可见的画布选中环 + 面板头部范围 chip;「不可关」→ chip 一键清除、
  点空白回全量。两次裁决都在案:2026-08-09 删的是无锚点的隐形过滤,2026-08-13 立的是
  锚点即选中态、状态可见、一键可退的范围机制。
  - **2026-08-20 修订「run 级派生不受范围影响」**。原文一刀切,导致收窄到某个节点后,
    该节点的几条事件下面仍然坐着一张「Run succeeded」结局卡——它是对整次运行的判词,
    却排在一串不是整次运行的序列末尾,读起来像是这几步成功了。裁决(PM 08-19 Q5)
    要求收窄时不出现。判据不是「run 级 vs 步骤级」,而是**这个派生长在哪里**:
    身份区(顶条)属于运行本身,列表区属于当前取景。降级计数 chip 一并跟随,理由是
    它是**可操作**的——点它就是往当前列表里搜,一个点开找不到的计数比没有计数更坏。
  - **报告在 app 内打开,不交给系统默认程序**(承接 2026-08-14「编辑器该怎么出现还是
    怎么出现」)。结局行的 `Open run report` 与运行列表行的报告链接走同一条
    `onFileOpen`,以只读文档落在工作区编辑器里。为此 `RunMetadata.report_path` 改为
    **工作区相对路径**(`.workspace/runs/<run_id>/report.md`):它唯一的消费者就是这两个
    打开入口,而工作区编辑器按相对路径读文件——绝对路径只有交给 OS 时才用得上,
    而那正是被推翻的做法。
- 原话/来源: `docs/design/2026-08-13-trace-goes-glass-box-decision.md` §D6(含对 D2 的正面回应);
  历史脉络 `docs/design/2026-08-09-trace-ia-and-streaming-overhaul-decision.md` §D2。
- 测试: `utils/trace-scope.test.ts`(各范围的准入规则)、`TracePanel.test.tsx`
  (chip 呈现/清除按钮/节点范围窄化/边范围含 tamper 区/无范围无 chip)。
- Status: live(2026-08-14 落地)。
- 归属: capability `trace-observability`; regions `canvas`, `timeline`.

### F8. Trace 顶条只回答两个问题

- 机制: 顶条自左至右只有四件:`←` 返回运行列表 · **完整 run_id**(等宽,不截断,溢出靠 CSS 截断且 `title` 保留全文)·
  **状态图标徽章**(成功 ✓ / 失败 ✗ / 暂停 ⏸ / 取消 ✗,不带文字,文字进 tooltip;运行中保留脉冲点,
  因为「还在跑」是静态图标表达不了的持续态)· `⋮` run 级动作菜单(Resume / Compare to golden / Promote to golden)。
  predict 运行在 run_id 左侧加**烧瓶图标**(`FlaskConical`),与运行列表、全站其他 predict 标识同一个图标。
- 决策: 顶条只回答「这是哪一次运行」和「它现在怎么样」;其余曾经挤占该行的元素都已删除——
  `Trace` 标题(视图名两条挂载路径下恒被 run_id 取代,是够不着的兜底)、`Predict` 文字徽章(改图标)、
  收窄提示与 link 开关(过滤行为本身已按 D2 删除)、run_id 重复出现在 `⋮` 菜单里的那一份。
  状态用图标不用词,是因为文字状态在窄面板里与 run_id 争同一行宽度,而 run_id 是不可缩写的那个。
- 原话/来源: `docs/design/2026-08-09-trace-ia-and-streaming-overhaul-decision.md` §D3 / §D9;
  PM 原话「顶条只显示run_id,后面跟状态徽章,状态徽章不需要一串字,用打勾、错误等原型徽章就行,加上tooltip显示文字success等」
  「predict徽章用一个图标就可以了,而且所有ui代表predict的都要统一」。
- 测试: 顶条含完整 run_id 且 `title` 为同一字符串;状态以 `aria-label` 表达而**不**渲染 `>Success<` 字样;
  predict 视图渲染 `aria-label="Predict attempt"` 而不渲染 `>Predict<` 文字;无 run 级动作时不渲染 `⋮`。
- Status: live(2026-08-09)。
- 归属: capability `trace-observability`; region `timeline`。

### F9. 呈现单位 = 步骤(开始即出现,完成才折叠)

- 机制: 纯投影 `buildTraceSteps(events)`(`src/utils/trace-steps.ts`)把事件流合成步骤:
  - **LLM 步骤**:`prompt_captured`(开始)+ 同一节点的下一条 `llm_call`(完成)合成一条。
    按**节点**配对,因为 `prompt_captured` 不带调用 id,而同一节点的下一次完成必定属于它。
  - **工具步骤**:`tool_call_started`(开始)+ 同 `tool_call_id` 的 `tool_call`(完成)合成一条。
    按 **id** 配对而不是按位置:一个 agent 回合可以有多个调用同时在飞,谁先回来不确定
    (引擎侧契约见 PR #655 / 决议 D14)。
  - 其余事件各自成一条,形态不变;**只有完成半边、没有开始半边**的事件也自成一条完成态步骤
    (筛选会藏掉开始半边,答案是显示手上这半边,而不是把事件丢掉)。
- 默认展开态由**步骤状态**决定:进行中默认展开,完成默认折叠;**用户的手动切换优先**且此后一直生效
  (只记录被显式切换过的步骤,其余跟随状态,所以完成时会自动折叠而不会推翻读者的选择)。
- 分组沿用 2026-08-08 D3:相邻步骤同节点时只在组首标一次节点名。
- 长文本 = **固定高度文本井**(2026-08-14 裁决,改判 2026-08-09「不设固定高度框」):步骤体内的
  每段长文本(prompt / thinking / answer / 工具输入输出 / payload)呈现为一个与 copilot thinking
  同款的固定高度滚动井(`components/ui/text-well`,唯一实现,copilot ThinkingBlock 与 trace 共用),
  短文本自然矮于井高;井溢出时提供「View full text」,走**正常编辑器出现方式**打开只读全文
  (`onFileOpen` 虚拟只读文档,`saveEnabled: false`),禁止自造 modal。一段文本**恰好一层视觉容器**
  (井自己),步骤体内不套卡片盒。决议全文:
  `docs/design/2026-08-14-trace-longtext-text-well-decision.md`。
- 原话/来源: 决议 D4;2026-08-14 PM 原话「不要套那么多层容器…改成和copilot的thinking一样,一个
  固定高度的scrollarea,把我之前说的5行20行覆盖掉…编辑器该怎么出现还是怎么出现」。
  (2026-08-09 原话「tracing里面的中间结果不要用一个固定高度的框框住,本来panel就有scroll」
  针对的盒中盒问题由「恰好一层容器」承接,固定高度禁令就长文本范围被上句改判。)
- 测试: 只有 `prompt_captured` 时步骤为 running 且 `end` 为空;补上 `llm_call` 后合成一条 done;
  一个节点的答复不会关掉另一个节点的 prompt;两个工具调用在飞时按 id 各自关闭;
  列表里 running 步骤 `aria-expanded="true"`、done 步骤 `false`。
- Status: live(2026-08-09)。
- 归属: capability `trace-observability`; region `timeline`; platform `engine`(`tool_call_started` 半边)。

### F13. 取景是一个动作,它的单位是步骤(2026-08-21,问题台账 T8)

- 机制: 读者手上有三样收窄这份列表的东西——搜索框、类型/节点标签、路由降级 chip。
  它们是**同一个动作**(本文档开头即写明「搜索与筛选是用户主动的取景」),所以它们共用
  一个形状 `TraceNarrowing`(`utils/trace-narrowing.ts`)、一个谓词 `narrowTraceSteps`,
  和一个「此刻是否在取景」的答案 `isNarrowingActive`。
- 决策(取景作用在**步骤**上,不作用在事件上): 收窄先 `buildTraceSteps` 再筛步骤,
  **一条步骤只要有任何一个事件命中就整条留下**。反过来先筛事件再合成步骤,会在只有闭合半边
  命中时把开场半边丢掉,读者拿到一个没有问题的答案。这与 F9 末句不矛盾:F9 说的是
  `buildTraceSteps` 面对**只有半边**的输入要显示手上那半边——那是直播流从中途接上时的
  真实处境;本条要求的是**取景不再制造**这种半边。稳健仍然稳健,只是不再有人靠它兜底。
- 决策(搜索匹配**值**,不匹配结构): 匹配面 = 事件类型 + 渲染后的标题 + 载荷里**所有字符串与
  数字值**(递归,深度上限 6 只为防病态记录)。此前把整个事件 `JSON.stringify` 进去,于是字段
  **名**也可搜:输入 `phase_name` 命中全 run 每一条,而命中的行上找不到任何理由。判据同 F3——
  **一个看不出理由的命中,比没有命中更坏**。标题由调用方渲染后传入,所以搜的是读者眼前那句话
  (含译文,问题台账 K4b),投影本身仍是纯的、与语言无关。
- 决策(路由降级 chip 有自己的条件,不写搜索框): chip 从前是把 `llm_route_decision` **写进
  搜索框**来收窄的——它因此销毁读者刚敲进去的字,再按一次又把框清空,而读者从没要求清空。
  现在它是 `routeIssuesOnly` 一个独立条件。同时它**只显示自己数过的那些**:计数按
  `decision !== 'answered'` 数降级,展开就必须是这些降级,而不是全部路由判定——两个集合不同,
  就又成了一句做不到的承诺(F3 2026-08-20 修订)。
- 决策(取景时不出结局行): 结局行说的是**这次 run** 怎么结束的。取景之后的列表不是这次 run,
  一句整体判词坐在几条步骤末尾会被读成对这几步的判决——与 F3 对**范围**的处置同一条理由,
  而搜索/标签/chip 按本文档开头的定义同样是取景。结局本身仍从**完整**事件列表读出
  (D8「run 的结局不是搜索命中」不变),变的只是**要不要显示**。
- 明确不做,且理由写在这里: **正则与字段限定搜索**(YAGNI,当前没有一次被需要的现场,来了再设计);
  **跳到下一个命中**(取景之后列表本身就只剩命中,再加一套上下跳是第二种做同一件事的方式);
  **输入防抖**(收窄是 `useMemo` 包着的纯函数,一次 run 的量级下先测量再优化,不先加延迟);
  **零事件时不挂搜索框**(那时确实没有可收窄的东西);**筛选行跟随聚焦开合**(D11 的既有裁决,
  收窄状态由框内计数常驻汇报,不是静默)。
- 原话/来源: 问题台账 T8 列出的 11 条行为;本文档 `:41`「搜索与筛选是用户主动的取景」;
  F3 2026-08-20 修订(列表区的派生跟随取景 / 可操作计数必须兑现)。
- 测试: `utils/trace-narrowing.test.ts` 七条(整步命中、值而非键、类型与标题、只留真降级、
  多条件 AND、活跃判定);`components/TracePanel.narrowing.test.tsx` 四条**客户端真渲染**——
  按 chip 不动搜索框、chip 展开数等于它数过的、取景时结局行消失且清空后回来、闭合半边命中带回
  开场半边。后两条在改前实测为红。**用真渲染而不是静态渲染**,因为这些行为讲的是读者把面板
  **切换到**的状态,而静态渲染只看得见初始状态——这正是这批缺陷活下来的方式。
- Status: live(2026-08-21)。
- 归属: capability `trace-observability`; region `timeline`.

### F14. 取景要看得懂:命中计数 + 命中高亮(2026-08-21,问题台账 T8)

- 机制: 取景之后读者手上有两个问题,F13 都还没回答——「我刚才藏掉了多少」和「这一行凭什么算命中」。
  两个答案在收窄发生的那一刻就已经在手上了:剩下几条步骤,以及读者敲的那个词。
  搜索框右端常驻一枚计数(`TraceSearchBar` 的 `matchCount`),行里逐字打印值的地方把那个词标出来
  (`ui/marked-text.tsx` 的 `MarkedText`,经 `trace/trace-mark-term.tsx` 分发)。
- 决策(计数读的就是列表本身那个数组): `matchCount` 传的是 `narrowing.narrowedSteps.length`——
  正在被 `TraceEventList` 渲染的那一个数组,不在别处再数一遍。判据同 F3 2026-08-20 修订:
  **一个点开找不到的计数比没有计数更坏**,而一件事数两遍正是两个数对不上的来源。
  未取景时不显示(`null`,不是 0);取景后即使是 0 也照报——「什么都没匹配上」恰恰是读者最需要的那个答案。
- 决策(计数的单位是步骤,不是事件、也不是命中次数): 与 F9 / F13 同一个单位。若再报一个「27 处命中」,
  屏幕上就有两个都自称"命中数"的数字,而它们永远不相等。
- 决策(高亮只落在**逐字打印的值**上): 标出来的地方 = 事件类型、行标题、模型、token 数、
  路由判定里的协议 / 路由 id / 理由、调用设置里的设置名 / 请求值 / 理由、机器叙述与事实值,
  以及全部长文本 well(`TextWell` 的 `markTerm`)。**不标**本 app 自己选的词——结局判词、
  `{{count}} filters on`、格式化后的时间、`Answered` 这类判词:搜索从来没有匹配过它们
  (匹配面见 F13:事件类型 + 渲染后标题 + 载荷里的字符串与数字**值**),在那里画一道高亮
  等于宣称一个没有发生过的命中。
- 决策(高亮的匹配规则必须与收窄的**同一条**): 大小写不敏感 + 字面子串,不是正则——
  `narrowTraceSteps` 两边都 `toLowerCase()` 后 `includes`。两边不同就会长出两种病:
  命中了却一处没标(读者看不出理由),或标在没命中的地方(读者看到一个不存在的理由)。
- 决策(值被印在本 app 写的句子里时,只标值、绝不标句子)(补记 2026-08-21,同批真机点验): 上面
  「只标逐字打印的值」这一条落地时漏了一整类位置——**值并不总是单独成行**。`endpoint: {{id}}`、
  `HTTP {{status}}`、`Loaded — {{path}}`、`Wrapped — {{source}}`、`Sent — {{role}}`、
  `answered: {{answer}}`、`This build has no reading for {{eventType}}` 这七句都是「本 app 写的框
  + 一个逐字的值」,当时整句原样输出,于是**值再怎么命中也标不出来**。真机实测(179 步的 run,
  搜 `ark-official`):留下 **27 条**步骤、屏幕上只有 **6 处**高亮,其余 21 条即使展开也一处没有——
  那 6 处全部来自行标题(`Answered by ark-official:...`,真实 route id 天然含 endpoint id),
  而**真正被搜的那一行 `endpoint: ark-official` 从头到尾没标过**。这正是 F13 判据
  「一个看不出理由的命中,比没有命中更坏」所指的那一档。
  修法是把「标哪里」的粒度从**整串**降到**串里的一段**:`ui/marked-text.tsx` 增
  `splitOnTermWithin(text, value, term)` 与 `MarkedValue`,只在 `value` 落在 `text` 里的那一段内
  施加 F13 的同一条匹配规则,段外一律不标;trace 侧经 `TraceMarkValue` 分发。
  **不把 i18n key 拆成「标签 + 值」两条**:那会把词序焊死在英语上(某些语言值在前),而这里需要的
  信息只是「成品句子里哪一段是引用」,句子本身仍旧整条交给 i18n 生成。
  `value` 在句子里找不到时(某个译文没写插值)整句不标——译文的措辞归 i18n 管,凭猜画一道高亮
  比不画更坏,与本条主旨同源。只认**第一处** `value`:这些框各自只插值一次;真出现重复,标出一处
  已足以让读者看出理由,而挑哪一处会变成又一次猜测。
- 决策(词用 context 送到叶子,不逐层当 prop 传): 命中可能出现在行标题、事件类型,或展开后
  十三个 well 里的任意一个;中间那些组件与"搜索"毫无关系,给它们每个加一个自己不读的参数,
  是把一件无关的知识铺满整棵树。`TraceMarkTermProvider` 挂在列表外面一层(`TracePanel`),
  叶子用 `useTraceMarkTerm()` 取——与这些行里早就在用的 `WorkspaceContext` 同一个形状。
  默认值是空串(标记什么都不做),所以 trace 之外的 well(copilot 那口)分毫不动。
- 决策(高亮用 `warning/40`): 高亮得压在它落地的那些底色**之上**仍然看得见,而 `accent` 与
  `destructive` 已经分别是**选中行**和**失败行**的底色——高亮用这两个,就会在读者最可能盯着的
  那两类行里消失。
- 明确不做,且理由写在这里: **跳到下一个命中**(F13 已裁:取景之后列表本身只剩命中);
  **命中次数**(与上面「单位是步骤」同一条理由);**给高亮配上下一个/上一个的导航**(同上)。
- 原话/来源: 问题台账 T8 十一条行为里的「无高亮无命中计数无跳转」一条(其余十条见 F13);
  F3 2026-08-20 修订「长在列表里的、以及承诺『点开就能看到』的可操作计数,一律跟随范围……
  一个点开找不到的计数比没有计数更坏」。
- 测试: `components/ui/marked-text.test.tsx` 十一条(前六条同上;新增五条钉 `splitOnTermWithin` /
  `MarkedValue`:标在值里、值即整句、值缺席或为空则整句不标、组件只在值内出 `<mark>`、
  词打不中值时整句纯文本);`components/trace/TraceStepRow.markValue.test.tsx` 四条钉**缺陷的真实形状**
  ——一条 `llm_call` 步骤挂着 route 判定 verdict(它的行标题讲的是这次调用,不含 endpoint id,
  正是真机上那 21 条不标的行),搜 endpoint id 要出高亮、搜它的一截也要出、搜 `end`(只落在本 app
  写的 `endpoint:` 标签上)必须一处都不出、状态码这种数字值同样要标;
  `components/TracePanel.narrowing.test.tsx` 四条**客户端真渲染**(标出来的每一处都正好是读者敲的
  那个词、清空搜索后一处 `<mark>` 都不剩、计数等于列表自己报的步骤数、零命中报 0 而不是隐藏)。
  改前把两个 endpoint 出口与 http 出口分别改回旧写法,对应断言实测为红。
- Status: live(2026-08-21)。
- 归属: capability `trace-observability`; region `timeline`.

### F4. 边点 = 边的步骤(2026-08-13 决议 D5,改组 2026-07-02 双态方案)

- 机制: 点边 dot = 选中这条边 = trace 范围收窄到这条边(F3 的 edge 范围),此时列表里的
  行**就是**这条边的操作步骤——`input_dispatch` / `blackboard_reduce` /
  `input_file_injected` 按 `from_phase`/`to_phase` 归边,`artifact_saved` 按上游
  `phase_name` 归边——与节点步骤同一套行样式(长文本走 `text-well` 原语),不再有第二套"边专用"呈现。
  面板中随范围 chip 保留的是 `EdgeTamperSection`,承载两件 trace 行给不了的东西:
  - **未跑前(静态推断)**:像节点 io 一样给出该边的黑板字段推断——"graph 跑到这个 dot
    时,黑板上应该有哪些字段"。推导规则与编译期数据流校验同源:该边可用字段 = 根
    `io.inputs` ∪ 下游节点全部上游祖先 phase 的 `io.outputs` ∪ runtime_config 中该
    phase 的 import binding 注入字段 ∪ iterate/batch 注入字段;同名顺序覆盖
    (`allow_sequential_overwrite`)取最近祖先;并标出下游节点将按其 `io.inputs` 切走
    哪些字段。没跑过就没有事件,trace 行天然空白——静态推断正是补这块的。
  - **篡改黑板续跑(操作,不是展示)**:`EdgeTamperEditor` 编辑该边派发的黑板 JSON 并从
    checkpoint 恢复下游,这是一个动作入口,不属于事件流呈现,留在面板。
  - **通往 Output 边界的那条终止边**(2026-08-20 新增):它的下游 `__global_output__` 是
    **画布自己铸的伪节点**——这个 id 在 engine、gateway、studio backend 三处各出现 **0 次**
    (由 `components/nodes/buildEdges.ts` 铸出),所以**没有任何运行事件会指向它**,
    trace 行在这条边上天然为空,静态推断也解释不了「已经跑完了」。这颗 dot 该显示的是
    **这次 run 交出去的那份东西**,它的唯一发布方是 run 自己在结束时报的那一次:
    `run_ended.final_context.phase_outputs[<带 output 标记的阶段>]`。实测 run
    `2026-08-20T13-14-59_14582c6b`:`phase_outputs.global_synthesis` 恰好是
    `{story_framework: …}`,与该 skill `GRAPH.md` 的 `io.outputs.required: [story_framework]`
    逐字对应——**声明的产出与实际产出是同一份数据**,不需要第二个来源。
    三条随之而定的规则:
    - **不新增引擎事件**。那份值 run 结束时已经报过一次;再发一条携带同样值的事件,
      就是同一个事实有两个发布方(与可观测性设计源的 OB11/OB12 同一条纪律)。
    - **判别用伪节点 id 本身,不用「是不是输出边界」**。skill 可以声明一个真名叫
      `output` 的阶段,那是**真节点、有真迁移、有真 `input_dispatch`**;只有画布伪节点
      `__global_output__` 是没有事件的那一个。
    - **终止边不提供 tamper / resume**。边界之后没有下游,续跑请求的 `resumeFromNodeId`
      会是引擎不认识的 id;面板在这条边上给出**只读的产出值**(`Run output` 段,并标明
      是哪个阶段产出的,长文本走同一个 text-well 原语),不给一个按下去必然报错的操作。
- 决策: dot 仍是节点间状态机转换点(2026-07-02 语义不变),但**运行期"真实快照/操作记录"
  的呈现载体从独立的 EdgeContextView 面板改组为 trace 行本身**(D5:"边点显示 phase 间
  步骤,与节点步骤同样式")。理由:边操作本来就是事件流里的事件,再养一个平行面板等于同一
  信息两处呈现、两处要同步;`EdgeContextView.tsx` 已删除,不重建。
- 原话/来源: `docs/design/2026-08-13-trace-goes-glass-box-decision.md` §D5;
  `01_workflows/04_run-and-verify.md:76` defines dot semantics;PM 2026-07-02 原话
  (静态推断 + 运行期都要)继续有效,变的只是运行期呈现的载体。
- 测试: `trace-scope.test.ts`(边范围恰好收进该边的边操作事件、`artifact_saved` 归上游、
  Input 边界边接受 null `from_phase`);`EdgeTamperSection.test.tsx`(静态推断体 / tamper
  编辑器 / 无记录时的诚实空态 / **Output 边界只读产出体且不出现 Tamper 与 Resume**);
  `edge-context.test.ts`(**终止边读 `run_ended` 的 `phase_outputs`;run 未结束时留给静态推断;
  真名叫 `output` 的阶段仍走 `input_dispatch`**);`TracePanel.test.tsx`(边范围时 tamper 区
  出现在范围 chip 下)。
- Status: live(2026-08-14:EdgeContextView 删除,EdgeTamperSection + edge 范围接管;
  静态推断 lib/edge-static-inference.ts 不变;2026-08-20:终止边接 `run_ended` 产出值)。
- 归属: rendering `graph-authoring`/`canvas`; data `trace-observability`.

### F5. Prompt 就在它自己的步骤里,并说清每一段字是谁写的

- 机制: 展开一条 LLM 步骤,**没有第二个入口**(没有 "Inspect prompt" 链接、没有独立弹窗),
  就地按**执行顺序**看到这几格——每格的标题是引擎**做的那个动作**,不是它**存的那类数据**:
  1. **`Loaded — <阶段文档路径>`**:作者写的那份阶段文档。这一格给的是一个**能打开真文件的
     链接**(「Open this phase」,走工作区既有的 `onFileOpen` 通路),不是文档正文的副本。
     数据源 `prompt_captured.phase_source_path`(工作区相对路径);阶段不来自文件时整格不出现。
  2. **`Wrapped — <模板 id>`**:引擎把作者那份文档裹进去的**认知模板全文**。
     数据源 `prompt_captured.template_source`(id,如 `cognitive/v0.3.0`)+ `template_text`(正文)。
  3. **`Filled in`**:代入的变量(`variables`),为空则整格不出现。
  4. **`Sent — System` / `Sent — User` / `Sent — Assistant`**:真正发出去的那几条消息,
     **一条消息一格、正文原样呈现**。数据源 `resolved_prompt`
     (无 `prompt_captured` 半边时退到 `llm_call.messages`)。
- 决策:
  - **两个入口 = 两处要同步、两处会不一致。** 2026-08-09 D5 因此删掉
    `components/PromptInspector.tsx` 及 `promptIndex` / `findPromptEvent` 整条链——
    F9 落地后 prompt 本来就在步骤开始时展示,不需要特殊化的第二个家。
  - **标题写动作,不写数据类别。** 这是 2026-08-13 D1「废除 TEMPLATE / VARIABLES 特殊容器」
    那条裁决的正读法:被废除的是**按种类归堆、与时间无关**的容器,不是"模板正文不许出现"。
    所以本条把每一格都命名成引擎当时做的那一下(装载 / 套模板 / 代入 / 发出),顺序即执行顺序。
  - **作者的文档走路径,引擎的模板走正文——因为二者的"真相在哪"不同。** 阶段文档是工作区里
    的一个**文件**,读者可以打开、可以改;把它的副本抄进 trace,读者改完文件后 trace 里那份
    立刻变成一份没人维护的旧影子(违反「文档事实唯一所有权」)。引擎模板则**盘上没有文件**——
    `V030_COGNITIVE_TEMPLATE_ID` 是常量 id,正文过去只以 f-string 形式存在于
    `cognitive/prompt.py` 里,读者无路可达;所以它只能以正文随事件走。
  - **发出去的消息按消息呈现,不塞进一坨 JSON。** 读者在这一格要做的事是"读模型读到的东西";
    一个带转义换行的 JSON 数组是同样的字节、却是没人读得下去的形状。
- 原话/来源: 决议 `docs/design/2026-08-09-trace-ia-and-streaming-overhaul-decision.md` D5 +
  `docs/design/2026-08-13-trace-goes-glass-box-decision.md` D1;PM 原话 2026-08-09
  「这个prompt inspect是什么东西?不要搞那么复杂,如果显示清楚每一步做了什么,就能直接从
  tracing里面看到具体的prompt,不用搞特殊化」;问题台账 T2「prompt 装载展示不全」。
  本条**取代** `01_workflows/04_run-and-verify.md:93` 的独立 inspector 动作,并**改写**本条
  2026-08-09 版「Template / Variables / Rendered 三段」的措辞(那是 D1 之前的旧形状)。
- 引擎侧前提: `prompt_captured` 新增 `template_text` / `phase_source_path` 两字段
  (`callbacks/events.py`);模板正文从 f-string 提成模块常量 `V030_COGNITIVE_TEMPLATE_TEXT`
  并以 `.format(...)` 渲染(`cognitive/prompt.py`),使"发出去的那份"与"展示的那份"同源。
- 测试: `TraceStepRow.test.tsx`(四格按 `Loaded → Wrapped → Filled in → Sent` 出现且带内容 /
  消息按消息呈现而非 JSON / 任何步骤都不渲染 "Inspect prompt")、
  `TraceStepRow.liveOutput.test.tsx`(流入的思考与回答排在 `Sent` 之后)、
  `utils/trace.test.ts`(`promptMessages` 的角色映射与正文提取)、
  引擎 `tests/cognitive/test_template_text_is_a_value.py`(渲染结果钉死在 golden 文件上——
  该 golden 由**改动前的 f-string 实现**渲染产出、与新实现逐字节相同,所以往后任何一处
  空格漂移都必须显式改 golden 才能过)。
- Status: target-design(2026-08-20 改写)。
- 归属: capability `trace-observability`; region `timeline`.

### F6. Run Status Projection(状态投影 SSOT,2026-08-13 决议 D7)

- 机制: 前端模块 `utils/run-status-projection` 是把 `(事件流, run 记录, 终态 gate)` 折叠成
  一切派生运行状态的**唯一出口**——画布节点灯、trace 步骤行、顶条/run 列表徽章全部消费它,
  不允许第二份推导逻辑。裁决函数 `runVerdict(events, metadata, runId, gateVerdict)` 按
  **三条通道排序**,顺序就是各通道能知道多少:
  1. **落章的 run 记录**(`metadata.status`)。只有它带全套状态词汇,因而只有它分得清
     cancelled 与 paused;它是 Studio 其他地方引用的权威封章。
  2. **后端发布的终态 gate**(`gateVerdict`)。它由**写记录的同一步**发出,所以带着记录的
     权威,只是措辞更粗(pass/fail/paused/stopped)。它必须**单独成为一条通道**,因为
     记录会**送不到**:回读是一次 HTTP 往返,它失败时若没有第四个答案,一切派生状态就
     永久停在 running(台账 N5)。gate 词表到 verdict 词表的翻译只写一处:
     `components/studio/gate-state.ts` 的 `runVerdictFromGateOutcome`(`pass→success`、
     `stopped→cancelled`),**禁止**把 gate 的词直接塞进决定节点徽标的那个槽。
  3. **最后一条流式 `run_ended`**。它只知道 worker 停了,不知道那次停**是什么**;
     resumed run 结束多次,只有最后一次描述读者当下所见。

  三条皆无 = running。第二真相通道(记录)的来源:`run_ended` 后的终态回读、以及
  stop/pause 请求返回的 canonical 记录快照(成功写返回权威快照,属 SSOT 读取原则允许的
  revalidation 触发)。
- **铁律: run 到终态 ⇒ 任何派生状态不得为 running。** 缺结束帧(worker 被杀、流先死)
  不是「永远转圈」的理由——记录终态本身就是最后的裁决输入,而**记录回读失败也不是**:
  gate 已经说了这次 run 怎么结束的,画布与 run 列表行都落在那同一个答案上。回读只补它
  独有的东西(token 汇总、报告路径、归档状态),补不到就照实说「run 结束了,详情读不出来」,
  **不把「读不到详情」说成「还在跑」**。
- 消费组件「状态 → 显示效果」对照表(各自用测试锁死):
  - **画布节点**(`NODE_STATUS_AT_RUN_END`,`run-status-projection.test.ts` 锁):
    verdict success → 节点 success;failed → error;cancelled → paused(用户止损不是节点失败);
    paused → paused。
  - **trace 步骤行**(`trace-steps.test.ts` + `TraceStepRow.test.tsx` 锁):
    running → 旋转 spinner + 自动展开;done → 落定行,无标记;终态 verdict 下未闭合的
    步骤 = **severed** →「never completed」灰 chip、无 spinner(不是 done:读者应看见
    「它没做完」,而不是一个看似完整的摘要)。paused 不 sever——步骤是挂起不是死亡,
    resume 的闭合半帧仍会配对。
  - **顶条/run 列表徽章**(`runStatusMark`,`run-status-mark.test.ts` 锁):
    running → 进行中;success → Run succeeded;failed → Run failed;paused → Run paused;
    cancelled → Run cancelled。live 且 running 时顶条显脉冲点(F8 形态不变)。
  - **结局行**(`trace-outcome.test.ts` 锁):只有真终态(success/failed/cancelled)产生
    结论条目;running/paused 无结论。流侧孤立的 `interrupted` 不武断下结论,等记录落章。
- 决策: this belongs to trace because it interprets runtime events into node view state;
  D7 把它从「trace 内一处推导」升格为跨表面 SSOT,收编原 `node-status.ts` 独立分支与
  `buildTraceSteps` 无闭合输入两处旧推导(B8)。
- 原话/来源: `docs/design/2026-08-13-trace-goes-glass-box-decision.md` §D7;
  `01_workflows/04_run-and-verify.md:106` 与 `01_workflows/05_debugging.md:25` 把派生归属 trace。
- 测试: `run-status-projection.test.ts`(三通道优先级 + 铁律 + 节点闭合表)、
  `run-status-projection.derived.test.ts`(迁移的逐事件派生回归)、
  `gate-state.test.ts`(效果带上 gate 判词 + 词表翻译)、
  `Workspace.test.tsx`(记录回读失败时画布仍收敛、run 行同步、文案不谎报在跑)、
  `useRunHistory.test.ts`(`projectRunStatus` 只动状态)、
  `trace-steps.test.ts`(severed)、`TraceStepRow.test.tsx`(三态视觉)、
  `run-status-mark.test.ts`(徽章表)、`trace-outcome.test.ts`(结论门槛)。
- Status: live(2026-08-14 落地;2026-08-21 补第三条通道)。
- 归属: capability `trace-observability`; capabilities `run-execution`, `debug-resume`; region `canvas` + `timeline`.

### F7. LLM Fallback Visibility

- 机制: gateway 的 `llm_fallback` 事件（provider route 失败、同 role 兜底 route 接手时发射）作为一等 trace UI 渲染：事件行人话化消息（`LLM fallback: A → B`；`to_provider='<none>'` 显 `failed — no remaining route`）、琥珀 warning 徽章/时间线圆点、FallbackBlock（`context.from_route/to_route` 的 provider_model_id 双模型 + 失败原因 + role + HTTP 码）、run 级 fallback 计数 chip（点击经 trace 类型过滤器只看降级事件）、模型 chip（`prompt_captured`/`model_resolved` 的 `resolved_model` = 解析时真值，`llm_call.response_data.model_name` = provider 回报的 post-call 真值，PromptInspector 标题同显）。纯前端消费：事件链 gateway emit（`call/chat_model.py` 三处）→ studio `run_manager._queue_event_subscriber` → WS + trace.jsonl 此前已 live，本条零后端改动。
- 决策: 降级不可见则模型对比不可信——run 可能静默从模型 A 降到模型 B，用户拿着 B 的产物当 A 的结论。因此任何 LLM 对比类功能之前必须先落本条（PM 排队单 2026-07-16 第一优先）。
- 原话/来源: PM 排队单 2026-07-16「用户做模型对比时可能『以为测的是模型 A、实际已降级到 B』而不自知」；事件契约 `graph_agent_gateway/events.py` LLMFallbackEvent（code `[F-v3-gateway-llm-fallback]`）。
- 测试: `utils/trace.test.ts`（message/color/details 解析/count/模型名三来源）、`TraceEventRow.fallback.test.tsx`（FallbackBlock/exhausted/模型 chip）、`TracePanel.test.tsx`（run 级 chip 单复数与 aria-label）、`PromptInspector.test.tsx`（标题模型 chip）。
- Status: live（2026-07-16 落地：utils/trace.ts `llmFallbackDetails`/`countLlmFallbacks`/`eventModelName` + TraceEventRow FallbackBlock + TracePanel fallback chip + PromptInspector 模型 chip；活跑与历史回看共用同一渲染链）。
- 归属: capability `trace-observability`; region `timeline`.

### F12. 每一步都说出自己做了什么(没有沉默的原始 JSON 兜底)

- 机制: 展开一个步骤,看到的是三层,按这个顺序:
  1. **它说的话**(`machineryNarration.details`):引擎的**整句自述**。数据源是**两类通道**——
     单句通道 `message` / `warning` / `reason`,与清单通道 `details`;两类都是引擎在说话。
  2. **它拨动的东西**(`eventFacts`):每种事件类型自己那几个有意义的字段,渲染成
     「标签 + 值」的事实行(如 `transition: draft → review`、`dispatched: topic, draft`、
     `synthesized: 2 / dropped: 1`)。长值(黑板快照、context、payload)不进事实行,归文本井。
  3. **它踩到的问题**(`machineryNarration.problems`):`errors` / `violations` 清单,
     外加 `tool_error_handled` 的单数 `error`。
- **没有读法的事件必须自己说出来**:`eventFacts` 对**认识**的类型返回数组(可以是空数组),
  对**不认识**的返回 `null`;渲染层据此给出一条明确告警行
  (`data-trace-unread-event=<类型>`:「This build has no reading for X — showing the raw
  event」)加原始 payload,而不是像从前那样直接 `JSON.stringify` 整个事件了事。
- **读法覆盖由门禁保证**:`utils/engine-event-types.ts` 镜像引擎 `CallbackEvent` 联合体的全部
  事件类型,后端测试 `test_engine_event_types_are_mirrored.py` 同时读 Python 联合体与这份 TS
  清单并要求一致;前端测试再断言清单里每一项都有读法。
- 决策:
  - **兜底渲染是伪装成渲染的黑箱。** 整坨 JSON 看上去"渲染了",于是引擎新加一个事件、
    某个步骤悄悄退回黑箱,没有任何人会发现——而去黑箱正是 2026-08-13 D4 要终结的状态。
    所以这里立两道:运行期**明说**没有读法,构建期**红灯**提醒补读法。
  - **句子归引擎,版式归前端。** 事件里那句整话是引擎产出的事实(D4 契约),前端不改写、
    不再造一份自己的叙述表——否则同一件事会有两种说法,而"哪个是真的"不可判定。
  - **事实行只放短值。** 事实行是给人扫一眼的;把黑板快照塞进去只会把它变成另一种 JSON 墙。
- 原话/来源: PM 2026-08-14②「tracing 对用户的目的是去黑箱」;2026-08-19 Q9(重复≥2 次:
  「只有结果没有过程」);决议 `docs/design/2026-08-13-trace-goes-glass-box-decision.md` §D4。
- 测试: `utils/trace.test.ts`(单句通道并入自述 / 吞掉的异常进 problems / 事实行内容 /
  转移读作转移 / **每个引擎事件类型都有读法**)、`TraceStepRow.test.tsx`(无读法时明确告警 /
  超长 payload 仍整份进同一个文本井 / 已知事件只出事实行不出原始 payload)、
  `apps/studio/backend/tests/test_engine_event_types_are_mirrored.py`(镜像不漂移)。
- Status: target-design(2026-08-20 立)。
- 归属: capability `trace-observability`; region `timeline`.

### F10. 降级只解释一次(重复的只报"又来了")

- 机制: 一条**降级判定**(`llm_route_decision` 中 `decision != 'answered'`)在整条 trace 里
  按「结果 + route + endpoint + 原因 + HTTP 码」认身份。**第一次出现**照旧渲染完整黄块
  (标题 / endpoint / 协议 / 状态码 / 模型链 / 原因);**之后每一次相同的**渲染成一行紧凑的
  重复行(`data-trace-route-repeat=<第几次>`):写清「又一次 + endpoint + 累计第几次 +
  原因见上」,不再重复原因与路由表。计数由投影层给出(`trace-steps.ts` 的
  `TraceVerdict.occurrence`),渲染层只按它选版式。
- **健康判定不折叠**:`answered` 说的是「这一次调用由谁应答」,那是**每次调用各自的事实**,
  不是重复的抱怨。所以它的 `occurrence` 恒为 1。
- 决策:
  - **重复事件保留在记录里,折叠的是解释。** trace 是按时间的记录,压掉真实事件就是撒谎;
    但一个坏掉的 endpoint 会在**每一次**调用上被重新探测,于是同一个事实被完整解释 N 遍。
    实测 run `2026-08-19T06-58-15_179d1440`:一个超时的 endpoint 在连续三个 LLM 步骤上
    各画了一整块黄框(两次 `probe_failed` + 一次 `skipped_circuit_open`)。读者需要知道
    「这一次调用也降级了」(与这次调用有关),不需要第三遍读同一个 `APITimeoutError`。
  - **参考对象**:syslog 的 `last message repeated N times`——同一条消息连续重复时只记一次
    加计数。本仓与它的差别是**不要求连续**:降级会被中间的正常步骤隔开,所以按身份在整条
    trace 里累计,而不是只看相邻。
  - **不同结果算新事实**:同一个 endpoint 从「探测失败」变成「熔断跳过」是状态变了,
    重新完整解释一次。
- 原话/来源: PM 2026-08-19 截图(每个 llm_call 上重复渲染 Probe failed 黄块)+ 判据
  「降级信息一次一处」。
- 测试: `utils/trace-steps.test.ts`(相同降级按出现次序编号 / 不同结果各自从 1 起 /
  健康判定不参与折叠)。
- Status: target-design(2026-08-20 立)。
- 归属: capability `trace-observability`; region `timeline`.

### F11. resume 是一道可见的接缝

- 机制: `resumed` 事件**不按步骤渲染**,而是渲染成一条横跨列表的接缝行
  (`data-trace-resume-seam=<阶段>`):左右各一条细线,中间一枚 chip 写清三件事——
  这是一次 resume、从哪个阶段接上、人回答了什么(附时间)。
- 决策:
  - **它不是步骤,因为它里面没有执行。** 与列表另一端的结局行同理(结局行也明确「不是步骤」),
    接缝不展开、不参与阶段分组的缩进。此前它按普通步骤渲染,于是一路掉进 `GenericPayload`
    的原始 JSON 兜底,唯一还看得出"这里断过"的线索只剩时间戳的跳变。
  - **它要修的误读是「串台」。** 同一个 run 被 resume 后复用同一个 `run_id`,于是两簇相隔很远的
    时间戳同屏出现,读起来像两次运行的事件混进了一条 trace。流层面已被证明是干净的
    (`useRunStream` 渲染期同步重置 + 每次写入都要报出 subject),缺的是**把断点画出来**。
- 原话/来源: PM 2026-08-09 与 2026-08-19 截图(跨 run 事件串台);台账 T12 复核结论。
- 测试: `TraceEventList.test.tsx`(接缝行出现 / 写明阶段与人的回答 / 不回落原始 payload)。
- Status: target-design(2026-08-20 立)。
- 归属: capability `trace-observability`; region `timeline`.

## 3. 接口契约
- Runtime input: run_id websocket events plus persisted `trace.jsonl`.
- UI output: timeline stream/list, node status map, prompt inspector, dot context。(独立的只读文档面已按 2026-08-09 D1 删除,见 F2。)
- Engine dependency: structured phase/transition events and enough ids for loop/retry/batch grouping.
- Region links: `timeline`, `canvas`, `properties`, `editor`.
- Capability links: `run-execution`, `golden-eval`, `debug-resume`.

## 4. 设计决策基础（PM 原话）
- 长 trace **默认折叠大块**;机制按 2026-08-14 裁决(`docs/design/2026-08-14-trace-longtext-text-well-decision.md`,推翻 2026-08-13 D3 的 5 行/20 行/Monaco 三态)为**固定高度文本井**:与 copilot thinking 同款的固定高度 scrollarea,超出井高的部分靠井内滚动;溢出时「View full text」走正常编辑器通路打开只读全文,不自造 modal。唯一实现是共享原语 `components/ui/text-well`(copilot ThinkingBlock 同源消费;禁止任何 trace 表面自造折叠;「默认折叠大块」的原则不变)。原话:「改成和copilot的thinking一样,一个固定高度的scrollarea,把我之前说的5行20行覆盖掉」「弹编辑器为什么要自创一个modal?编辑器该怎么出现还是怎么出现啊」。
- 2026-08-13 D1:展开的 LLM 步骤按**执行顺序**渲染子条目——装载 prompt(`template_source`)→ 渲染后 prompt → 思考(`response_data.reasoning`)→ 回答 / 工具 → 设置 / 路由判定;废除 TEMPLATE / VARIABLES 特殊容器。**2026-08-20 补(同一条决议的必然推论)**:一次**还在跑**的调用,它正在流进来的思考与回答**就落在这条序列的「思考」「回答」两格里**,不是挂在整个步骤体之外的固定位置——此前流式输出画在步骤体之前,于是 running 时读者先看到答案、prompt 被压到最底下,恰好把「按执行顺序」读反了。同一格永远只有一个来源:调用一旦落定,`llm_call` 的终值接管,流式副本消失(两份会在丢包后互相矛盾)。**折叠**的行仍单独显示流进来的文本——那一行没有序列可言,只有「它现在在说什么」。agent phase 内按 Iteration 分层,**数据源只有 `agent_loop_iteration`**,往后顺延给它之后的事件(纯前端投影)。**2026-08-20 更正**:原文并列写了 `prompt_captured.loop_index`,而那是**另一件事**——它数的是 LLM **调用**,一个 ReAct 轮次可以花掉好几次调用(引擎批处理夹具实测:每个 item 两轮却发了三次调用,因为被驳回的 finish_task 会在不触发新 `before_model` 的情况下重试)。把调用序号当轮次号,会让某条 prompt 落在一条还没打开的分隔条底下。两个数各自回答各自的问题,谁也推不出谁;第一条轮次标记之前的调用**保持平铺**(它确实还不属于任何一轮),不猜。机器自述事件(`finish_task_verdict` / `loop_detected` / `protocol_violation` 等,决议 D4)以通用语义行渲染:行首整句 `message`,展开显示 `details` 管线叙述与 `errors`/`violations` 原因列表。
- 2026-08-09:「full trace删掉,功能重复,本来就应该显示full tracing」——通读职责回到 Trace 自身(F2/F3)。
- 2026-08-09:「顶条只显示run_id,后面跟状态徽章,状态徽章不需要一串字,用打勾、错误等原型徽章就行,加上tooltip显示文字success等」(F8)。
- 2026-08-09:「predict徽章用一个图标就可以了,而且所有ui代表predict的都要统一」(F8)。
- 2026-08-09:「running的时候,timeline的显示要和copilot一样显示动态过程啊,内部处理的过程显示太少了,要把每一步具体做了什么都流式的显示出来,就和copilot一样。不要直接显示折叠结果,而是和copilot一样,等完成后再折叠」(F1/F9)。
- 2026-08-09:「tracing里面的中间结果不要用一个固定高度的框框住,本来panel就有scroll」(F9;
  固定高度禁令就长文本范围已被 2026-08-14 裁决改判,见下条)。
- 2026-08-14:「tracing里面长文结果的折叠展开还是很奇怪。首先不要套那么多层容器,第二改成和
  copilot的thinking一样,一个固定高度的scrollarea,把我之前说的5行20行覆盖掉,第三,弹编辑器
  为什么要自创一个modal?编辑器该怎么出现还是怎么出现啊。」(F9 文本井;推翻 2026-08-13 D3 三态
  与 2026-08-09 固定高度禁令,决议 `docs/design/2026-08-14-trace-longtext-text-well-decision.md`)。
- 2026-08-09:「这个prompt inspect是什么东西?不要搞那么复杂,如果显示清楚每一步做了什么,就能直接从tracing里面看到具体的prompt,不用搞特殊化」(F5)。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| TRACE_OBSERVABILITY-1 | trace 挂载 | 单元 `trace-dot-blackboard`；**为什么**：TracePanel/useRunStream 已建但零挂载(zombie)，要接线成 live trace |
| TRACE_OBSERVABILITY-2 | dot 黑板 | 单元 `trace-dot-blackboard`；**为什么**：边 dot 现假黑板，要换真实黑板 state card + 只读编辑器查看 |
| TRACE_OBSERVABILITY-3 | 节点态 | 单元 `run-execution-node-status`；**为什么**：事件→节点态投影的实现归共享 state(state-engine)，trace 只拥有语义 |
| TRACE_OBSERVABILITY-4 | 取景是一个动作,单位是步骤 | F13；**为什么**：搜索/标签/路由 chip 三样都是「让我少看点」,分开实现就会各自长出一套条件与一套「现在算不算在筛」的答案;而按事件筛会在只命中闭合半边时丢掉开场半边,把一条步骤劈成没有问题的答案 |
| TRACE_OBSERVABILITY-5 | 搜索匹配值,不匹配结构;取景时不出结局行 | F13；**为什么**：序列化整个事件让字段名也可搜,`phase_name` 命中全 run 而行上看不出理由;结局行是对整次 run 的判词,坐在一段被收窄的列表末尾会被读成对这几步的判决 |
| TRACE_OBSERVABILITY-6 | 取景要看得懂:计数读列表本身那个数组,高亮只落在逐字打印的值上 | F14；**为什么**：收窄之后「我藏掉了多少」和「这一行凭什么算命中」两个答案在收窄那一刻就已在手上,不给就是让读者对着一份不知道凭什么的列表;计数另算一遍必然与列表对不上,高亮落在本 app 自己写的词上则是在宣称一个没发生过的命中 |

## 6. 测试关键点
1. trace 挂载: TracePanel 已挂 timeline 主路径(active run 流式,结束回 TimelinePanel 历史);agent 分类折叠摘要已实现(ToolCallSubtree verb 分类 + ~2KB 折叠,TraceEventRow.tsx:220-280);PromptInspector 三视图已挂 live+历史两路径(F1/F5 旧 orphan 标注已过时,2026-07 对账)。
2. dot 黑板: 双态均 live——运行期真实事件派生(edgeContextFromEvents,mock 已删)+ 未跑期静态字段推断(staticEdgeInference,前端按拓扑 + io 声明 + runtime_config 推导,GraphCanvas.tsx:1429-1434 / lib/edge-static-inference.ts:139);跑后打开真实 transition blackboard / before-after。(2026-07 对账:旧"未跑时仅空态"已落地静态推断。)
3. 节点态: baseline 现状为 event -> node state 派生未成统一源；目标为 state-engine 消费 trace events 并投影 canvas/timeline。

## 7. 涉及 region / platform
`canvas` · `timeline` · `properties` · `debug-resume` · `state-engine` · `engine` observability

## 8. gaps / 报警
- ✅ dot 双态已齐备(2026-07 对账清除旧报警): 未跑期静态字段推断 staticEdgeInference(lib/edge-static-inference.ts:139)+ 跑后真实 transition blackboard edgeContextFromEvents,均挂 GraphCanvas.tsx:1429-1434。(trace 挂载与 dot 真实数据 2026-07-02 已 live。)

## 交叉引用（链接, 不复制）
[baseline](./baseline.md)（现状,双向）· `canvas` · `timeline` · `properties` · `debug-resume` · `state-engine` · `engine` observability
