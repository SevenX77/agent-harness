---
module: 03_regions/canvas
doc: mvp1-alignment
status: FROZEN（React Flow 画布 live；node status 仍非真实 run 态，edge dot 用 mock 黑板，inline subgraph 用 mock rows ⚠️。；目标结构已按 R4-R8 retrofit）
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
  - ② **运行态** = 节点上一个小圆点灯(复用 Settings provider-row 运行灯视觉:绿=通过 / 橙=中间态;位置不照抄)。
  - ③ **运行错** = 该圆点灯变红。
  - ④ **debug 控制 = 节点上方悬浮一个小 bar**:运行时 focus 到哪个节点、哪个节点的 bar 显示;可点暂停 / 开始(resume)/ 打开聊天框说话;**聊天框仅当该节点是 agent phase 下的子节点时可用,其余节点 disable**;非运行时鼠标 hover 节点才显示该 bar。
- 决策: 三态**不叠同一个优先级槽**——badge / 圆点灯 / 悬浮 bar 各占独立视觉位置,无需"谁盖谁"层级(推翻早期 visual-hierarchy gap);debug 干预集中到悬浮 bar,且"对话续跑"能力锁定在 agent phase 子节点(只有 agent 节点能边跑边对话)(PM 2026-06-04)。
- 原话/来源: `01_workflows/03_compile.md:15`(节点错误标记)、`01_workflows/04_run-and-verify.md:50`(节点运行灯)、`01_workflows/05_debugging.md:14`(失败节点变红);节点 debug 悬浮 bar + agent 子节点对话续跑 = PM 2026-06-04。
- 测试: 编译错在对应节点出 badge;运行事件驱动圆点灯绿/橙/红;运行中 focus 节点显 debug bar,可暂停/resume;agent phase 子节点的 bar 聊天框可用、其余 disable;非运行态 hover 显 bar。
- Status: partial/target-design.
- 归属: capabilities `compile-lint`, `run-execution`, `debug-resume`.

### F4. Subgraph Visual Affordance

- 机制: subgraph node can expand inline or navigate to child graph when path resolves;**下钻进入子图后,导航面包屑显示在画布左上角(不在 Header)**,逐级可返回上层图。
- 决策: child graph references use **绝对 path**(engine skill-syntax §2.1:绝对路径、无 registry)、missing paths recover through Assets;**下钻面包屑刻意放画布左上角而非 Header**——避免"跳出项目"的页面切换感(本地 app 防"项目没保存"恐慌)(PM 2026-06-04)。
- 原话/来源: `01_workflows/02_authoring.md:37` locks path-based subgraph references.
- 测试: resolved subgraph expands; unresolved path shows recovery state; inline content is real, not mock.
- Status: placeholder/stale.
- 归属: region `canvas`; capability `skill-workspace`, `graph-authoring`.

### F5. Edge Dot Hit Target

- 机制: the line/dot between nodes is clickable and opens blackboard transition data for the selected run.
- 决策: dot represents operations between upstream end and downstream start.
- 原话/来源: `01_workflows/04_run-and-verify.md:76` defines dot; `01_workflows/04_run-and-verify.md:109` preserves the PM quote.
- 测试: dot opens real transition context; parallel branch dot shows shared filtered blackboard.
- Status: mock/target-design.
- 归属: region `canvas`; capability `trace-observability`.

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
| CANVAS-2 | dot 黑板 | 单元 `trace-dot-blackboard`；**为什么**：边 dot 渲染真实黑板字段切片，非假数据 |
| CANVAS-3 | 子图 inline | 单元 `subgraph-path-inline-drilldown`；**为什么**：主画布 inline 展开子拓扑 + 下钻并存，虚线容器靠父图最右 |

## 6. 测试关键点
1. 节点态: baseline 现状为 Workspace 未传真实 `statusByNodeId`，buildNodes 有默认假态 ⚠️；目标为 节点灯来自真实 run/predict/state-engine 投影。
2. dot 黑板: baseline 现状为 `ContextEdge:getMockEdgeContext` 生成 mock JSON ⚠️；目标为 edge dot 点击打开真实 blackboard transition。
3. 子图 inline: baseline 现状为 `SubgraphInline` 是 mock rows ⚠️；目标为 解析绝对 `path` 后 inline 展开/下钻/面包屑可用。

## 7. 涉及 region / platform
`graph-authoring` · `run-execution` · `state-engine` · `trace-observability` · `assets` · `engine`

## 8. gaps / 报警
- 🚨 节点态: Workspace 未传真实 `statusByNodeId`，buildNodes 有默认假态 ⚠️；目标 节点灯来自真实 run/predict/state-engine 投影。
- 🚨 dot 黑板: `ContextEdge:getMockEdgeContext` 生成 mock JSON ⚠️；目标 edge dot 点击打开真实 blackboard transition。
- 🚨 子图 inline: `SubgraphInline` 是 mock rows ⚠️；目标 解析绝对 `path` 后 inline 展开/下钻/面包屑可用。

## 交叉引用（链接, 不复制）
[baseline](./baseline.md)（现状,双向）· `graph-authoring` · `run-execution` · `state-engine` · `trace-observability` · `assets` · `engine`
