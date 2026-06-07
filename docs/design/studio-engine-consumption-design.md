# Studio 侧引擎契约消费设计（B2–B4·前向）

**日期**: 2026-06-06　**状态**: design（前向；engine 侧 B2–B4 实现归 kiro，本文先把 studio adapter 设计就位）
**不进 FROZEN / 不入哈希锁**：前向设计，engine 契约 kiro 实现时可能微调；engine 稳定后**折叠回** capability 文档（`compile-lint`/`trace-observability`/`debug-resume`/`golden-eval`）。
**三层别混**：① **engine V2 分期**（P0-1/P0-2/P0-3/P1，权威 `compile-rules §3.1.1`）② **studio DTO/落地现状**（多模型 `extra=forbid`、`RunDetail` 现不读 `result.json`、golden 现为 whole-state 旧布局）③ **engine physical-layout SSOT**（golden 户型，studio 只消费不重定义）。
**输入契约（SSOT 在 engine，只消费）**：错误契约 V2 → `01-contract/03-compile-rules §3.1/§3.1.1` + 形状 `04-data-contracts DC5` + API `03-api-contract`；V4 trace → engine `INDEX` U9 + `06-seam/02-observability` + `04-run-outer/02-iterate §2`；resume C2 → `03-api-contract §3.2`；golden 户型 → `01-contract/01-physical-layout §2.2.3`。

---

## 0. 定位
engine 用"对接各类 app、非只 studio"的通用视角定型了错误协议 / 事件流 / resume / golden 户型（部分实现归 kiro）。本文是 **studio 消费方**对接设计：engine 产出什么（输入），studio 模型 / UI / 降级 / **落地面**（route、DTO、TS 类型、数据迁移）怎么接（产出）。B1（run 路径 3 P0）走独立 session，不在本文。

**贯穿硬依赖 — `extra="forbid"` 的真实炸点**：studio 多模型 `extra="forbid"`（多余字段抛错）。但要分清谁真消费 engine 产出 + 真正炸在哪：
- **`CallbackEvent`**（事件判别 union，`_EventBase` 也 `extra="forbid"`，`events.py:42`）—— studio 历史回放时用 `TypeAdapter(...).validate_json` 逐行解析 engine `trace.jsonl`（`run_manager.py:529`），且 `RunDetail.events: list[CallbackEvent]`（`runs.py:104`）。engine 一发新事件类型 / 新字段,**回放/RunDetail 这条路**会被 forbid 挡（`_read_events` 经 `_EVENT_ADAPTER.validate_json` 逐行解析 `trace.jsonl`,`run_manager.py:522`）。**live WS 流不经 forbid 校验**——`_queue_event_subscriber._emit` 走 `event.model_dump(mode="json")` 把 engine **自产**事件序列化出队/上 WS(`run_manager.py:74`),是出向序列化、不反向 validate;forbid 炸点只在**回放/RunDetail** 这一条解析路。
- **`RunMetadata`/`RunDetail`/`ErrorResponse`**（`runs.py:53/99`、`errors.py:10`）—— 是 **studio 自己的 DTO**，当前**并不消费 engine `RunResult`**：`RunDetail` 现在只读 `input_data.json`/`trace.jsonl`/`final_state.json`/`artifacts`，**不读 `result.json`**（`run_manager.py:304/312`）。要拿 engine 的 `error`/`source`/`phases`/`path_diff`/`diagnostics`，studio 得**新建一条"宽容读 `result.json` → 投影到 studio DTO"的路径**（不是拿严格 `RunDetail` 直接吃 engine JSON），并同步前端 TS `RunDetail`（`apps/studio/frontend/src/api/types.ts:188`，现也无这些字段）。

---

## 1. B2 — 错误契约 V2 消费〔分期 gated〕

