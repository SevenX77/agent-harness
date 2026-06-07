---
module: 02_capabilities/debug-resume
doc: mvp1-alignment
status: FROZEN（Studio resume route 存在但直接 501，节点级 Resume 主路径不可用 ⚠️。；目标结构已按 R4-R8 retrofit）
binds_baseline: ./baseline.md
units: [debug-resume-checkpoint]
aligns_with: 01_workflows/05_debugging.md（debug / resume）
---

# debug-resume — MVP1 Alignment

> **Tier**: capability | **Owns**: `debug-resume-checkpoint`（Studio 节点级 resume UI；checkpoint contract 引 engine） | **现状**: Studio resume route 存在但直接 501，节点级 Resume 主路径不可用 ⚠️。 | **Related**: [baseline](./baseline.md)（双向）· `trace-observability` · `timeline` · `properties` · `engine` checkpoint/resume SSOT

## 1. 定义
`debug-resume` owns intervention after a failed or paused real run: node-level resume, HitL answer injection, context tampering from an edge dot, and checkpoint invalidation.

Source workflow basis: `01_workflows/05_debugging.md:8`, `01_workflows/05_debugging.md:11`, `01_workflows/05_debugging.md:23`.

## 2. 数据流 / 机制（设计细节）
### F1. Failed Node Resume Button

- 机制: failed/paused node turns red, shows error message, and exposes Resume on the node itself.
- 决策: resume is anchored at the broken node, not a global action.
- 原话/来源: `01_workflows/05_debugging.md:14` and `01_workflows/05_debugging.md:15` define the node Resume behavior; `01_workflows/05_debugging.md:36` tests the non-global placement.
- 测试: failed node shows Resume; clicking resumes from that node while upstream checkpoints are reused.
- Status: target-design, backend route 501.
- 归属: capability `debug-resume`; capability `trace-observability`; region `canvas`; platform `engine`.

### F2. Dirty Checkpoint Invalidation

- 机制: editing upstream node/topology/output schema invalidates affected downstream Resume buttons while unrelated branches remain resumable.
- 决策: checkpoint validity must protect users from replaying stale context.
- 原话/来源: `01_workflows/05_debugging.md:16` defines dirty invalidation; `01_workflows/05_debugging.md:33` states the test.
- 测试: change upstream phase; downstream Resume disables; unrelated branch Resume stays enabled.
- Status: target-design, engine dependency.
- 归属: capability `debug-resume`; capability `graph-authoring`; platform `engine`.

### F3. HitL Question And Answer Injection

- 机制: an agent request for human input pauses the run, shows a floating rich-text input **above the node's debug bar**(anchored to the node, no fixed canvas top frame), and injects the answer before resume.
- 决策: HitL is a first-class debug pause flow, not just a log event.
- 原话/来源: `01_workflows/05_debugging.md:17` and `01_workflows/05_debugging.md:18` define HitL question/answer.
- 测试: clarification event opens the frame; answer resumes the graph and appears in subsequent trace context.
- Status: target-design/backend primitives.
- 归属: capability `debug-resume`; region `shell-layout`, `timeline`; platform `engine`.

### F4. Context Tamper From Dot

- 机制: clicking an edge dot opens last real context in Monaco, switches it writable, saves JSON, then resumes downstream with modified context.
- 决策: reuse the trace editor surface for context tampering.
- 原话/来源: `01_workflows/05_debugging.md:19` and `01_workflows/05_debugging.md:20` define the context tamper flow; `01_workflows/05_debugging.md:24` records editor reuse.
- 测试: saved modified context is the downstream resume input; original trace remains auditable.
- Status: target-design.
- 归属: capability `debug-resume`; capability `trace-observability`; region `editor`, `canvas`.

### F5. Shared Trace State Deriver

- 机制: use one event-to-node-state derivation for run lights and debug red/resume states.
- 决策: the derivation belongs to trace-observability and should be reused.
- 原话/来源: `01_workflows/05_debugging.md:25` assigns Q4 to trace; `01_workflows/04_run-and-verify.md:106` records the same decision.
- 测试: the same event fixture produces run status and debug state without divergent mappings.
- Status: target-design.
- 归属: capability `trace-observability`; capability `debug-resume`; region `canvas`.

## 3. 接口契约
- Prerequisite: a real run with trace and checkpoint artifacts.
- Trace input: event-to-node-state identifies failed/paused node and dot context.
- Resume API target: resume from node/dot with checkpoint reuse and optional injected answer/context.
- Region links: `canvas`, `timeline`, `editor`, `properties`.
- Platform links: `engine`, `state-engine`, `native-fs`.

## 4. 设计决策基础（PM 原话）
- HitL **不做固定画布顶栏**:点节点 debug 悬浮 bar 的"对话"按钮 → **就在该 bar 上方就地弹出一个悬浮富文本输入框**(锚定节点、跟 bar 走);输入即作 HitL 回答注入续跑。

## 5. 决策 + 动机
| ID | 决策 | 动机 |
|---|---|---|
| DEBUG_RESUME-1 | resume API | 单元 `debug-resume-checkpoint`；**为什么**：节点级 resume 用 checkpoint 已有数据精准续跑、上游不重跑(现 `runs.py:resume_run` 501) |
| DEBUG_RESUME-2 | 节点入口 | 单元 `debug-resume-checkpoint`；**为什么**：改完 prompt/代码点节点 [Resume]；脏上游 → 下游 Resume 自动置灰 |
| DEBUG_RESUME-3 | trace 来源 | 单元 `trace-dot-blackboard`（消费；owner=trace-observability）；**为什么**：失败/暂停节点与 dot context 由 trace 事件投影提供，debug 只消费 |

## 6. 测试关键点
1. resume API: baseline 现状为 `resume_run` 返回 501 ⚠️；目标为 失败节点可 resume，并携带 checkpoint / answer / tamper 输入。
2. 节点入口: baseline 现状为 SkillNode 无 Resume button ⚠️；目标为 失败节点显示 Resume，非失败态不显示或 disabled。
3. trace 来源: baseline 现状为 TracePanel/useRunStream 未挂主路径 ⚠️；目标为 resume 选择基于真实 failed-node trace/state。

## 7. 涉及 region / platform
`trace-observability` · `timeline` · `properties` · `engine` checkpoint/resume SSOT

## 8. gaps / 报警
- 🚨 resume API: `resume_run` 返回 501 ⚠️；目标 失败节点可 resume，并携带 checkpoint / answer / tamper 输入。
- 🚨 节点入口: SkillNode 无 Resume button ⚠️；目标 失败节点显示 Resume，非失败态不显示或 disabled。
- 🚨 trace 来源: TracePanel/useRunStream 未挂主路径 ⚠️；目标 resume 选择基于真实 failed-node trace/state。

## 交叉引用（链接, 不复制）
[baseline](./baseline.md)（现状,双向）· `trace-observability` · `timeline` · `properties` · `engine` checkpoint/resume SSOT
