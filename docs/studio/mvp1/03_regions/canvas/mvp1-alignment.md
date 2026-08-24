---
module: 03_regions/canvas
doc: mvp1-alignment
role: alignment
status: FROZEN（2026-07-02 按代码核对:edge dot 已接真实事件派生(edgeContextFromEvents,mock 已删),缺静态推断态;node status / inline subgraph 现状以代码为准 ⚠️。；目标结构已按 R4-R8 retrofit）
binds_baseline: ./baseline.md
units: [subgraph-path-inline-drilldown, run-execution-node-status, trace-dot-blackboard]
aligns_with: 01_workflows/02_authoring.md（canvas authoring）· 01_workflows/04_run-and-verify.md（node status / dot）
---

# canvas — MVP1 Alignment

> **Tier**: region | **Owns**: `subgraph-path-inline-drilldown` 的 inline 展开/下钻/面包屑 + `run-execution-node-status` 的节点灯/边 UI + `trace-dot-blackboard` 的 dot 渲染 | **现状**: React Flow 画布 live；node status 仍非真实 run 态，edge dot 用 mock 黑板，inline subgraph 用 mock rows ⚠️。 | **Related**: [baseline](./baseline.md)（双向）· `graph-authoring` · `run-execution` · `state-engine` · `trace-observability` · `assets` · `engine`

## 1. 定义
`canvas` owns the visible graph workspace: nodes, edges, topology direct manipulation, subgraph affordances, runtime status badges, compile/debug markers, and edge-dot hit targets.

Source workflow basis: `01_workflows/02_authoring.md:18`, `01_workflows/04_run-and-verify.md:75`, `01_workflows/05_debugging.md:14`.

## 2. 数据流 / 机制（设计细节）
### F1. Graph Render And Selection

- 机制: render graph nodes/edges and use node click/double-click to drive selection and file/panel focus;**agent phase 节点可在画布上内联展开为正文 XML 的 L3 子节点(可拖拽增删改排),这些子节点也是运行期 debug bar 对话续跑的对象**。
- 决策: canvas 是宏观/中观创作面 **+ 正文 XML 结构编辑面**(L3 子节点内联);**Properties 只管 frontmatter 属性,编辑器看文件/diff/trace**——三者职责切分(PM 2026-06-04)。
- 原话/来源: `01_workflows/02_authoring.md:18` lists graph authoring and Properties actions.
- 测试: click selects node; double-click phase opens file and Properties; double-click input opens i/o panel.
- Status: live.
- 归属: region `canvas`; capabilities `graph-authoring`, `phase-editing`.

### F2. Topology Edit

- 机制: edge create/delete and add-phase context menu mutate topology through persistence callbacks.
- 决策: direct graph manipulation should persist to source and then compile validates.
- 原话/来源: `01_workflows/02_authoring.md:31` ties edits to lint/compile.
- 测试: connect/disconnect persists; cycle is blocked; rollback preserves old graph on failure.
- Status: live with native-fs migration pending.
- 归属: region `canvas`; capability `graph-authoring`.

### F3. Compile And Runtime Node Markers

