---
ws_id: WS-3-six-states
modules: [08]
depends_on: []
blocks: []
owns_files:
  - apps/studio/backend/app/services/llm_state_projection.py        # ProviderUiState Literal + project_provider_model_state + _setup_reason + 新增蓝态判定 helper
  - apps/studio/backend/app/services/llm_role_materializer.py       # materialize 跳过集合 needs_setup→failed + _projection 喂 draft_history
  - apps/studio/backend/app/routers/llm.py                          # 仅 6 态连带点：_provider_model_option / _provider_model_projection（投影消费点）+ _model_group_response 的 status_summary + _admission_decision
  - apps/studio/backend/tests/services/test_llm_state_projection.py # 投影单测（现断言 needs_setup，要改 6 态 + 加蓝态）
  - apps/studio/backend/tests/routers/test_llm_registry_api.py      # registry API（现断言 needs_setup，要改 failed/historical_ready + status_summary 6 态）
  - apps/studio/backend/tests/routers/test_llm_role_materializer_api.py # materializer API（现断言 needs_setup → failed）
spec_ssot:
  - docs/graph-agent-gateway/mvp1/08-orch-test-status-ssot/mvp1-alignment.md  # §接口契约 + §F2(6态) + §F1/F3/F4/F6
status: drafted
created: 2026-06-06
owner: Graph-Agent Gateway
related_design: ../../../docs/graph-agent-gateway/mvp1/08-orch-test-status-ssot/mvp1-alignment.md
related_baseline: ../../../docs/graph-agent-gateway/mvp1/08-orch-test-status-ssot/baseline.md
related_plan: ../../../docs/graph-agent-gateway/mvp1/_impl/IMPL_PLAN.md
review_flow: Claude 写任务书 → Codex 写 RED 测试 → Claude 契约门 → Gemini 实现 GREEN → Codex 审 → Codex 回写 baseline → Claude 终审
---

# Graph-Agent Gateway MVP1 WS-3 — Studio provider 6 态投影改造 · 任务书

> **流水线当前位置**：本任务书 = 输入。下一步 = Codex 按 §6 写**失败测试（RED）**，Claude 过**契约门**（审"测试是否忠实编码 alignment §F2 6 态目标"），通过后才放给 Gemini 实现。**禁止跳过契约门直接实现。**
>
> **给 agentic worker 的边界提醒**：
> - **owns 锁（IR1/IR7）**：只碰 frontmatter `owns_files` 那 6 个文件。`apps/studio/backend/app/services/llm_import_drafts.py`（证据库）**只读 import、绝不修改**；前端任何 `.ts/.tsx`（含 `api/llm.ts`、`provider-state-badge.tsx`）**不在本 WS**（见 §9）。
> - **工作树很乱**：`apps/studio/backend/app/routers/llm.py` 已有一堆**预存未提交改动**。只改本任务点名的 6 态连带行，**不要碰、不要回退那些预存改动**。
> - **git 纪律**：不 `git commit`、不 `git add .`；如被要求 stage，只按文件名 stage 本 WS owns 文件。

---

## 1. 目标（intent + why）

把 Studio provider UI 状态从现状**旧 5 态** `ready/untested/cooling_down/needs_setup/off` 改成目标**6 态** `ready/historical_ready/untested/failed/cooling_down/off`：

- **取消 `needs_setup`**（灰），并入 `failed`（🔴 红）+ `reason_code`——动机：配置缺口本质是 failure，灰色会和 untested（没测、中性）混淆、弱化"这是要修的错误"（alignment §F2 PM 取消 needs_setup 原话）。
- **新增 `historical_ready`**（🔵 蓝 = 以前联通过）作为第 6 态——动机：endpoint 验过 + 历史 probe 连通过、但当前无 live 验证时，给一个"以前好"的中间态（介于 untested 与 ready 之间），由 draft/证据库历史证据推出。

后端 SSOT（单一事实源）投影出 6 态，前端只读、只渲染颜色。目标机制细节以 `spec_ssot`（alignment）为唯一真理，本任务书只给指针 + 增量（测试/验收/文件归属/顺序），不复制 alignment 正文（IR5）。