### 1.1 engine V2 形状（输入，引自 `compile-rules §3.1.1` / `data-contracts DC5`）
- `ErrorPayload`（错误负载；字段名是 **`code`**，非 studio 的 `error_code`）：
  - `source_span:{path, line, column?, end_line?, end_column?}`——**只有 `path`+`line` 保证有,列/末位可选**；`source_path` 留兼容别名。
  - `phase_path:[{skill_id, phase_id, phase_execution_id, kind}]`（kind=logic|agent|subgraph|iterate）——嵌套定位;`phase_execution_id` 与 V4 trace 同源。
  - `details: dict[str, JsonValue]` + registry 每码 `details_schema`（**非自由 dict**；JSON-safe + 脱敏）；`remediation: str`（+ 可选 `remediation_actions` P1/P2）；`doc_ref: graph-agent://errors/<code>` + `doc_url`（`doc_link` 弃用别名）；`stage_id: compile|assemble|runtime|persistence|provider`（机器枚举；`stage` 中文仅展示）；i18n `message_key`+`template_vars`（默认文案 fallback）；码生命周期 `introduced_in/deprecated_in/replaced_by/status`。
- `RunResult` 诊断（**有界 + 双轨,非"全集"**）：`DiagnosticEmittedEvent`（实时,完整 `ErrorPayload` + `diagnostic_id`,走事件流）+ `RunResult.diagnostics`（最终**有界快照** + 主 fatal `error`,靠 `diagnostic_id` 关联）；上限 `diagnostics_limit`/`diagnostics_truncated`/`diagnostic_counts`。
- **注意区分新旧字段**：`error`/`source`/`phases`/`path_diff` 是 `RunResult` **现有**字段（`result.py:68`）；**只有 `diagnostics` 是 V2 新增**（P0-1）。

### 1.2 studio 改动
1. **CallbackEvent 容错解析（不 gated,先做；但要落到 DTO 形状）**：`TypeAdapter` 解析（`run_manager.py:529`）对**未知 event_type / 未知字段**不 raise。**默认策略 = 跳过未知事件并计数告警**（保持 `RunDetail.events: list[CallbackEvent]` 类型不变）。若要**保留 raw**（前端原样显示未知事件），则须改 `RunDetail.events` 类型为 `list[CallbackEvent | RawEvent]` + 前端 TS/渲染——这是更大的改动,默认不取,显式记为可选。无论哪种,丢弃/保留策略必须写死,不留"跳过或保留"模糊。**计数落点也必须写明**:默认仅记 structured log(`WARNING` + `skipped_count`),**不进 `RunDetail`**(`runs.py` 不加字段);若要前端可见,显式新增可选 `RunDetail.parse_warnings: int`(+ 前端 TS),默认不取——不留"计数告警"却无消费位的悬空。
2. **`result.json` → studio DTO 投影通路（宽容读 + 投影，非严格 DTO 吃 JSON）**：新建"读 `result.json`（`runner.py:543` 写）→ 宽容解析 engine `RunResult` → 投影到 studio `RunDetail`/前端 TS"的路径，加 `error`/`source`/`phases`/`path_diff`/`diagnostics` 字段。**分两段 gate**(见 §4)：`error/source/phases/path_diff` 是现有字段、**只等 B1 修好 run 落盘**即可投影；`diagnostics` 等 engine P0-1。
3. **错误 UI 对接（按 engine 分期）**：`source_span` → Monaco **有列/末位时精确区间、否则退行级 marker**；`phase_path` → 画布嵌套定位；`stage_id` → UI 机器分支；`remediation`/`doc_url` → 修复提示 + 可点文档；`diagnostics` → 列表 + **显式标"截断/计数"（`diagnostics_truncated`/`diagnostic_counts`），不承诺全集**；`DiagnosticEmittedEvent` → 实时流式补充。
4. **i18n**：engine `code` + `message_key` → react-i18next 词条 key，`template_vars` 插值；默认文案兜底（`i18n.md` Strategy C）。
5. **compile DTO 扩展（加字段，非仅投影逻辑）**：`CompileError` 模型（`models/skills.py:91`）现仅 `file/line/field/severity/message`，**行内加字段** `code/source_span/phase_path/stage_id/details/remediation`，投影点 `skills.py:1440` + 前端 TS 同步。**`doc_url`/`message_key`/`template_vars` 不进 `CompileError` 行内**——编译错误只带 `code`,前端按 `code` 去 `GET /errors` 码表(§1.2.6)join 出 `doc_url` 与 i18n 文案(`message_key`+`template_vars`),避免每条错误重复嵌信封;行内只保留定位轴 + `remediation` 即时文案。
6. **`GET /errors` 码表消费——需建 studio 适配面（engine 端点现不存在）**：engine `GET /errors` router 现标 `—`（`03-api-contract §3` 未落地）。studio 侧要建：① **后端 proxy/cache route**（拉 engine 码表、按 `registry_version`/`etag` 缓存失效）；② **前端 fetch 点**（从 studio 后端取，渲染 `doc`/`remediation`/`details_schema`）。**studio DTO/TS 信封命名**（对齐 engine `03-api-contract` GET /errors 信封）:`ErrorCatalogEnvelope{registry_version, etag, items: list[ErrorCatalogItem]}` + `ErrorCatalogItem{code, message_key, doc_url, remediation, details_schema, stage_id, status}`(后端 Pydantic model + 前端 TS 双向对齐)。**分期**：信封 + remediation/doc/details_schema = 等 engine **P0-2**；`status=deprecated/replaced_by` 等生命周期、分页/过滤 = 等 engine **P1/P2**（不要塞进 P0-2）。