- 机制: 节点上**三条独立视觉通道 + 一个 debug 悬浮 bar**,互不抢位:
  - ① **编译错** = 节点上一个 warning/error 小标志(badge)。
  - ② **运行态 = 节点右上角一枚「状态胶囊」,由三件东西合成,永远同时出现**
    (PM 2026-08-19 运行时观测裁决):
    - **状态灯**:一枚小圆点,复用 Settings LLM Roles 的路由运行灯视觉
      (`settings/llm-roles/role-route-status.tsx` 的 `roleRouteStatusLightClass`
      ——同尺寸、同 ring、running 时同 `animate-pulse`);位置不照抄。
    - **状态标签**:紧挨状态灯的一个词,词表固定为
      `Idle` / `Running` / `Success` / `Failed`(另有 `Paused` / `Breakpoint`
      两个非常态)。**不用图标代替标签**:一块缩放过的画布上,颜色 + 词读得出,
      六个字形读不出。
    - **运行时间**:该节点本次运行段的耗时,挂在状态胶囊正下方。
      **精度随时长下降**(`4s` → `3m 05s` → `2h 03m`),不显示亚秒——运行段由两条
      引擎事件时间戳夹出,亚秒精度是它给不出的准头。
    - **活动计数**:该节点在本次 run 里做了多少事,挂在运行时间下方。
      **同一个数字,两种时态**——running 时写序数 `Call 3`(第 3 次调用正在飞),
      终态时写基数 `3 calls`(一共调了 3 次);时态本身告诉读者这行在回答哪个问题
      (「它现在在干嘛」还是「它干了多少」)。工具次数只进 tooltip
      (`3 LLM calls · 5 tool calls`):卡片那一行要在缩到很小的画布上还读得出,
      所以只留那个**读者盯着看时会变的数**。**一次都没调过的节点不显示这行**,
      而不是显示 `0 calls`——渲染出来的 0 读起来像一条结论。
      数据源 `prompt_captured`(调用**开始**)、`tool_call_started` 与 `tool_call`,投影
      `deriveNodeActivity`,与状态灯、运行时间同一条事件流、同一个 run 过滤器。
      **有工具在跑时这一行直接写工具名**(`read_file`),工具返回后回到 `Call N`。
  - ③ **运行错** = 状态灯变红 + 标签变 `Failed`(不是 `Error`:这一列是运行结论的
    词表,不是异常类名)。
  - ④ **运行中的节点整块卡片走「虚线流动」边框**(marching dashes):虚线图案与行进
    方向**与 edge 的运行流动线(`.animated-flow-line`)取同一套**,让"这条边在跑"
    和"这个节点在跑"读起来是同一件事而不是两套设计;承载方式借
    `provider-card-border-flow` 的遮罩渐变边环(CSS border 的 dash offset 不可动画,
    且画在 ::after 上,状态翻转时卡片自身布局零位移)。`prefers-reduced-motion`
    下退化为静止边环,信息不减。
  - ⑤ **debug 控制 = 节点上方悬浮一个小 bar**:运行时 focus 到哪个节点、哪个节点的 bar 显示;可点暂停 / 开始(resume)/ 打开聊天框说话;**聊天框仅当该节点是 agent phase 下的子节点时可用,其余节点 disable**;非运行时鼠标 hover 节点才显示该 bar。
- 决策:
  - 三态**不叠同一个优先级槽**——badge / 状态胶囊 / 悬浮 bar 各占独立视觉位置,无需"谁盖谁"层级(推翻早期 visual-hierarchy gap);debug 干预集中到悬浮 bar,且"对话续跑"能力锁定在 agent phase 子节点(只有 agent 节点能边跑边对话)(PM 2026-06-04)。
  - **运行时间只存两个端点(start / end),不存已算好的时长**:一个还在跑的节点必须
    继续走秒,而把秒数塞进节点数据会逼整块画布每秒重建一次。开着的运行段
    (`endedAtMs === null`)由该卡片自己本地走表。
  - **计数按「调用开始」数,不按「调用结束」数**:一次 LLM 调用从发出到回来是读者
    盯着卡片看的那一整段;数结束事件(`llm_call`)会让卡片在这整段里少报一次,
    恰好在最需要它说话的时候落后一拍。所以数的是 `prompt_captured`。
  - **计数跨执行累加,时长只取最后一段**:两者刻意不同。时长描述的是**一段**运行,
    所以取最后那段;计数描述的是**做了多少活**,而一个 iterate 阶段确实把每个 item 都
    跑了——只报最后一个 item 的份额,会把这个节点的工作量少报 item 数倍。
  - **一有工具在跑,这一行就写工具名**:「它现在在干嘛」有字面答案时,没有哪个序号比
    它更好。工具返回后这行回到 `Call N`(它在等模型),终态回到 `3 calls`。
    **这是个真答案不是猜的**:引擎在工具**开始**时就发 `tool_call_started`,前端按
    `tool_call_id` 配对,「还开着」= 有开始没结束,而不是「最近听说的那一个」。
    (2026-08-20 更正:本条上一版写的是「不报当前工具,因为引擎只在工具答复后才发事件」
    ——那是错的。`ToolCallStartedEvent` 一直存在,只是被 `CognitiveFlowMiddleware`
    抢答的那些工具收不到,现在把 tracing 移到决策者外层后全都收得到,见引擎
    `middleware/__init__.py` 的顺序契约。)
  - **停下来的节点不许说有工具在跑**:一个终态节点还挂着「开着」的工具,说明流在半路
    断了;诚实读法是回到计数,而不是显示一个并没有在跑的工具名。
  - **运行段开着、但节点已经不是 running(worker 被杀、流断在半路)⇒ 不显示时间**。
    封存的 run 记录只给终态、不给结束时刻,所以"跑了多久"的诚实答案是沉默——既不
    让表继续走,也不拿"读者恰好什么时候看的"编一个数。