---

## 2. SSOT 指针（grounding，IR2/IR5）

- **目标（怎么做，唯一真理）**：`docs/graph-agent-gateway/mvp1/08-orch-test-status-ssot/mvp1-alignment.md`
  - §接口契约表（`ProviderUiState` Literal 改动 + `project_provider_model_state` 新增 `draft_history` 入参）
  - §F2「6 态 UI state」（6 态语义 + 投影优先级 + 蓝态判据从窄 + failed 两类 reason）
  - §F1「探测→持久化→投影→复用」（materialize 复用投影、跳过 failed/off）
  - §F3「draft + evidence library 知识库」（蓝态历史证据来源 = `EvidenceRecord.trust_state`）
  - §F4「后端 SSOT 回写四类」（failed 的 reason 来源语义）
  - §F6「版本-stale + 历史证据两轴合成」（蓝态合成；本 WS 只做 draft 历史这一轴，见 §9）
- **现状（起点）**：`docs/graph-agent-gateway/mvp1/08-orch-test-status-ssot/baseline.md` §1（投影判定顺序）+ §5（游离 probe-verified 展示）
- **并发分区**：`docs/graph-agent-gateway/mvp1/_impl/IMPL_PLAN.md`（WS-3 = 模块 08，无依赖，全并发，P1）
- **必读源码（实现前先读并回述关键符号/现状，IR2）**：
  - `apps/studio/backend/app/services/llm_state_projection.py:12`（`ProviderUiState` 旧 5 态 Literal）、`:23-46`（`project_provider_model_state` 签名 + 判定顺序，现**无 draft_history 入参**）、`:49-56`（`_setup_reason` 现产 missing_key/invalid_endpoint/invalid_model）
  - `apps/studio/backend/app/services/llm_role_materializer.py:51`（现 `if projection.ui_state in {"needs_setup", "off"}` skip）、`:149-154`（`_projection` 调投影，现无 draft_history）
  - `apps/studio/backend/app/routers/llm.py:1717`（`_provider_model_option` 调投影）、`:4273`（`_provider_model_projection` 调投影）、`:1616-1621`（`status_summary` 硬编码 5 态 key + `status_summary[ui_state] += 1`）、`:4286-4291`（`_admission_decision` 含 `{"needs_setup","off"}`）
  - `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:23-31`（`EvidenceTrustState` 七值，蓝态判据 = `"probe-verified"`）、`:332-366`（`EvidenceRecord` 字段：`trust_state`/`route_id`/`scope`）
  - `apps/studio/backend/app/services/llm_import_drafts.py:74-81`（`load_evidence_library` 读证据库，找不到返回空 library——消费点 import 它读证据，**不改此文件**）

---

## 3. 文件归属（并发锁，IR1）

**本 WS owns（可改/建）**：见 frontmatter `owns_files`。说明 `routers/llm.py` 仅 carve 出 4 个 6 态连带点（`_provider_model_option`、`_provider_model_projection`、`status_summary`、`_admission_decision`），**不是整文件改写**。

**禁止触碰**：
- `apps/studio/backend/app/services/llm_import_drafts.py` — 证据库模块（只读 import `load_evidence_library`，不改逻辑/不加查询函数）。
- `apps/studio/backend/app/routers/llm.py:871-876`（`probe_import_draft` 桩）— 去桩是独立待办（见 §9），不在本 WS。
- `apps/studio/backend/app/routers/llm.py:4076-4106`（evidence 推导 `probe-verified` 展示标签）— 收口为蓝态是后续工作，本 WS 不动（见 §9）。
- 任何前端 `.ts/.tsx`（含 `api/llm.ts`、`provider-state-badge.tsx`、`AvailableModelsSidebar.tsx`、`role-route-status.tsx` 等）。
- `routers/llm.py` 内的预存未提交改动（工作树乱，与本 WS 无关的改动不碰）。

**共享文件协调**：`routers/llm.py` 只被 WS-3 触碰（WS-1/2/4/5 的 owns 均不含它，见 IMPL_PLAN §三），无并发冲突；但同文件有预存改动，靠"只改点名行"隔离。

