# Codex 评审 prompt 存档 — Studio 侧引擎契约消费设计(B2–B4)

**日期**: 2026-06-06
**用途**: 把 `docs/design/studio-engine-consumption-design.md` 交 codex 对抗性评审(Peer Review Framework 强制 Plan Review checkpoint)。
**派发**: `/ask codex`(下面为完整 prompt 原文)。

---

[PLAN REVIEW REQUEST] Studio 侧引擎契约消费设计(B2–B4)评审

## 你的角色
严格的设计评审者。**对抗性评审** `docs/design/studio-engine-consumption-design.md`——默认有问题、主动挑错、不附和。你有本仓库读取权限,**必须亲自读源码/源文档核对**,不只信文档转述。

## 背景(你没有对话历史)
agent-harness monorepo。`packages/graph-agent` 是**通用 graph-agent 运行时 SDK**(engine),被多 app 以 sidecar 嵌入。`apps/studio/backend` + 前端是其中一个消费方(studio)。engine 已用"对接各类 app"的通用视角定型了**错误契约 V2 / V4 trace 事件 / resume C2**(部分实现归 kiro)。本文档是 **studio 作为消费方**的对接设计,engine 契约是输入。

## 判据(最关键)
engine 是通用 SDK、studio 只是消费方。本设计**只应在 studio 侧消费/适配**,**不得反向要求 engine 改**——除非该需求同时"通用(任何嵌入 engine 的 app 都要)+ 必须(engine 外做不到)+ 只有 engine 能给"。**你要专门挑出任何越界要求 engine 的地方。**

## 重点评审(对抗性)
1. **字段映射对不对**:B2 把 engine V2 的 `source_span`/`phase_path[]`/`stage_id`/`remediation`/`RunResult.diagnostics` 映射到 studio UI(Monaco 精确标红 / 画布嵌套定位 / 机器分支 / 全集诊断),映射合理吗?有错配吗?核 engine 权威 `docs/engine/mvp1/01-contract/03-compile-rules/mvp1-alignment.md §3.1/§3.1.1` + `data-contracts DC5`。
2. **extra=forbid 分析对不对**:studio `RunMetadata`/`RunDetail`/`ErrorResponse`/`CallbackEvent` 是否真 `extra="forbid"`?"放开是 engine 加字段的前置"成立吗?核 `apps/studio/backend/app/models/runs.py`、`errors.py`。
3. **gated/not-gated 排序**:B2.1(放开 forbid + 给 `RunDetail` 补 `diagnostics`/丢失字段)真不 gated 吗?其余 gated 判断对吗?(§4 表)
4. **B3 降级设计**:engine 未发 V4 事件前 studio 降级到 phase 级——合理 / 够吗?
5. **B4 resume**:`ResumeReq` 补 `from`(节点寻址)+ 接 engine `resume_run` C2 寻址,契约对吗?核 `_api-handshake-audit.md` §3.3 + `03-api-contract` resume。
6. **完整性**:有没有漏掉 studio 消费侧该设计的东西?有没有哪条其实越界要求 engine(应收回)?

## 源文件
- 本设计:`docs/design/studio-engine-consumption-design.md`
- engine:`01-contract/03-compile-rules/mvp1-alignment.md`、`01-contract/04-data-contracts/mvp1-alignment.md`、`03-api-contract/mvp1-alignment.md`、`_api-handshake-audit.md`、`_report-2026-06-06-engine-opt-studio-handoff.md`
- studio:`apps/studio/backend/app/models/runs.py`、`app/models/errors.py`、`app/services/run_manager.py`、`app/services/skills.py`

## 输出
- 先结论清单:① 字段错配 ② 越界要求 engine(应收回)③ 遗漏 ④ gated 判断错。每条挂 `file:line`。
- 再 rubric 打分(overall + 各维度;通过 ≥7.0 且无单项 ≤3),文字批评优先。
- 中文。

## round-3 补充（文档已按 round-2 评审修订）
文档已按 round-2（codex 6.8 不通过）全部修订,见文档 §5 修订记录:B3 逐轮字段名改 `phase_execution_id`/`iteration_index`/`source`（区分 agent 内 `AgentLoopIterationEvent.iteration` 只是 ReAct loop 轮次）;B4 写清 `human_input`→engine HITL `ToolMessage` 注入的**投影**（engine 签名只命名 `from`/`context_overrides`,HITL 是执行语义非同名字段）;CallbackEvent 容错落到 DTO（默认跳过+计数 / 保留 raw 须改 `RunDetail.events` 类型,二选一已定死）;`result.json`→DTO 明确为**宽容读+投影**且同步前端 TS;`GET /errors` 补 studio proxy route+缓存+前端 fetch 落地面;golden 补 **whole-state（`golden_metadata.json`+`final_state.json`）→ SSOT per-node** 旧布局迁移;gated 拆细（`error/source/phases/path_diff` 仅等 B1、`diagnostics` 等 P0-1、`stage_id` 等 P0-3、`GET /errors` 生命周期等 P1/P2）;engine golden 文档矛盾提醒移出主体为 §7 非 gating handoff 附注。**请复核这些修订是否到位、有无新错配/遗漏/越界;若已达线请明确给过。**

## 确立判据的 PM 原话
> engine应该是通用的sdk包, 不是只服务你, 你要考虑他有通用性要求; 你可以提出需求, 但必须是通用的, 必须的, 其他一些adaptor的工作应该是你自己后端做的