---

## 2. B3 — V4 trace 事件消费〔分两半〕

### 2.1 engine 现有 vs 待发
- **现有可用**：`phase_start`/`phase_end`/`llm_call`/`tool_call`/`agent_loop_iteration`/`prompt_captured`（三视图 `template_source`/`variables`/`resolved_prompt` 齐，`events.py:217`）。
- **待发（U9 归 kiro）**：`parent_node_id`/`node_type`（微观拓扑）、3 边操作事件（`blackboard_reduce`/`input_dispatch`/`input_file_injected`）、**逐轮归属 `phase_execution_id` + `iteration_index` + `source`**（`02-iterate §2` 行 24）。
  - **3 边事件字段契约(engine 已答 Q1,落 `observability §8`;事件类未建、impl 归 kiro,studio 可照此先做渲染层)**:三者继承 `_EventBase`(`event_type`/`run_id`/`thread_id`/`seq`/`ts`),**事件类本身即操作类型**(判别 `event_type`,无 `op` 字段)。**共有**(支撑按 edge 聚合 + dot 渲染):`from_phase: str|None`(源,图入口 `None`)、`to_phase: str`(目标)、`changed_keys: list[str]`(触及黑板 key)、`blackboard_snapshot: dict`(操作后快照,供 OB5 在 phase 边界近似 reducer-diff)。**专有**:`BlackboardReduceEvent.reducer: str`(`merge`/`append`/`override`,取自 `iterate.accumulate.merge` 声明式元数据——engine 不发 authoritative 逐 reducer 前后态,OB5 选 A,逐 key 用快照比对近似);`InputDispatchEvent.dispatched_keys: list[str]` + `branch_index: int|None`(并联/iterate 扇出各发一条、据此画各自分发边,非并联为 `None`);`InputFileInjectedEvent.file_ref: str` + `target_field: str`。
  - ⚠️ **别混字段**：现有 `AgentLoopIterationEvent.iteration`（`events.py:359`）只是 **agent 内 ReAct loop 轮次**，不等于 V4 的多轮归属（`phase_execution_id`/`iteration_index`/`source`）。逐轮分组必须等 engine 发后者。
  - engine 现状还有缺口:batch 并发跑+聚合**未给每 item 盖维度** → 100 项 trace 全糊在同一 `phase_name`（engine 侧待补，`02-iterate §2`）。

### 2.2 studio 消费（`trace-observability` F1–F6）
- **不 gated,先做**：① 未知事件容错解析（同 §1.2.1）；② 用现有事件做 **phase 级 timeline + 人类可读 trace + Prompt 三视图**（现有 `TracePanel`/`PromptInspector` 已能吃）。
- **gated（engine 发 V4 后）**：微观拓扑嵌套（`parent_node_id`/`node_type`）、边 dot 黑板（3 边事件按 from/to phase 聚合）、**逐轮分组（`phase_execution_id`/`iteration_index`/`source`）**。engine 未发前这几个视图**显式置"不可用"占位,不空白不报错**。