- 原话/来源: `01_workflows/03_compile.md:15`(节点错误标记)、`01_workflows/04_run-and-verify.md:50`(节点运行灯)、`01_workflows/05_debugging.md:14`(失败节点变红);节点 debug 悬浮 bar + agent 子节点对话续跑 = PM 2026-06-04;状态灯闪烁 + 边框虚线流动 + 状态标签(idle/running/success/failed)+ 运行时间 = PM 2026-08-19 原话。
- 成熟参考: n8n 的节点执行态(marching-ants 边框 + 节点角上的耗时徽标)与 GitHub Actions 步骤计时器(耗时精度随时长下降)。借来的是"边框行进 + 角标耗时 + 精度分档"这三点;**没借**它们把耗时做成 hover tooltip——本仓画布上的节点常年可见,耗时是一眼要看的常驻信息,不是需要悬停去问的细节。
- 测试: 编译错在对应节点出 badge;运行事件驱动状态灯绿/橙/红且标签同步;running 节点卡片出虚线流动边框、终态即消失;有运行段的节点显示耗时,running 时逐秒推进、终态冻结;运行段开着但节点非 running 时不显示耗时;运行中 focus 节点显 debug bar,可暂停/resume;agent phase 子节点的 bar 聊天框可用、其余 disable;非运行态 hover 显 bar。
- Status: 状态灯 / 标签 / 虚线流动边框 / 运行时间 / 活动计数 = live(2026-08-20);debug 悬浮 bar = target-design。
- 归属: capabilities `compile-lint`, `run-execution`, `debug-resume`.

### F4. Subgraph Visual Affordance

- 机制: subgraph node can expand inline or navigate to child graph when path resolves;**下钻进入子图后,导航面包屑显示在画布左上角(不在 Header)**,逐级可返回上层图。
- 决策: child graph references use **绝对 path**(engine skill-syntax §2.1:绝对路径、无 registry)、missing paths recover through Assets;**下钻面包屑刻意放画布左上角而非 Header**——避免"跳出项目"的页面切换感(本地 app 防"项目没保存"恐慌)(PM 2026-06-04)。
- 原话/来源: `01_workflows/02_authoring.md:37` locks path-based subgraph references.
- 测试: resolved subgraph expands; unresolved path shows recovery state; inline content is real, not mock.
- Status: placeholder/stale.
- 归属: region `canvas`; capability `skill-workspace`, `graph-authoring`.

### F5. Edge Dot Hit Target(双态)

- 机制: the line/dot between nodes is clickable;**双态**:未跑前打开该边的**静态黑板字段推断**(根 `io.inputs` ∪ 上游祖先 `io.outputs` ∪ runtime_config import binding 注入 ∪ iterate/batch 注入,前端按拓扑 + io 声明 + runtime_config 推导,逐边不同、随编辑即时更新);跑后(选中某次 run)打开真实 blackboard transition data(边事件快照 + 操作记录)。完整语义与数据契约归 `trace-observability` F4,canvas 只渲染。
- 决策: dot represents operations between upstream end and downstream start;**未跑前也要像 node 的 io 一样给出 schema 推断**(PM 2026-07-02)。
- 原话/来源: `01_workflows/04_run-and-verify.md:76` defines dot; `01_workflows/04_run-and-verify.md:109` preserves the PM quote;静态推断原话留底于 `trace-observability` F4(PM 2026-07-02)。
- 测试: 未跑时 dot opens per-edge static field inference(随 io 声明/拓扑变化更新);跑后 dot opens real transition context; parallel branch dot shows shared filtered blackboard.
- Status: mock/target-design(静态推断 = 2026-07-02 新增目标)。
- 归属: region `canvas`; capability `trace-observability`.