---

## 4. 现状锚点（baseline）

现状投影 `project_provider_model_state`（`llm_state_projection.py:23-46`）判定顺序：`off（disabled）→ needs_setup（_setup_reason 命中）→ cooling_down（active circuit）→ ready（双 verified）→ untested（兜底）`，产**旧 5 态**，签名只读 `endpoint/route/circuits/now`、**不读 draft 历史证据**。`_setup_reason`（`:49-56`）对"缺 key / endpoint failed / route failed"返回 reason 字符串触发 needs_setup。详见 baseline.md §1。

---

## 5. 目标行为（可测的契约 — 提炼自 alignment，权威以 alignment 为准）

> 以下是**测试契约要点**（让 Codex 能写测试），权威语义见 alignment §F2 + §接口契约；如本节与 alignment 冲突，以 alignment 为准（IR5）。

### 5.1 `ProviderUiState` 6 态（删 needs_setup、加 historical_ready + failed）
- 目标 Literal：`["ready", "historical_ready", "untested", "failed", "cooling_down", "off"]`。
- 颜色心智（alignment §F2）：红=出错要你修；灰=非错误的不可用（untested/cooling_down/off）；绿=好（ready）；蓝=以前好（historical_ready）。

### 5.2 投影优先级链（alignment §F2 投影优先级）
`off > failed🔴 > cooling_down > ready🟢 > historical_ready🔵 > untested⚪`。
- `historical_ready` 插点 = 现 `ready` 检查（`:44-45`）之后、`untested` 兜底（`:46`）之前。

### 5.3 各态判定（提炼，权威见 alignment §F2）
- **off**：endpoint 或 route `status == "disabled"`（优先级最高，不变）。
- **failed🔴（取代 needs_setup，带 reason_code）**：两类经 `reason_code` 区分——
  - ① **配置缺口**（现状 `_setup_reason` 命中：缺 api_key 等）→ `reason_code = "missing_config"`；
  - ② **测试失败**：endpoint `status == "failed"` → `reason_code = "endpoint_unreachable"`；route `status == "failed"` → `reason_code = "model_failed"`。
  - 注：alignment §F2#4 把配置缺口范围写作"缺 key / base_url / protocol / model id"。MVP1 至少把现状 `api_key` 缺失映射为 `missing_config`；是否扩展检查 base_url/protocol/model id 缺失，由 Codex 写测试 + 契约门裁定，不能扩展的登记 deferred（§9）。
- **cooling_down**：存在匹配且 `retry_at > now` 的 active circuit（带 retry_at/message，不变）。
- **ready🟢**：endpoint.status 和 route.status 都是 `verified`（不变）。
- **historical_ready🔵（新增）**：endpoint.status == `verified` **且** 该 route 有 probe-verified 历史连通证据（`draft_history` 入参为真）**且** route.status != `verified`（否则上一档已返回 ready）。
- **untested⚪**：以上都不命中的兜底（含"有 doc-discovered / draft-inferred 但无 probe-verified 历史"——蓝判据从窄，这类**不冒充蓝**）。

### 5.4 `project_provider_model_state` 新增入参 `draft_history`（alignment §接口契约）
- 新增 keyword-only 入参 `draft_history`（语义：该 route_id **是否有 probe-verified 历史连通证据**；MVP1 用 `bool` 即可，命名沿用 alignment 接口契约表）。
- 投影**保持纯函数**：只消费 `draft_history` 布尔，**不在投影内读文件/证据库**（③b 内核不绑存储介质）。
- 蓝态判定 helper（纯函数，建议放 `llm_state_projection.py`）：输入"已加载的 `EvidenceRecord` 列表 + route_id"，输出 bool；判据 = 存在 record 满足"匹配该 route（按 `EvidenceRecord.route_id` 或 `scope` 中的 route_id，实现前核对 schema）+ `trust_state == "probe-verified"`"。`doc-discovered`/`provider-list-observed`/`draft-inferred`/`probe-failed`/`deprecated`/`stale` **都不算蓝**。
- **消费点负责"读证据 + 算 draft_history + 喂投影"**（绑存储介质 = ③a 应用层）：消费点调 `load_evidence_library()`（只读）取 `evidence_records`，调上面纯 helper 算出布尔，传入投影。

