---
doc: _report-2026-06-06-engine-opt-studio-handoff
status: retired（2026-06-06 session 报告快照;engine mvp1 优化总结 + studio 对接建议,内容已消费完毕,仅存档）
owns: 本 session engine 侧优化记录 + engine↔studio 对接 handoff
audience: PM + studio session（B 部分可直接转交 studio session）
related: _api-handshake-audit.md（API 对接细节）· INDEX.md（单元锁台账）
---

# Engine MVP1 优化报告 + Studio 对接建议(2026-06-06)

> 两部分:**A. 引擎侧本轮优化**(已落地、已提交);**B. 给 studio 的建议**(actionable,可转交 studio session)。API 对接细节见 `_api-handshake-audit.md`,单元锁台账见 `INDEX.md`。

---

## A. 引擎侧优化(已落地)

### A1. 设计单元锁迁移收口 —— 11/12 锁定
mvp1 设计文档从"部分优化"推进到 **single source of truth + 单元级锁**。12 个横切设计单元中 **11 个 `locked`**(U1-U9、U11、U12),仅 **U10(API 操作面)defer**(牵 studio + 17 块迁移源未迁)。

- **每个单元锁前过"现状/目标 demarcation 终审"**:堵住反复出现的"把目标态写成现状"缺陷——例如把**未实现**的 agent-loop checkpoint、图级 loop、6 槽中间件链、V4 trace 写得像 live。统一加"⚠️ 现状 vs 目标"框,实现差距标 impl 归 kiro。
- **纠正"假真空"**:多处标"真空"的部件其实决策已定、只差成段——如 iterate 声明语法(收编进 `skill-syntax §2.9`)、action/tool 生命周期(`04-tools §2`)。是 doc 整理活,不是 PM 设计。
- **per-facet 锁判据**:单元按 ◆owner 的**相关 facet** 是否 ✅ 判锁,不被模块整体 A◐ 误挡(纠正过 U1/U4 误判)。

### A2. 文件级 `audited-ready` 机器锁(防多-session 静默漂移)
按 design-doc-standards("无机器层不冒用 FROZEN,过渡用 `audited-ready`"),搭了 **engine 自包含哈希锁机器层**:
- `_audited-ready-hashes.json`(底账)+ `packages/graph-agent/tests/test_doc_hash_lock.py`(**目录 scope** 漂移/缺失/未入账检测)+ `_doc-exemptions.yaml`(豁免须 `file+sha256+reason+owner_approval`)。
- **不耦合 studio**(逻辑通用、实例自包含)。
- **8 个三关全 ✅ + 单元锁齐的模块**(16 文件)已 `audited-ready` 入锁;测试 `4 passed`。
- 直接动机:防当前**并发 studio session 同仓库改**导致的静默漂移。
- 过程发现并修正了 codex 初版测试的一个 bug(全局 basename → 增量锁会误判 15 个未锁模块的同名 `baseline.md`/`mvp1-alignment.md`;改目录 scope)。

### A3. 错误契约 V2(通用引擎错误协议)
以"对接各类 app、非只 studio"视角评估错误码:**分类骨架 OK(版本化 code / 11 domain / severity / stage / 注册表强制),但 payload 太薄**(扁平、定位轴可选且常空、无结构化 details、无 remediation、doc_link 是仓库相对路径、run 只返回单个 error)。证据:studio 不得不自建 `{...,details}` 模型且没消费 engine 4 轴。

设计 V2(G1-G6,**目标归 kiro**,经 codex 复审采纳 + 分期):
- 结构化 `details` + 每码 `details_schema`、定位 `source_span`/`phase_path[]`、`stage_id` 机器枚举、`remediation`、`doc_ref`+`doc_url`、`RunResult.diagnostics`(有界)+ `DiagnosticEmittedEvent` 双轨、i18n/码生命周期。
- 分期:**P0-1**(details+diagnostics)/ **P0-2**(registry 化)/ **P0-3**(安全加码:注册 golden/iterate 待加码 + 运行期细分)/ **P1-P2**(轴审计/i18n/生命周期)。
- 权威在 `compile-rules §3.1 / §3.1.1`,形状 `data-contracts DC5`,API `03-api-contract`。

### A4. Engine↔Studio API 牵手审计
2 个 Explore agent 扫两边 + codex 复审 + 亲验:**predict / compile / resolver / gateway DI 能牵手;run 这条有 3 个 studio 侧 P0**(见 B1)。亲验确认 OK 的:`current_hashes` engine 消费、predict 写 trace、`mock_llm`、Prompt 三视图。详见 `_api-handshake-audit.md`。

### A5. 仓库清理
`git gc --prune=now`:loose objects 18146 → 18、garbage 0,消除每次 push 的 gc 警告。

---