### F6. Edge Run Segment State(边自己的运行态)

- 机制: 一条 edge 是**一段运行分段**,和 node 平级(engine 的 `edge_start` / `edge_end`,
  决议 2026-08-15 edge-as-run-segment),因此它有**自己的状态**,不靠下游节点倒推:
  - **词表**:`idle` / `running` / `done` / `failed` / `paused`。
    用 `done` 而不是 `success`——一段 transition 没有"通过/不通过",它只是走完了。
  - **视觉**:
    - `idle` = 底色细线,无强调层;
    - `running` = 强调色叠加层 + **虚线流动**(`.animated-flow-line`),图案与节奏与
      running 节点卡片的行进虚线**取同一套**(F3 ④);
    - `done` = 强调色叠加层,静止;
    - `failed` = destructive 色叠加层,静止;
    - `paused` = warning 色叠加层,静止。
  - **选中**:**整条线可点**,不只中点那颗 dot;选中后线加粗并出现选中环。点线与点 dot
    进入的是同一个 edge 范围——一个选择动作,一条代码路径。
  - **线的状态**与 **dot 的"派发了什么"是两件事,分开表达**:一段空 transition
    (`operation_count = 0`)照样是 `done`,但 dot 里没有派发值。引擎对此有明文:
    "nothing happened between these two nodes is an observation, not a gap in the record"。
- 决策:
  - **状态从 edge 自己的分段事件推导,不从"下游节点是不是在跑"倒推**。旧实现是
    `flowing = (target === runningPhase)`,那是猜:fan-in 的几条边会被一起点亮,而真正
    在跑的可能只有其中一条;更要命的是它**没法表达"这条边跑完了"和"这条边就是死在
    这儿"**——只有"动"和"不动"两档。
  - run 到终态时,**还开着的 edge 分段按与节点同一张对照表关闭**
    (success→done / failed→failed / cancelled→paused / paused→paused)。D7 铁律不变:
    终态的 run 不留任何还在动的东西,edge 和 node 同一条规矩。
  - 事件按 `from_phases` × `to_phase` 归到画布边 id:空 `from_phases` 归到 Input 边界边
    (与 `edge-identity` 同一条判定,不另立一套)。fan-in 的一次 transition 同时点亮它
    join 的每一条边,因为那几条边确实都参与了这一段。
- 原话/来源: PM 2026-08-19 Q1「运行时分段结构是否明确?input-->edge-->node-->edge-->node
  -->...-->output。哪一部分运行哪一部分呈现 running 时的前端状态」· Q3-2/5「边框虚线流动
  (类似 edge 虚线流动)」「subgraph 连接线流动」· Q4-1「edge 选中,点得高亮」。
- 测试: edge_start 点亮该 transition join 的每一条边为 running 并走流动虚线;edge_end 转
  done 且动画停;run 终态时仍开着的分段按对照表关闭;空 transition 是 done 而 dot 无派发值;
  点线任意位置可选中并高亮,与点 dot 落到同一个 edge 范围。
- Status: live(2026-08-20)。
- 归属: region `canvas`; capabilities `run-execution`, `trace-observability`。

### F7. Subgraph Run Scope(容器与容器内节点的运行态)

- 机制: 一个 SUBGRAPH 节点是一段**嵌套的运行**——容器自己是父图的一个 phase,同时它内部
  整张子图也在跑。两级都要在画布上看得见:
  - ① **一个 phase 在一次 run 里的身份是它的 phase path**:自根图起、途经的每一层
    SUBGRAPH 容器 phase 名 + 它自己的 phase 名,以 `.` 连接(`event_timeline.extract`);
    根层 phase 的 path 就是它的名字本身。引擎已在每条事件上盖了这条链
    (`_EventBase.subgraph_path` = 容器链,`phase_name` = 自己),Studio 只是把两段接起来。
  - ② **状态表按 phase path 记账**,于是展开的容器里那些子节点拿到的是**它们自己的**
    状态灯、失败原因和运行时长——与根层节点走的是同一套 F3 呈现,不是另一套弱化版。
  - ③ **容器在 running 时自动展开,成功收起,失败保持展开**;用户在这次 run 里手动开合过
    某个容器之后,自动开合不再碰它。
  - ④ **容器显示子图进度**:已达终态的子 phase 数 / 子图 phase 总数(`3/7`)。**总数只有
    在子拓扑已加载时才算得出**;未加载时只报已完成数(`3 done`),不给分母。
  - ⑤ **容器在 running 时,容器框走与节点卡片、运行边同一套虚线流动**(`.studio-running-dash-frame`)。