### 5.5 materialize 复用（alignment §F1#6）
- `materialize_role` 跳过集合从 `{"needs_setup", "off"}` → `{"failed", "off"}`（needs_setup 已并入 failed）；`cooling_down` 仍写 warning（不变）；其 `_projection` 同样要喂 `draft_history`。

---

## 6. 测试要求（Codex 必须覆盖 — RED 清单，IR3/IR4）

> Codex 按此写**失败测试**，Claude 在契约门审"是否忠实编码 alignment §F2 目标"。标 ★ 的必须有**真实端到端**（registry API 级，非纯 mock 到绿）。

**A. 投影纯函数（`test_llm_state_projection.py`）**
1. **6 态优先级链全覆盖**：off / failed / cooling_down / ready / historical_ready / untested 各产正确态，且优先级 `off > failed > cooling_down > ready > historical_ready > untested` 被验证（现 `test_provider_state_projection_uses_explicit_priority_chain` 要扩成 6 态）。
2. **取消 needs_setup（回归）**：现 `:73` 断言 `ui_state == "needs_setup"` + `:74` `reason_code == "missing_key"` → 改为 `ui_state == "failed"` + `reason_code == "missing_config"`；并断言 `ProviderUiState` 不再含 `"needs_setup"`。
3. **failed 三 reason**：配置缺口→`failed`+`missing_config`；endpoint failed→`failed`+`endpoint_unreachable`；route failed→`failed`+`model_failed`。
4. **historical_ready 蓝态**：endpoint verified + `draft_history=True` + route 非 verified → `historical_ready`；`draft_history=False` 同条件 → `untested`。
5. **蓝判据从窄**：构造 `draft_history` helper 输入——只有 `trust_state=="probe-verified"` 的 record 才令 helper 返回 True；其余六个 trust_state 值返回 False。
6. **蓝↔绿升级**：endpoint verified + 有 probe-verified 历史 + route.status 升 `verified` → 投影从 `historical_ready` 升 `ready`（蓝不替代绿）。

**B. materializer（`test_llm_role_materializer_api.py`）**
7. **skip failed（回归）**：现断言 skip `needs_setup` 的用例（`:91`、`:140` 标 `"needs_setup"`）→ 改为该 route 投影 `failed` 且被 materialize 跳过（不进 fallback_chain，进 skipped_provider_details）。
8. materialize 对 `cooling_down` 仍写 warning（不回归）。

**C. registry API 端到端（`test_llm_registry_api.py`）★**
9. **status_summary 6 态**：现 `:660` `status_summary` 含 `needs_setup`、`:666-667` 断言 provider_model `ui_state == "needs_setup"` → 改为 6 态键（含 `failed`/`historical_ready`、去 `needs_setup`），相应 provider_model 断言 `failed`（带 reason）。
10. **hard failure → failed**：现 `:3474` `test_route_probe_force_true_hard_failure_projects_needs_setup` + `:3504` 断言 `needs_setup` → 改为投影 `failed` + 对应 reason（`model_failed`/`endpoint_unreachable`）。
11. **★ 蓝态真 e2e**：往 evidence library 写一条该 route 的 `trust_state="probe-verified"` 证据（用 `append_evidence_record` 或等价真实路径）+ endpoint verified + route 非 verified → registry API 返回该 provider_model `ui_state == "historical_ready"`；再令 route.status=verified → 升 `ready`。
12. **无历史证据回归**：证据库无该 route 的 probe-verified 证据时，同条件 provider_model 为 `untested`（不误报蓝）。

**注**：现有断言 needs_setup 的测试是**既有测试改写**（非新增）——按 IR 要求，回报里必须逐条列出"改了哪些既有测试、从什么断言改成什么"（§Phase 5）。

---