## B. 给 Studio 的建议(可转交 studio session)

> 以下定位均在 `apps/studio/backend/`;engine 契约本身正确,问题在 studio 侧调用/对接。

### B1. 🔴 [P0] run 路径 3 个 bug(立即修)
codex 用临时 V0.3 skill 复现 + 13 测试通过:

1. **skill 路径传错**:`run_manager.py:184` 设 `skill_dir / "SKILL.md"`,worker `:95` 传给 `run_skill()`;但 engine 要 skill **root**(目录且含 `GRAPH.md`,`runner.py:499`)。→ run 返回 `success=False` + `[F-v3-graph-root-missing]`。**修**:传 `skill_dir`(root),对齐 predict 路径(predict 传的就是 root,正确)。
2. **workspace_dir 双层**:worker 传 `workspace_dir=run_dir.parent`(`run_manager.py:97`),而 `run_dir_for`(`skills.py:762`)已是 `.workspace/runs/{id}`,engine 又写 `workspace_dir/runs/{id}`(`runner.py:644`)→ 真 trace/result 落 `.workspace/runs/runs/{id}/`,studio 读的 `.workspace/runs/{id}/trace.jsonl` 是空文件。**修**:传 workspace 根,让 engine 的 `runs/{id}` 落对。
3. **worker 吞失败 = 假成功**:worker 调完 `run_skill` 不查 `result.success`,直接推 `"status":"success"`(`run_manager.py:95→111`)→ engine 的失败被标成 studio 成功。**修**:按 `result.success` 置 status,失败时把 `result.error` 落 metadata。

### B2. 🟡 [P1] ErrorPayload 对接(等 engine V2 落地)
现状:studio 自建 `app/models/errors.py` 的 `{error_code, http_status, message, details}`,**没消费 engine ErrorPayload 的 level/stage/source_path/phase_id 四轴**;compile 投影(`skills.py:1449`)只 file/line/field/severity/message。
建议:engine V2 落地后(`compile-rules §3.1.1`),studio error UI 对接 `source_span`(精确标红)/`phase_path`(嵌套定位)/`stage_id`(机器分支)/`diagnostics`(全集)。**注意**:studio 多处 `extra="forbid"` 模型(`RunMetadata`/`RunDetail`/`ErrorResponse`),engine 加 `diagnostics` 字段后须**同步 studio 模型 + TS 类型**,否则反序列化会被 forbid 挡。

### B3. 🟡 [协同] V4 trace 事件(studio 已就绪、engine 待发)
studio canvas(F4)依赖 `parent_node_id`/`node_type`(微观拓扑)、3 个边操作事件(`blackboard_reduce`/`input_dispatch`/`input_file_injected`)、`phase_execution_id`/`iteration`(逐轮分组)——engine `events.py` 还没发(U9 锁为目标归 kiro)。engine 实现这些事件后,studio 微观/dot/逐轮视图才渲染得出。**Prompt 三视图已可用**(engine `PromptCapturedEvent` 已带 template_source/variables/resolved_prompt)。

### B4. 🟢 [协同] resume / per-node golden(2026-06-10 更新)
- **resume**:engine 已有 public `resume_skill(...)`，支持 checkpoint_id / checkpoint_ns latest、context_overrides 与 HITL ToolMessage 注入；studio `runs.py:69` 仍 501,后续只应薄接 Engine API。
- **per-node golden**:engine 已有 public `evaluate_golden_baseline(...)`，读取 `workspace_dir/golden/<baseline_id>` 并写逐节点 diff/report；studio F5 仍需消费 Engine report,旧 whole-state diff 不再是目标真相。
两者的 Engine 通用能力已落地,剩余是 Studio 消费接线。

### B5. ℹ️ 文档哈希锁 = 两套独立
engine 已自建一套(`packages/graph-agent/tests/test_doc_hash_lock.py` + `docs/engine/mvp1/_audited-ready-hashes.json`),**与 studio 那套(`apps/studio/backend/tests/test_doc_hash_lock.py` + `docs/studio/mvp1/_audited-ready-hashes.json`)完全独立**,各锁各的 docs、互不耦合。逻辑同构,如需可日后抽共享 util(目前按"不混"保持独立)。

---

## C. 后续(kiro 实现 / 优先级待 PM 定)
- 错误契约 V2 分期实现(P0-1 → P2)。
- V4 trace 事件 / resume / per-node golden(engine 侧实现)。
- U10 api-contract(17 块,牵 studio,需双边协同)。
- 更多模块进 `audited-ready`(待各自 W◐/A◐ 缺口补齐 / V2 落地)。
- refactor-target(归 kiro):LOGIC 干净契约落地、iterate loop/图级、checkpoint 内层 ns/agent、6 槽中间件后 3 槽实现等。