- 决策:
  - **phase path 取代裸 phase 名作为状态表的键**。裸名不是身份:两个子图可以各有一个
    `review`,引擎侧已经因此把两个不同 `review` 的 13 次 llm_call 折进同一行报告并丢掉
    一个 `setup` 节点(`_EventBase.subgraph_path` 字段注释记录的 run
    `2026-08-19T01-56-15_d0733362`)。根层 phase 的 path 与它的名字**逐字相同**,所以这次
    换键对根层的每个读者都是恒等变换,只是表上多出了嵌套条目。
  - **能 resume 的锚点只在根层**:resume 把图倒回某个根图节点重跑,子图内部的 phase 不是
    根图的节点,拿它当 `resume_from_node_id` 请求后端等于送一个不存在的 id。所以自动
    resume 锚点(F-n5 的 dirty-downstream 灰化)**跳过带 `.` 的 path**;子图内失败时,
    它的容器同样是失败态(容器的 `phase_end` 永远不会到,run 终态把它关成 error),
    锚点落在容器上——这正是用户要重跑的那个根图节点。
  - **同理,「现在在跑哪个 phase」答的是最外层那个**:子 phase 在跑蕴含它的容器在跑,
    两者同时为真;答最外层的那个,读者拿到的才是根图上的位置。
  - **容器开合的自动化让位于人**。自动开合是省事,不是主张;用户手动开合过就说明他要看
    的东西和自动规则不一致,此后这个容器由他说了算(本次 run 内)。
  - **失败的容器不自动收起**:收起会把唯一能解释"为什么失败"的那几个子节点藏起来,而
    失败恰恰是最需要展开的时刻。
  - **总数不知道就不写分母**,与 F3 运行时长"开着的段不显示时间"同一条纪律:UI 只报能
    证明的数,不为了版式凑一个。
- 原话/来源: 状态要递归进子图 = PM 2026-08-19(两天连续指出"展开容器内子节点恒 Idle");
  "running的时候subgraph要打开" = PM 2026-08-19 原话;"subgraph框闪烁/边框虚线流动,看哪个
  效果好,找成熟参考" = PM 2026-08-19 运行态呈现清单第 6 条。
- 成熟参考: GitHub Actions 的日志分组(运行中的 step 自动展开、成功后自动折叠、**失败的
  留在展开态**)与 n8n 子工作流节点上的执行计数。借来的是"自动开合 + 失败留开 + 容器上带
  计数"这三点;**没借** GitHub Actions 把折叠状态一路记进 URL——本仓的画布开合是一次会话
  内的看图姿势,不是要分享给别人的定位。
- 测试: 子图内节点按 phase path 拿到自己的状态/失败原因/时长;同名的两个子 phase 不互相
  串台;容器 running 自动展开、success 自动收起、failed 保持展开;手动开合后自动规则不再
  介入;容器显示 `已完成/总数`,总数未知时只显示已完成数;running 容器框出虚线流动;
  自动 resume 锚点永远是根层节点 id。
- Status: target-design(2026-08-20 立)。
- 归属: region `canvas`; capability `run-execution`, `trace-observability`.

### F8. IO Boundary Run State(端点也在同一套状态系统里)