## Phase 0：契约门（Claude 审，Codex 写完 RED 测试后）

- [ ] 0.1 Codex 按 §6 写完失败测试后，Claude 审"测试是否忠实编码 alignment §F2 6 态目标"
  - 重点查：6 态全覆盖 + 优先级链 + 蓝态判据从窄（只 probe-verified）+ failed 三 reason + 取消 needs_setup 回归 + 蓝↔绿升级 + 至少一条蓝态真 e2e（§6 C-11，非纯 mock）。
  - 查既有 needs_setup 断言是否都迁移（§6 A-2/B-7/C-9/C-10），无遗漏。
  - 通过才放 Gemini 实现；不过则打回 Codex 补测试。
  - _Requirements: 08.F2_

## Phase 1：`ProviderUiState` 6 态 Literal + `_setup_reason` 改产 failed

- [ ] 1.1 `ProviderUiState` Literal 5 态 → 6 态
  - `llm_state_projection.py:12`：`["ready","untested","cooling_down","needs_setup","off"]` → `["ready","historical_ready","untested","failed","cooling_down","off"]`。
  - 验证命令：`uv run pytest apps/studio/backend/tests/services/test_llm_state_projection.py -q`
  - _Requirements: 08.F2_
- [ ] 1.2 投影 needs_setup 产出 → failed + reason
  - `llm_state_projection.py:33-35`：`_setup_reason` 命中时返回 `ui_state="failed"` + `reason_code`（不再 `needs_setup`）。
  - _Requirements: 08.F2, 08.F4_
- [ ] 1.3 `_setup_reason` 改产三 reason 枚举
  - `llm_state_projection.py:49-56`：配置缺口（现 missing_key 分支）→ `missing_config`；endpoint failed → `endpoint_unreachable`；route failed → `model_failed`。顶层 `reason_code` 收敛到这三枚举（provider 细分 reason 如需保留可降级到 `ui_detail`，不污染 reason_code——契约门把关）。
  - 验证命令：`uv run pytest apps/studio/backend/tests/services/test_llm_state_projection.py -q`
  - _Requirements: 08.F2, 08.F4_

## Phase 2：投影加 `draft_history` 入参 + `historical_ready` 蓝态

- [ ] 2.1 新增蓝态判定纯 helper
  - 在 `llm_state_projection.py` 加纯函数（建议名 `has_historical_probe_verified(evidence_records, route_id) -> bool`）：存在 `EvidenceRecord` 匹配该 route（按 `route_id` 或 `scope`，实现前核对 `schema.py:332-366`）且 `trust_state == "probe-verified"` → True。仅类型 import `EvidenceRecord`，**不读文件**（保持纯函数）。
  - _Requirements: 08.F2, 08.F3, 08.F6_
- [ ] 2.2 `project_provider_model_state` 加 `draft_history` 入参 + 蓝态投影
  - 签名加 keyword-only `draft_history`（bool，语义见 §5.4）。
  - 在 `:44-45`（ready）与 `:46`（untested）之间插入：`endpoint.status == "verified" and draft_history and route.status != "verified"` → `historical_ready`。
  - 投影内**不读证据库**（draft_history 由调用方喂）。
  - 验证命令：`uv run pytest apps/studio/backend/tests/services/test_llm_state_projection.py -q`
  - _Requirements: 08.F2, 08.F6_

## Phase 3：materializer 适配（skip failed + 喂 draft_history）

- [ ] 3.1 跳过集合 needs_setup → failed
  - `llm_role_materializer.py:51`：`if projection.ui_state in {"needs_setup", "off"}` → `{"failed", "off"}`。
  - _Requirements: 08.F1, 08.F2_
- [ ] 3.2 `_projection` 读证据库算 draft_history 并喂投影
  - `llm_role_materializer.py:131-154`：`_projection` 调 `load_evidence_library()`（只读 import `llm_import_drafts`）取 `evidence_records`，用 Phase 2.1 helper 算 `draft_history`，传给 `project_provider_model_state`。
  - 验证命令：`uv run pytest apps/studio/backend/tests/routers/test_llm_role_materializer_api.py -q`
  - _Requirements: 08.F1, 08.F2_