> 更正 round-0 误判:曾说"现有字段够、无需 engine 改"。逐轮分组依赖 engine 发 V4 归属字段,studio 不自己脑补。

---

## 3. B4 — resume / per-node golden〔双边 target〕

### 3.1 resume（节点级续跑）
- **engine public 签名**（`03-api-contract §3.2`）：`resume_run(run_id, from=<node_id> | <node_id>:<iter>, context_overrides?)`——**只命名 `from` / `context_overrides`**。HITL 是**执行语义**（engine 在续跑时把人工回答包成 `ToolMessage` 注入），**不是 engine 已命名的请求字段**。
- **studio 适配**：`ResumeReq`（`runs.py:109`）已有 `context_overrides` + `human_input`；**补 `from`**（`from` 是 Python 保留字,Pydantic 要 alias:`from_: str | None = Field(alias="from")`）。**HITL 投影(engine 已答 Q2,落 `api-contract §3.2`)**:engine HITL 注入入参 = 结构化 `{tool_call_id?: str, content: str}`(给中断点的 pending tool call—`ask_clarification`/`interrupt()`—注一条 ToolMessage)。studio `human_input` → 投影成 `{content: human_input}`;`tool_call_id` **默认省略**,engine 从该 checkpoint 唯一 pending 中断 call 自解析(传了则 engine 校验须匹配;多 pending 并存才需显式传)。`POST .../resume`(现 501)待 engine `resume_run` 落地接通(精确 wire 随内层 create_agent checkpointer 终定,engine `checkpoint §7` 标最高风险项)。
- **checkpoint 失效 → Resume 置灰**：上游/拓扑/输出 schema 变 → 下游 checkpoint 失效 → 前端 [Resume] 置灰（`debug-resume` F2 + `03-api-contract §3.2`;失效语义归 engine `05-invalidation`,studio 只渲染置灰）。
- **UI**（`debug-resume` F1–F4）：失败节点 Resume 按钮、HITL 悬浮输入注入、dot context 篡改续跑。

### 3.2 per-node golden（逐节点期望输出 + 旧布局迁移）
- **消费 engine physical-layout SSOT,不重定义户型**：golden 落 **`.workspace/golden/<baseline_id>/{baseline.json, report.json, cases/<case_id>.json}`**（`01-physical-layout §2.2.3`）。**绑定键 = `phase_id`(engine 已答 Q3 确认,权威在 `physical-layout §3#2`;`golden-eval §8` 那个 `phase_id?` 是 stale 标记,engine 因该文件已哈希锁未改)**。`cases/<case_id>.json` schema(engine 已给):`{case_id: str, phase_id: str(绑定键=校验哪个节点), expected_output: {...}(匹配该 phase 的 io.outputs schema), source: "manual"|"copilot"(永不取 trace,409 天然成立), updated_at: iso8601, input_ref?: str(指向 test_inputs/)}`;`baseline.json`=baseline metadata + 绑定信息,`report.json`=`evaluate_golden_baseline` 评估报告(engine SDK 目标入口,现 drift 未 live)。
- **studio 旧布局迁移（不能只说"按新户型读"）**：studio **当前**是 whole-state 旧布局——`<golden_root>/<id>/golden_metadata.json` + 整份 `final_state.json` 拷贝（`golden_diff.py:26/36/51`,`set_golden_baseline_for_run` 复制整次 final_state）。要迁到 SSOT 的 per-node `baseline.json/report.json/cases/<case_id>.json`：① 读写路径切户型;② whole-state → per-node **按 `phase_id` 拆**(`case.expected_output` vs 该 phase 实跑 output);③ diff 从整 `final_state` 改逐节点字段级(同按 `phase_id` 对齐;现 `golden_diff.py` 作用在整 final_state,per-node 版按 `phase_id` 拆)。**这是 studio 侧数据布局迁移,需显式排期**。
- **studio UI**（`golden-eval` F1–F6）：per-node 字段级 diff 渲染;入口（I/O output + Assets + editor 分屏 + Copilot 分析 bar）;predict 假数据 409 guard（已 live）;run 真实输出做默认种子。**不在 studio 文档定义 golden 磁盘户型。**