- 机制: Input / Output 两个端点节点与普通 node、普通 edge **共用同一套运行态**:
  - ① **它们的状态键就是它们的画布 id**(`__global_input__` / `__global_output__`),
    与 phase 的 phase path 同住一张状态表——画布上的每个节点都能在同一张表里查到自己。
  - ② **端点自己不执行任何东西**,所以它的状态来自它那一端**已经存在的真实证据**,
    而两端的证据不是同一种(见下「决策」第一条):
    - **Input 看从它出发的边分段**(`inputBoundaryStatus`):边开着 = `Running`,
      合上 = `Success`,死在那儿 = `Failed`,run 被按停 = `Paused`,没跑到 = `Idle`。
    - **Output 看产出它的那些 phase**(`outputBoundaryStatus`,即拓扑里 `output: true`
      的阶段):这些阶段跑完 = 这张图交付了它的产物。run 走到终局时仍是 idle/running 的,
      由与每个 node 完全相同的收口表(`NODE_STATUS_AT_RUN_END`)合上。
  - ③ **一个端点有多个来源时取最差的那个**(failed > running > paused > done/success > idle)。
  - ④ **进入 Output 端点的那条边跟着它的产出阶段走**(`outputEdgeStatus`),不查边分段表——
    理由同下:那条线不是一次真实跳转,查不到分段。否则会出现「端点绿了、喂它的线还是灰的」。
  - ⑤ 呈现与 phase 卡片完全一致:同一枚状态胶囊(灯 + 词)、running 时同一套行进虚线边框。
    **不显示运行时长**——端点没有"执行了多久"这回事,一段瞬时派发的耗时是个假数。
  - ⑥ **端点按作用域记账**:展开的子图预览有它自己的一对端点,读的是**该容器作用域**下的
    证据(`expand.__global_input__->…` / `expand.<产出阶段>`),不是 run 的两端。
- 决策:
  - **不给端点造第二套事件语汇**。它们不是 phase,拿不到 `phase_start`/`phase_end`,
    这正是它们此前在每一次 run 里全程空白的原因。
  - **两端不对称,因为证据不对称。** 本单元初版(2026-08-20 立)写的是「Input 看出边、
    Output 看入边」,对称漂亮但**与事实不符**:引擎只为**每一次真实的图内跳转**发
    `edge_start`/`edge_end`,而"到达 Output 端点"不是一次跳转。实测 run
    `predict-2026-08-20T04-09-33` 全量事件流:每一条 `edge_end` 都指向一个真实下游阶段,
    最后一条是 `['story_analysis'] -> 'global_synthesis'`,**没有任何事件指向端点**。
    于是「看入边」在一次完全成功的 run 上让 Output 恒为 `Idle`。改判为看产出阶段——
    阶段跑完就是图交付了产物,这是图自己对"产物好了没"的回答。
    (**同时否掉的替代方案**:只看 run verdict。那会让 Output 从 run 第一秒起就是
    `Running`,等于宣称产物从头到尾都在产出。)
  - **多来源取最差**:Output 由两条分支喂,其中一条死了,它就没拿到该拿的东西;因为另一条
    到了就报 Success,等于让端点替一条不属于它的分支说话。
  - **端点不能当 resume 锚点**:它们和 phase 同住一张状态表,于是自动 resume 锚点必须
    显式跳过它们——图的两端不是图里的节点,resume 没有可倒回的地方。
- 原话/来源: "INPUT/OUTPUT 节点及其连线的显示与状态管理必须与普通 node/edge 统一
  (我也说过,也不做)" = PM 2026-08-14 ⑦、2026-08-19 Q7 两次点名。
- 测试: 端点在 run 前 Idle;Input 的边分段开着时 Running、合上后 Success;Output 跟随产出
  阶段、run 终局时按收口表合上;多来源取最差;子图预览的端点只读本作用域证据;
  自动 resume 锚点永不落在端点上。
- Status: target-design(2026-08-20 立;同日按真机实证修正 Output 的证据来源)。
- 归属: region `canvas`; capability `run-execution`.

### F9. Run State Is Scoped(运行态按子图作用域记账,边与端点一并)

- 机制: F7 把**阶段**的身份改成了 phase path,本单元把同一条规则贯彻到**边和端点**:
  - ① **边分段的 key 是带作用域的两端**:`${subgraph_path}.${from}->${subgraph_path}.${to}`。
    根图作用域为空,key 与从前逐字节相同。
  - ② **`from_phases: []` 是"本图里没有上游",不是"run 的输入"**。它在子图内指的是**该子图
    自己的入口**,记作 `segmentation.__global_input__->segmentation.setup`。
  - ③ **展开的子图预览按同一 key 查它自己的边**;缓存的子布局仍只按拓扑算,运行态在
    `inlineChildEdge` / `inlineChildNode` 里按容器路径贴上(与 F7 同一理由:同一个子技能
    挂在两个容器下是同一份布局、两次不同的执行)。