## Phase 4：`routers/llm.py` 6 态连带点

- [ ] 4.1 两个投影消费点适配新签名 + 喂 draft_history
  - `_provider_model_option`（`:1717`）、`_provider_model_projection`（`:4273`）：读证据库（`load_evidence_library`，只读）算 `draft_history` 传投影。**避免每 route 重复读证据库**（可在 `_model_group_response` 层 load 一次传入，属 routers/llm.py 内实现细节，由 Gemini 选）。
  - _Requirements: 08.F1, 08.F2_
- [ ] 4.2 `status_summary` 5 态 → 6 态（防 KeyError）
  - `_model_group_response`（`:1616-1621`）：硬编码列表 `["ready","untested","cooling_down","needs_setup","off"]` → 6 态（含 `failed`/`historical_ready`，去 `needs_setup`）。否则投影产新态时 `status_summary[ui_state] += 1` 会 **KeyError 崩后端**。
  - _Requirements: 08.F2_
- [ ] 4.3 `_admission_decision` 去 needs_setup
  - `:4286-4291`：`if ui_state in {"needs_setup", "off"}` → `{"failed", "off"}`（保持"原 needs_setup→block"语义迁移到 failed；failed 含配置缺口 + 测试失败，运行期 admission block 合理）。
  - 验证命令：`uv run pytest apps/studio/backend/tests/routers/test_llm_registry_api.py -q`
  - _Requirements: 08.F1, 08.F2_

## Phase 5：验证与回报

- [ ] 5.1 跑全部 WS-3 验证
  - `uv run pytest apps/studio/backend/tests/services/test_llm_state_projection.py -q`
  - `uv run pytest apps/studio/backend/tests/routers/test_llm_registry_api.py -q`
  - `uv run pytest apps/studio/backend/tests/routers/test_llm_role_materializer_api.py -q`
  - `uv run mypy apps/studio/backend/app/services/llm_state_projection.py apps/studio/backend/app/services/llm_role_materializer.py`（`routers/llm.py` 因工作树预存改动可能报无关错误——只确认本 WS 改动点无**新增**类型错误，并在回报里说明）
  - 若有 Studio/Tauri dev session 在跑，改 backend Python 后按项目规则重启 Studio App；未跑则报告"未启动 dev session，无需重启"。
  - _Requirements: 08.F2_
- [ ] 5.2 向 Codex 回报等待审核
  - 回报：modified files、每条验证命令与结果、**逐条列出改了哪些既有测试（从什么断言→改成什么）**、是否有 deferred、是否重启 Studio App。
  - **fail-loud（WS-1 踩坑）**：消费点喂 `draft_history` 是真接线但当前 evidence library 几乎无 probe-verified 历史证据（因 probe worker 是桩，见 §9）——此事实必须在回报里写明，不得当作"蓝态已完整可用"。
  - 不 claim "终审通过"；Gemini 完成 → Codex 审到 §8 硬退出全满足 → Codex 回写 baseline。
  - 不 stage；如被要求 stage，只按文件名 stage 本 WS owns 文件，禁止 `git add .`。
  - _Requirements: 08.F2_

---

## 8. 验收标准（硬退出，IR4）

- [ ] 三个测试文件全绿。
- [ ] `ProviderUiState` = 6 态，不含 `needs_setup`；投影优先级 `off > failed > cooling_down > ready > historical_ready > untested` 被测试验证。
- [ ] failed 三 reason（`missing_config`/`endpoint_unreachable`/`model_failed`）各有测试覆盖。
- [ ] `historical_ready` 蓝态：probe-verified 历史 + endpoint verified + route 非 verified → 蓝；蓝判据从窄（仅 probe-verified）；蓝真探通升绿——均有测试。
- [ ] **无回归**：materialize 跳过 `failed`/`off`、`cooling_down` 写 warning 不变；`status_summary` 不再 KeyError；现有 cooling_down/ready/untested/off 用例仍通过。
- [ ] **至少一条真实 e2e**（§6 C-11）：registry API 端到端从 evidence library 真证据投出 `historical_ready`。
- [ ] mypy 对 `llm_state_projection.py` / `llm_role_materializer.py` 无新增类型错误。