---

## 4. 执行顺序与依赖

| 项 | gated? | 依赖 / 何时 |
|---|---|---|
| **B2.1 CallbackEvent 未知事件/字段容错解析（+ 定死跳过/保留策略）** | **否** | 现在即可（`run_manager.py:529`）——engine 发任何新事件的前置 |
| B2.2a `result.json`→studio DTO 投影 + 补 `error/source/phases/path_diff` | 是（仅 **B1**） | 这些是 `RunResult` **现有**字段,B1 修好 run 落盘即可投影,**不等 engine V2** |
| B2.2b 同上通路补 `diagnostics` | 是 | engine **P0-1** |
| B2.3 错误 UI:details/diagnostics | 是 | engine **P0-1** |
| B2.4 错误 UI:remediation/doc_url + `GET /errors` 信封/缓存（建 studio proxy route + 前端 fetch） | 是 | engine **P0-2** |
| B2.5 错误 UI:`stage_id` 机器分支 | 是 | engine **P0-3**（G6 stage 机器化 + 运行期码细分） |
| B2.6 错误 UI:`source_span` 区间 / `phase_path` 嵌套 | 是 | engine **P1**（轴审计逐码补齐） |
| B2.7 `GET /errors` 生命周期（`status`/`deprecated`/`replaced_by`）+ 分页/过滤 | 是 | engine **P1/P2** |
| **B3.1 未知事件容错 + phase 级 timeline/可读 trace/Prompt 三视图** | **否** | 现在即可（现有事件已够） |
| B3.2 微观拓扑 / dot 黑板 / 逐轮分组（`phase_execution_id`/`iteration_index`/`source`） | 是 | engine 发 V4 事件后 |
| B4 resume 接通（`from` alias + `human_input`→HITL 投影 + 置灰） | 是 | engine `resume_run` C2 落地 |
| B4 per-node golden（**含 whole-state→per-node 旧布局迁移**） | 是 | engine per-node golden + `evaluate_golden_baseline` 落地 |

**不 gated 的即时项**：B2.1 + B3.1（CallbackEvent 容错 + 用现有事件渲染 phase 级视图）。B2.2a 仅等 B1。是否现在派实现由 PM 定。

> **设计已 schema-complete(round-4,engine 答 Q1–Q3)**:B3.2 渲染层、B4 `ResumeReq`+HITL 投影、B4 golden 迁移/per-node diff 的**契约都已知**,studio 可**照契约先建**(engine 明示"可先做渲染层");仍 impl-gated 的只是**真实数据**(engine 发 V4 事件 / `resume_run` 落地 / per-node golden SDK 落地)。即:**设计不再卡 engine,只剩实施等 engine 代码**。

---