- 决策:
  - **不把子图内的边归给根端点**。改之前,`from_phases: []` 一律映射成
    `__global_input__->setup`,于是每个子图的第一跳都凭空造出一个根边、并把根 Input
    端点点亮——"三层深处的一次跳转"被报成"run 收到了输入"。实测 2026-08-20 的 run
    里,`event_timeline.extract`(82 个事件)与 `story_analysis.analyze_batches`
    (103 个事件)都带着 `subgraph_path`,这些事件全部落在根端点上。
  - **一条规则一处实现**:阶段、边、端点共用 `phase-path` 的拼接函数,不各写一套前缀逻辑。
- 测试: 同名边在两个子图里互不串台;子图首跳不落在根 Input 上;展开预览的内部边与两个
  端点都读本作用域的证据;根图 key 不变(改动对根级读者是恒等变换)。
- Status: target-design(2026-08-20 立)。
- 归属: region `canvas`; capability `run-execution`.

## 3. 接口契约
- Inputs: skill detail, selected node id, status map, compile diagnostics, trace dot data references.
- Outputs: node selection, file open requests, topology mutation requests, active panel changes.
- Capability links: `graph-authoring`, `phase-editing`, `compile-lint`, `trace-observability`, `debug-resume`.

## 4. 设计决策基础（PM 原话）
- 节点三态不叠优先级(见 F3):编译错=badge、运行态=圆点灯(运行错变红)、debug=节点上方悬浮 bar(暂停/resume/对话;对话仅 agent phase 子节点可用;非运行态 hover 显示)。三者各占独立视觉通道,无层级冲突。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| CANVAS-1 | 节点态 | 单元 `run-execution-node-status`（消费；owner=run-execution/state-engine）；**为什么**：节点灯/边由 run events 经 state-engine 投影，canvas 只渲染 |
| CANVAS-2 | dot 黑板 | 单元 `trace-dot-blackboard`；**为什么**：边 dot 双态——未跑渲染静态字段推断(拓扑+io 声明前端推导),跑后渲染真实黑板字段切片,非假数据 |
| CANVAS-3 | 子图 inline | 单元 `subgraph-path-inline-drilldown`；**为什么**：主画布 inline 展开子拓扑 + 下钻并存，虚线容器靠父图最右 |

## 6. 测试关键点
1. 节点态: 真实投影已 live(2026-08-20)——Workspace 由 `deriveNodeStatuses` / `deriveNodeRuntimes` 喂 `NodeRunProjection`,状态灯 + 标签 + 虚线流动边框 + 运行时间四件同源同 run;剩余 target = F3 ⑤ debug 悬浮 bar。
2. dot 黑板: baseline 现状为 真实事件派生已 live(GraphCanvas 用 edgeContextFromEvents,mock 已删),但未跑时无内容(空态)⚠️；目标为 edge dot 双态——未跑显示静态字段推断,跑后打开真实 blackboard transition。
3. 子图 inline: baseline 现状为 `SubgraphInline` 是 mock rows ⚠️；目标为 解析绝对 `path` 后 inline 展开/下钻/面包屑可用。

## 7. 涉及 region / platform
`graph-authoring` · `run-execution` · `state-engine` · `trace-observability` · `assets` · `engine`

## 8. gaps / 报警
- ✅ 节点态: 已闭合(2026-08-20)。真实 run 投影从 `run-status-projection` 一路到卡片,状态灯 / 标签 / 虚线流动边框 / 运行时间同源。仍开着的只有 F3 ⑤ debug 悬浮 bar。
- 🚨 dot 黑板: 真实事件派生已 live(mock 已删),未跑时仅空态、无静态推断 ⚠️；目标 edge dot 双态(未跑静态字段推断 + 跑后真实 blackboard transition)。
- 🚨 子图 inline: `SubgraphInline` 是 mock rows ⚠️；目标 解析绝对 `path` 后 inline 展开/下钻/面包屑可用。

## 交叉引用（链接, 不复制）
[baseline](./baseline.md)（现状,双向）· `graph-authoring` · `run-execution` · `state-engine` · `trace-observability` · `assets` · `engine`