---

## 9. 不做（范围锁定，IR7）

以下**不在本 WS**，发现相关问题记 `docs/deferred-items.md`，不顺手改：

1. **前端 6 态渲染（紧后续 WS，须 fail-loud 声明）**：后端改产 `failed`/`historical_ready` + status_summary 6 态后，前端尚未同步——`api/llm.ts:13`（`ProviderUiState` 旧 5 态类型）、`:113`（`StatusSummary` 含 needs_setup）、`:617`（前端**自算** needs_setup，违反"前端只渲染不自持"，见 alignment §gaps Finding C-2）、`provider-state-badge.tsx:39` / `AvailableModelsSidebar.tsx` / `role-route-status.tsx` / `RoleTestResultPanel.tsx` 等颜色/排序/标签映射 + 大量前端测试。**后端先行会让前端暂时显示异常**（TS 不认新态、颜色映射 fall-through）。前端 6 态同步 = 独立 WS，必须登记 deferred。
2. **probe worker 去桩**：`routers/llm.py:871-876` `probe_import_draft` 是桩（只改 status=probed，不真探测）。蓝态的**真历史证据来源**依赖它去桩——本 WS 把"读证据→喂蓝"接线接通，但当前证据库几乎无 probe-verified 历史，蓝态实际很少触发（接线为真、数据源待 probe worker，alignment §gaps 已登记）。
3. **F5 capability 第二轴**：`_capability_state` 二值升四态（`routers/llm.py:1767`）归模块 05，不在本 WS。
4. **F6 版本-stale 轴**：版本-stale（route 曾 verified、因版本失效不算 ready）字段权威源归 04，本 WS 只做 **draft 历史证据**这一轴的蓝态；版本-stale 合成待 04 落地后补（登记 deferred）。
5. **游离 probe-verified 展示收口**：`routers/llm.py:4076-4106` 从 evidence 推导 `probe-verified` 展示标签——收口为蓝态是后续工作，本 WS 不动该段。
6. **不下沉 gateway 包**：投影/知识库内核下沉 ③b 是后续工程，本 WS 在 studio 后端原地改。

---

## 10. baseline 回写指令（IR6，Codex 实现落地后执行）

实现 + 测试全绿后，Codex 照**真实代码**改 `docs/graph-agent-gateway/mvp1/08-orch-test-status-ssot/baseline.md`：

- §1「UI state projection 判定顺序」：旧 5 态描述 → 6 态已落地（`ProviderUiState` 6 态、`needs_setup`→`failed`+reason、新增 `historical_ready` 插点、投影加 `draft_history` 入参）。
- §1 第 4-5 步、§3「投影到复用」：`_setup_reason` 产 failed reason 三枚举、materialize 跳过集合 `{"failed","off"}`。
- §5「前端易失态」+「待办」：标注 6 态投影已落地的部分；未落地的（前端同步、probe worker 去桩、版本-stale 轴、游离展示收口）照真实状态诚实保留为待办，**不得把"目标当现状"**。
- 同步 binds_code frontmatter（若函数签名/新 helper 落地，更新符号清单）。
- 回写后 baseline 受 design-doc-standards R2（对齐真实代码）约束。

---

## 11. 评审检查点

- **契约门（Claude 审测试，Phase 0）**：6 态 + 优先级 + 蓝判据从窄 + failed 三 reason + needs_setup 迁移无遗漏 + 蓝态真 e2e。
- **Codex 审查退出** = §8 验收硬退出全满足（非主观"看着差不多"）。
- **Claude 终审**：① 合不合 alignment §F2 意图；② baseline 是否诚实回写（含未完成部分，尤其蓝态数据源待 probe worker、前端待同步）；③ 测试是否假绿（蓝态 e2e 是否真从证据库投影，而非 mock 投影输出）；④ 是否只碰 owns、未误改 routers/llm.py 预存改动 / 未碰前端。