## 5. 修订记录
- **round-4（engine 答 Q1–Q3 设计意图后整合,B3.2/B4 由占位补成 schema 定稿,不再等 engine "设计")**:① B3.2 三边事件补**字段契约**(共有 `from_phase`/`to_phase`/`changed_keys`/`blackboard_snapshot` + 专有 `reducer`/`dispatched_keys`+`branch_index`/`file_ref`+`target_field`);② B4 resume **HITL 投影定稿**(`{content: human_input}`,`tool_call_id` 省略交 engine 解析);③ B4 golden **绑定键确认 = `phase_id`**(`golden-eval §8` 的 `phase_id?` 是 stale,权威 `physical-layout §3#2`)+ 补 `cases/<case_id>.json` schema + 迁移按 `phase_id` 拆;④ 多模态生成式调用 = **gateway 库 ③b**(PM 2026-06-06,DEF-014,studio 只做 ③a 测试 UX)。**剩下纯 impl-gated(等 engine 发事件/落 resume/落 golden SDK),设计无缺口。**
- **round-3（codex 7.4 通过）后修正**：① CallbackEvent **live 路径错配**——live 走 `event.model_dump()` 出向序列化(`run_manager.py:74`)、不经 forbid,forbid 只炸回放 `validate_json`(`:522`),删"live 也经同一 union"误述;② golden **越界收回**——绑定键 engine 尚未定稿(`golden-eval §8` 标 `phase_id?`),studio 不替 engine 定 schema key,改"等定稿后消费";③ compile DTO 缺口补清——`doc_url`/`message_key`/`template_vars` 不进行内、按 `code` 去 `GET /errors` join;④ `GET /errors` 信封 studio DTO/TS 命名(`ErrorCatalogEnvelope`/`ErrorCatalogItem`);⑤ 未知事件**计数落点**写明(默认 structured log,不进 RunDetail,可选 `parse_warnings` 字段)。
- **round-2（codex 6.8 不通过）后修正**：B3 逐轮字段名 `iteration`→`phase_execution_id`/`iteration_index`/`source`（区分 agent 内 `AgentLoopIterationEvent.iteration`）;B4 写清 `human_input`→engine HITL `ToolMessage` 注入的**投影**（非 engine 同名字段）;CallbackEvent 容错落到 DTO（默认跳过+计数 / 保留 raw 须改 `RunDetail.events` 类型）;`result.json`→DTO 明确为**宽容读+投影**且需同步前端 TS;`GET /errors` 补 studio proxy route+缓存+前端 fetch 落地面;golden 补**旧布局（`golden_metadata.json`+`final_state.json`）→ SSOT per-node** 迁移;gated 拆细——`error/source/phases/path_diff` 仅等 B1（现有字段)、`diagnostics` 等 P0-1、`stage_id` 等 P0-3、`GET /errors` 生命周期等 P1/P2;§(原)engine 提醒移出主体为非 gating handoff 附注（见 §7）。
- **round-1（codex 5.8 不通过）后修正**：golden 路径收回消费 physical-layout SSOT;`source_span` 行级兜底;`diagnostics` 有界+双轨;i18n `message_key`/`code`;`extra=forbid` 拆清谁真消费;补 `GET /errors`/resume 置灰/`from` alias;gated 按 P0-1/P0-2/P1 分期。

## 6. 交叉引用
- engine：`01-contract/03-compile-rules §3.1.1`、`01-contract/04-data-contracts DC5`、`01-contract/01-physical-layout §2.2.3`、`02-mechanism/04-run-outer/02-iterate §2`、`03-api-contract`、`_api-handshake-audit.md`、`_report-2026-06-06-engine-opt-studio-handoff.md`
- studio：`apps/studio/backend/app/{models/runs.py,models/errors.py,models/skills.py,services/run_manager.py,services/skills.py,services/golden_diff.py}`、`apps/studio/frontend/src/api/types.ts`；capability 折叠目标 `02_capabilities/{compile-lint,trace-observability,debug-resume,golden-eval}/mvp1-alignment.md`、`04_platform/i18n.md`

## 7. Handoff 附注（非 studio 执行依赖）
> engine `03-api-contract §3.1`（Golden API 面，`:59`）仍写 golden 在 `phases/<phase_id>/golden.json`、随技能进 git——是**反转前旧路径**，和同仓 `01-physical-layout §2.2.3`（`.workspace/golden/<baseline_id>/...`，不进 git）矛盾。**这是 engine 文档内部治理,不是 studio B2–B4 的 gate**;仅作 handoff 提醒,engine session 统一即可。
>
> 另:engine `golden-eval §8` 的 `phase_id?`(待设计)是 **stale 标记** —— 绑定键权威结论在 `physical-layout §3#2` = `phase_id`(engine 2026-06-06 已确认,因 golden-eval 已哈希锁未改)。建议 engine session 经豁免/re-baseline 修正 `golden-eval §8`,免误导。
