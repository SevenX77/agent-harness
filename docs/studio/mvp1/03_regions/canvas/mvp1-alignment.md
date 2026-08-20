---
module: 03_regions/canvas
doc: mvp1-alignment
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
  - **运行段开着、但节点已经不是 running(worker 被杀、流断在半路)⇒ 不显示时间**。
    封存的 run 记录只给终态、不给结束时刻,所以"跑了多久"的诚实答案是沉默——既不
    让表继续走,也不拿"读者恰好什么时候看的"编一个数。
- 原话/来源: `01_workflows/03_compile.md:15`(节点错误标记)、`01_workflows/04_run-and-verify.md:50`(节点运行灯)、`01_workflows/05_debugging.md:14`(失败节点变红);节点 debug 悬浮 bar + agent 子节点对话续跑 = PM 2026-06-04;状态灯闪烁 + 边框虚线流动 + 状态标签(idle/running/success/failed)+ 运行时间 = PM 2026-08-19 原话。
- 成熟参考: n8n 的节点执行态(marching-ants 边框 + 节点角上的耗时徽标)与 GitHub Actions 步骤计时器(耗时精度随时长下降)。借来的是"边框行进 + 角标耗时 + 精度分档"这三点;**没借**它们把耗时做成 hover tooltip——本仓画布上的节点常年可见,耗时是一眼要看的常驻信息,不是需要悬停去问的细节。
- 测试: 编译错在对应节点出 badge;运行事件驱动状态灯绿/橙/红且标签同步;running 节点卡片出虚线流动边框、终态即消失;有运行段的节点显示耗时,running 时逐秒推进、终态冻结;运行段开着但节点非 running 时不显示耗时;运行中 focus 节点显 debug bar,可暂停/resume;agent phase 子节点的 bar 聊天框可用、其余 disable;非运行态 hover 显 bar。
- Status: 状态灯 / 标签 / 虚线流动边框 / 运行时间 = live(2026-08-20);debug 悬浮 bar = target-design。
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
