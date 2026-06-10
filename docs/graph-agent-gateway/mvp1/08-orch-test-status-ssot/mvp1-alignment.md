---
module: 08-orch-test-status-ssot
doc: mvp1-alignment
status: drafted
binds_design: ./baseline.md
binds_code: apps/studio/backend/app/services/llm_state_projection.py:ProviderUiState/ProviderModelStateProjection/project_provider_model_state/_setup_reason/_select_active_circuit · apps/studio/backend/app/services/llm_import_drafts.py:create_draft/load_draft/load_evidence_library/append_evidence_record/apply_draft/sync_remote_evidence_library/DraftNotFound/DraftExpired/DraftApplyConflict/DEFAULT_CATALOG_URL · packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:EvidenceRecord/ProviderImportDraft/ProbeResult
units: [test-status-ssot-evidence]
aligns_with: ../README.md · ../DESIGN_UNITS_INDEX.md
---

# 08 — Test Status SSOT（测试状态唯一事实源:6 态投影 + draft/证据库）· MVP1 设计

> **组织方式**：**以每个功能为索引**（DESIGN-PROCESS §2.2 铁律）—— 每个功能(F1–F6)一段，把它的机制/数据流 · 决策+动机 · 原话 · 测试点 · status · 归属**全收在自己段里**；仅「定义」「接口契约」是模块级总览，证据附录(已实现/差异、决策原因、代码索引、覆盖率)留模块级末尾。现状基线见同目录 `baseline.md`。
> **Tier**：③b gateway 公共能力内核（6 态标准总结 `state_projection` + draft/证据库知识库内核 `import_drafts` **本轮反转判 ③b 公共,现散 ③a 待下沉**；UI 颜色渲染 / import-apply 工作流 / 远端源选择 / 存储介质留 ③a）
> **Owns**：把"配置 + 健康 + 熔断 + 历史证据"总结成一套**标准 6 态**(`ready/historical_ready蓝/untested/failed带reason/cooling_down/off`)的投影内核 + 探测证据知识库(draft + append-only evidence + 远端共享)内核；**不渲染颜色、不做 import/apply 工作流 UI、不绑定存储介质**(归 ③a)
> **Status**：设计定稿（2026-06 判据第四轮反转 + ux-spec §4.2 六态对齐）；代码已落地 `ProviderUiState` 六态、`draft_history` 蓝态投影、真实 `probe_import_draft` worker、compact model status 六态收口和前端六态展示。尾债 = `state_projection`/`import_drafts` 仍在 Studio 后端待下沉 ③b；evidence library 回写 active credentials 的规则待明确；`snapshot_version` 填充仍由 loader/materializer/host 侧负责。
> **Related**：[[02-orch-role-resolution]]（materialize 消费 6 态投影排 fallback_chain，已取消 needs_setup）· [[05-orch-capabilities-and-models]]（`capability_state` 第二轴 + identity/notable/model_groups 同属下沉知识库）· [[07-orch-fallback-circuit-probe]]（probe 产证据 + 熔断写 health store）· [[04-orch-registry-schema]]（`ProviderImportDraft`/`EvidenceRecord`/`ProviderRoute` 字段权威源）· [[03-orch-credentials-endpoints]]（endpoint test 回写 active credentials）· studio `llm-copilot-http-api`（HTTP 探测/draft 端点 = ③a 薄壳，`docs/studio/mvp1/04_platform/llm-copilot-http-api/`）
> **决策日志**：`docs/studio/mvp1/01_workflows/00_settings-ux-spec.md` §4.1(draft)/§4.2(6 态体系)/§4.3(测试落点)/§6.0(判据)/§6.4(横切四层) + `docs/graph-agent-gateway/mvp1/module-disposition-revised.md`（08 行两处反转 + 下沉清单）+ gateway 包 `README.md` §3 D/B（6 态总结 + draft 知识库属公共）
> **现状**：见同目录 `baseline.md`

## 定义

MVP1 目标:测试状态以**后端 SSOT(单一事实源)**为准。探测结果回写 active backend store 或 runtime health store,UI **只读投影**,import draft 与 evidence library 只提供候选和证据、不能绕过 SSOT。

⚠️ **本模块反转最大**。原文档隐含把 `project_provider_model_state`(6 态投影)+ `llm_import_drafts`(draft + 证据库)当作"**studio 后端 SSOT / 后端投影**"——即隐性 ③a。按 2026-06 第四轮判据,这两者的**能力内核恰是 ③b 公共**:

- **6 态标准总结** = **③b 公共内核**:把"配置 + 健康 + 熔断 + 历史证据"总结成一套标准状态集,是 gateway 从自身机制提炼的最佳状态方案,任何调模型 app 装上就能用;`module-disposition-revised.md:50` 08 行新判定 = "**③b 公共(标准总结),下沉 gateway;颜色渲染留前端**"。gateway 包 `README.md:74` D 节明确"标准状态总结(6 态)"属公共。
- **draft + 证据库知识库内核** = **③b 公共内核**:记住"哪些模型存在 / 可用 / 值得试"、每条路线历次探测的证据、可远端共享——这是 gateway 背后可沉淀、可共享的知识资产;`module-disposition-revised.md:51` 08 行新判定 = "**③b 公共(知识库),知识库下沉 gateway;import UI 留 studio;远端源选择/配置留 ③a**"。gateway 包 `README.md:64` B 节明确"探测知识库(draft + 证据库 + notable)"属公共。

**留在 ③a 的应用加工(四件事)**:① import / apply 工作流 + 录入 UI(交互)② 状态颜色 / 文案渲染(展示)③ 远端源选择/配置(当前有默认 GitHub URL,并支持 `url` 参数或 `STUDIO_CATALOG_URL` 覆盖；下沉后由应用注入,四件事之④)④ 存储介质(draft / 证据 / 健康库存哪个文件 / SQLite 路径)。

不调真实模型;本模块定义"探测→持久化→投影→复用"的唯一写回路径与状态语义。本文只写文档目标,不改代码。

**判据(本轮反转 6 态投影 + draft 知识库归属，跨 F1/F2/F3 共用)**：

> **判据(本轮反转 6 态投影 + draft 知识库归属)**："换个 app 还原样能用吗?能=③b,不能=③a。"(ux-spec §6.0 判据铁律 `00_settings-ux-spec.md:342`, `00_settings-ux-spec.md:352`) → 6 态标准总结 + draft/证据知识库是 gateway 机制衍生的最佳方案、任何调模型 app 可复用 → **③b 公共**(原隐性 ③a 后端 SSOT);UI 颜色 / import 工作流 / 远端源 / 存储介质绑死那四件事 → **③a**。

## 接口契约

> 跨边界签名 / schema / 错误 / 归属。前端只投影、不持第二份真相(ux-spec §6.5 检查 2);③a↔③b 边界 = ③a 注存储介质 + 渲染颜色 + 跑 import 工作流,③b 出标准 6 态 + 知识库内核。

| 边界 | 契约 |
|---|---|
| **6 态投影输出（③b 内核 → ③a/前端）** | `project_provider_model_state(endpoint, route, circuits, now, draft_history) → ProviderModelStateProjection`{ `ui_state`: 6 态 Literal `ready/historical_ready/untested/failed/cooling_down/off`, `reason_code`(failed 时 `missing_config`/`endpoint_unreachable`/`model_failed`), `retry_at`(cooling_down 时), `ui_detail` }。`draft_history` 表示该 route_id 有无历史连通证据,来自 `EvidenceRecord.trust_state == "probe-verified"`(`apps/studio/backend/app/services/llm_state_projection.py:26-63`)。**前端只渲染 `ui_state`→颜色,不在组件态另存真值**(ux-spec §6.5 检查 2)。 |
| **`ProviderUiState` Literal（③b schema）** | 当前已是 6 态 `["ready","historical_ready","untested","failed","cooling_down","off"]`(`apps/studio/backend/app/services/llm_state_projection.py:15`)。旧 `needs_setup` 已被 `failed` + reason 取代;`_setup_reason` 当前返回 `missing_config`/`endpoint_unreachable`/`model_failed` 并由投影映射到 `failed`(`apps/studio/backend/app/services/llm_state_projection.py:37-39`,`:66-73`)。 |
| **draft / 证据知识库（③b 内核 API）** | `create_draft`/`load_draft`(找不到抛 `DraftNotFound`)/`load_evidence_library`(找不到默认 `studio-evidence-library` 返空 library)/`append_evidence_record`(append-only)/`apply_draft`(route→`unverified_manual`)/`sync_remote_evidence_library`(远端合并去重)。`ProviderImportDraft`{ endpoint_candidates / route_candidates / probe_results / evidence_records / agent_notes / diff } + `EvidenceRecord`{ evidence_type / trust_state / scope / endpoint_id / route_id / model_id / probe_status / probe_attempts } 字段权威源 `registry/schema.py:332-386`(归 04)。当前远端源有 `DEFAULT_CATALOG_URL` 默认 GitHub URL,并支持 `url` 参数或 `STUDIO_CATALOG_URL` 覆盖;下沉后远端源选择由 ③a 配置注入,不把默认源当 ③b 公共事实。 |
| **熔断持久化（③b 内核,与 07 同源）** | `SqliteLlmHealthStore.open_circuit(...)` / `get_active_circuits(route_id, endpoint_id, rate_limit_bucket) → RuntimeCircuit[]`(只返回 retry_at 未过);`RuntimeCircuit` 字段 `scope/scope_id/opened_at/retry_at/ttl_seconds/reason_code/failure_count/message`(`llm_health_store.py:14-101`)。SQLite 路径 ③a 注入。 |
| **SSOT 写回入口（③a 壳触发,③b 内核回写）** | endpoint test `test_endpoint` → 写 `ProviderEndpoint.status`+last_test 并追加模型列表观察 evidence;endpoint model test / official profile probe → 写 route/profile probe evidence;route probe `_force_probe_route` → success 写 `route.status=verified`+clear circuit、temp-fail 开 circuit(不 failed)、hard-fail 写 `route.status=failed`+reason;import draft probe worker → 写 `probe_results`、append probe evidence、temp-fail 开 circuit。evidence 如何进一步回写 active credentials 的晋升规则仍需单独明确。 |
| **存储介质（③a 注入,不归 ③b）** | draft / 证据库 / 健康库存哪个文件 / SQLite 路径 = ③a 提供(gateway 定 schema + 读写,studio 给位置)。`_save_all`(draft/evidence 原子写,目录 `0700`/文件 `0600`,`llm_import_drafts.py:220-244`)的"写哪个目录"由 ③a 决定。 |
| **错误** | `load_draft` 找不到 → `DraftNotFound`;投影对缺失输入有兜底(disabled→off 优先,无证据→untested 兜底)。 |
| **归属 / 稳定性** | `ProviderImportDraft`/`EvidenceRecord`/`ProviderRoute`/`ProviderEndpoint` 字段权威源 = [[04-orch-registry-schema]];`RuntimeCircuit` 与 [[07-orch-fallback-circuit-probe]] 同源;`capability_state` 第二轴归 [[05-orch-capabilities-and-models]];本模块**只链接不复制**,防 drift。 |

---

## 功能逐项（每个功能为索引）

### F1 探测 → 持久化 → 投影 → 复用（唯一写回路径）

- **机制 / 数据流**：**上下游**:① 探测入口(endpoint test / route probe,③a HTTP 壳触发,内核 ③b)→ 写回 **active backend store(endpoint/route status)+ health store(熔断 circuit)+ 证据库(probe 结果含失败)**(③b 内核,③a 注存储介质)→ **6 态投影 `project_provider_model_state`(③b 内核)** 把 status + key + circuit + draft 历史证据合成 UI state → 两个消费方:前端 registry row(③a 渲染颜色)+ [[02-orch-role-resolution]] materialize(③b 编排,跳过 `failed/off`、`cooling_down` 写 warning、只把 fit route 进 fallback_chain)。逐步五段:

  1. 探测入口:Endpoint 探测由 `test_endpoint`(endpoint 探测 API,调 provider models-list 最小请求)发起,route 探测由 `probe_route` / `_force_probe_route`(route 探测 API + 真实探测 helper)发起,draft 探测由 `probe_import_draft` worker 发起;这些入口必须是真实测试状态的唯一写入点之一(`apps/studio/backend/app/routers/llm.py:488-600`,`:810-846`,`:899-972`,`:2017-2076`)。**判据:HTTP 端点 = ③a 薄壳;探测/拆分/匹配的内核 = ③b 公共。**

  2. 持久化 endpoint:Endpoint 成功/失败/空 key/并发变更结果写入 `ProviderEndpoint.status`、`last_test_at`、`last_test_message`,并通过 `save_credentials` 落盘;models-list 观察会追加到 evidence library(`apps/studio/backend/app/routers/llm.py:509-600`)。**判据:status 字段 schema + 写回规则 = ③b;落盘到哪个文件(存储介质)= ③a 注入。**

  3. 持久化 route:Route 成功写 `status="verified"` 并写 capabilities/profile metadata;确定失败写 `status="failed"` 和 reason metadata;临时网络/限流/超时写 runtime circuit,不把 route 永久打 failed(`apps/studio/backend/app/routers/llm.py:843-846`,`:2017-2076`)。

  4. 持久化 circuit:`SqliteLlmHealthStore.open_circuit`(熔断持久化入口,upsert circuit 到 SQLite)把 cooling_down 事实写进 SQLite;`get_active_circuits` 只返回仍未到 retry_at 的 circuit(`apps/studio/backend/app/services/llm_health_store.py:34-62`,`:70-101`)。**判据:熔断持久化内核 = ③b(与 07 同一反转);SQLite 路径 = ③a 注入。**

  5. 投影:前端 registry row 和 role materializer 都调用 `project_provider_model_state`(6 态投影函数),由后端把 status + key + circuit + draft 历史证据合成 UI state(`apps/studio/backend/app/routers/llm.py:1862-1907`;`apps/studio/backend/app/services/llm_role_materializer.py:142-170`)。**判据:6 态投影内核 = ③b(本轮反转);前端把 state 渲染成颜色 = ③a。**

  6. 复用:role 物化时跳过 `failed`(含原 needs_setup 配置缺口)/ `off`,对 `cooling_down` 写 warning,只把 fit 的 route 放进 fallback_chain;这使 UI test state 与实际编排共享同一判断(`apps/studio/backend/app/services/llm_role_materializer.py:48-90`)。**注**:此处旧文写"跳过 needs_setup",**6 态对齐后改为跳过 `failed`**(needs_setup 已并入 failed),与 [[02-orch-role-resolution]] §2 同步。

- **决策 + 动机**：**探测→持久化→投影→复用是唯一写回路径**——`test_endpoint` / `_force_probe_route` / `probe_import_draft` 是真实测试状态的写入入口,投影内核(③b)把多源事实(endpoint status / route status / key / circuit / 历史证据)合成 UI state,materialize 与 UI 共享同一投影口径,不各拼一份。**后端 SSOT 能避免前端易失态**:ready 不是单一字段,而是 endpoint status、route status、secret 存在性、runtime circuit(+ 历史证据)的组合;这些事实都在后端 SSOT,前端只投影、不持第二份(ux-spec §6.5 检查 2;`apps/studio/backend/app/services/llm_state_projection.py:26-73`)。**注**:SSOT 在"后端"是相对前端而言;后端里**投影内核**属 ③b(可下沉 gateway 包),与"前端不持第二份"不矛盾。

- **原话**：见 F2/F3 各功能原话(投影归属判据见模块级「定义」判据铁律)。

- **status**：`project_provider_model_state`、`draft_history` 入参、router/materializer 共享投影、真实 draft probe worker 均已落地；MVP1 剩余工程是投影内核 + 熔断持久化内核 + 知识库内核下沉 gateway(待下沉)。

- **测试点**：
  - **前端不持第二份(ux-spec §6.5 检查 2)**:切 tab / 刷新后状态仍在(从后端投影读)= 对;丢 = 前端自持 = 错。
  - **draft 喂投影**:`project_provider_model_state` 入参含 `draft_history`(读 `EvidenceRecord.trust_state`);回归点 = 必须读到历史证据才出蓝,无证据不能冒充蓝。

- **归属**：**③b** = 探测/拆分/匹配内核 + 6 态投影内核 + 熔断持久化内核(`services/llm_state_projection.py`、`services/llm_health_store.py`、`routers/llm.py` 探测段,待下沉 gateway);**③a** = HTTP `/api/llm/*` 探测端点薄壳(归 14)+ 存储介质(落盘到哪个文件 / SQLite 路径)+ 前端渲染颜色 + 批量探测进度 UI;**② Rust** = N/A(凭证/角色/证据/健康数据永不 Rust)。

### F2 6 态 UI state（取消 needs_setup + 蓝态 historical_ready）

> **本功能为 6 态对齐重写**。原文是旧 5 态(ready/untested/cooling_down/**needs_setup**/off),与文末 MVP1 回填段(蓝态 + 取消 needs_setup)自相矛盾。现按 ux-spec §4.2 canonical 6 态统一,**取消 `needs_setup`(并入 `failed` + reason)、新增 `historical_ready`(🔵 蓝=以前联通过)**。颜色心智(ux-spec §2.1 `00_settings-ux-spec.md:114`):**红=出错要你修;灰=非错误的不可用(untested 没测 / cooling 熔断中 / off 关了);绿=好;蓝=以前好。**

- **机制 / 数据流（UI state 的唯一语义,6 态）**：

  1. `ready`(🟢 绿):endpoint.status 和 route.status 都是 `verified`(真 probe 过);这是唯一绿色可用状态(`apps/studio/backend/app/services/llm_state_projection.py:48-49`)。

  2. `historical_ready`(🔵 蓝=以前联通过):endpoint verified + draft/证据库显示该 route **历史连通过**(来自 `EvidenceRecord.trust_state`,`packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:333-366`),但当前无 live `route.status=verified`;介于 untested 与 ready 之间的历史态。**蓝判据**:只 `probe-verified` 历史(真连通过)算蓝,贴合"以前联通过";doc-discovered / 没连过的不算。**蓝不替代 ready**:真 route-probe 通 → 升 🟢;draft probe worker 与 model probe 会写历史连通证据供蓝态消费(`apps/studio/backend/app/routers/llm.py:899-972`,`:2605-2745`)。投影插点 = `ready` 检查之后、`untested` 兜底之前(`apps/studio/backend/app/services/llm_state_projection.py:48-52`)。

  3. `untested`(⚪ 灰):没有 disabled、没有配置缺口、没有 active circuit、也没有历史连通证据、但也不是双 verified;通常对应 `unverified_manual` 或待验证 route(`apps/studio/backend/app/services/llm_state_projection.py:52`)。

  4. `failed`(🔴 红,带 reason,**取代旧 `needs_setup`**):出错了要你修,两类经 `reason` 区分——① **配置缺口**(缺 key / base_url / protocol / model id,旧 `needs_setup` 已并入此类)reason=`missing_config`;② **测试失败**(route 真探挂)reason=`endpoint_unreachable` / `model_failed`。**红、不挡进可用**(failed route 仍列出、仍可拖,换 role 配置 / 重试可能就好,真正永久不可用在运行期 admission 拦)。当前 `_setup_reason` 已返回 reason code,投影统一产 `failed` + reason(`apps/studio/backend/app/services/llm_state_projection.py:37-39`,`:66-73`)。

  5. `cooling_down`(⚪ 灰+倒计时):存在匹配 route/endpoint/rate_limit_bucket 且 retry_at 未过的 circuit(临时网络/限流/超时);UI 展示 retry_at 和 message,不当永久失败(`apps/studio/backend/app/services/llm_state_projection.py:40-47`,`:76-95`)。

  6. `off`(⚪ 灰+不可选):endpoint 或 route disabled(用户/配置主动关闭),优先级最高(`apps/studio/backend/app/services/llm_state_projection.py:35-36`)。**注**(ux-spec §4.2 单模型 probe 失败两类 `00_settings-ux-spec.md:273`):模型已弃用 / 不再提供(provider 明确返回"无此模型")归 `off`(灰、不可选),**不是** `failed`(不是"连不上",是"没这模型了");弃用可逆——点击仍可复制名 + 单独 re-probe,再次连通 → 从弃用区捞回。

  **6 态投影优先级（route 级,目标语义,ux-spec §4.2 状态分层 `00_settings-ux-spec.md:279-282`）**:`off > failed🔴 > cooling_down > ready🟢 > historical_ready蓝🔵 > untested⚪`。其中 `ready / 蓝 / untested` 同属"证据 tier",按证据新鲜度排:刚测通(ready) > 历史通(蓝,来自 draft) > 无证据(untested)。蓝插在 ready 检查之后、untested 兜底之前。

- **决策 + 动机**：
  - **6 态标准总结 `state_projection` = ③b 公共内核(本轮反转)**:把"配置 + 健康 + 熔断 + 历史证据"总结成标准状态集,是 gateway 从自身机制提炼的最佳方案、任何 app 可复用;**判据**:"换个 app 还原样能用吗?能=③b"。**被反转**:原 baseline `Baseline/Alignment 差异` 与 `决策原因` 隐含"UI state 必须**后端**投影"——把它当 studio 后端职责(隐性 ③a);现按判据,投影**内核** = ③b 公共,**只有把 state 渲染成颜色 = ③a**(`module-disposition-revised.md:50`、ux-spec §6.4 横切表 `00_settings-ux-spec.md:468`)。
  - **取消 `needs_setup`,统一 `failed`(红)+ reason(6 态对齐)**:消除文档自相矛盾(原正文旧 5 态 vs 文末回填段 6 态)+ 对齐 PM 裁定。心智:红=出错要你修、灰=非错误的不可用、绿=好、蓝=以前好;`needs_setup`(配置缺口)本质是 failure → 并入 `failed` + reason=`missing_config`,真测试失败 = reason=`endpoint_unreachable`/`model_failed`;权威 ux-spec §2.1 + §4.2 + 状态分层实现 gap(`00_settings-ux-spec.md:285`)。
  - **新增 `historical_ready`(🔵 蓝=以前联通过)第 6 态**:蓝态归 `Capability` 域的 draft/证据子源(历史连通),是 `ui_state` 投影层的第 6 态、**不是新源域**(ux-spec §4.2 状态分层 `00_settings-ux-spec.md:281`);蓝判据从窄(只 probe-verified 历史算蓝)。

- **原话**：
  > **PM #A 6 态体系**(ux-spec §4.2 `00_settings-ux-spec.md:262`)：标签颜色 = 该 **route** 的状态,**三页一致**;canonical 6 态 = `ready` / `historical_ready`(🔵 蓝) / `untested` / `failed`(带 reason) / `cooling_down` / `off`。

  > **PM 取消 needs_setup**(ux-spec §2.1 #10 PM 裁定 `00_settings-ux-spec.md:114`)：原话 PM 问"现在有一个状态叫做needs_setup, 这是一个什么状态? 要setup什么呢??";裁定"取消原 `needs_setup` 灰态——它本质是 `failed` 的一个 reason(配置缺口),并入 failed 显红"——理由:①「配置缺口」本质是 failure、和 failed 同族;②灰色会和 untested(没测、中性)混淆、弱化"这是致命错误";③现码 `_setup_reason` 把真测试失败也揉进 needs_setup 显灰、双重混淆。

  > **PM 蓝↔绿 = endpoint 验证 vs model 保证**(ux-spec §4.3 + §4.2 状态分层 `00_settings-ux-spec.md:283`)：API key 页验 endpoint + draft 回填 → 模型显 🔵 蓝;role 页对模型真 probe → 升 🟢 绿。即"endpoint 验证(蓝)→ model 保证(绿)"。

- **status**：已落地:后端 `ProviderUiState` Literal 是六态,旧 `needs_setup` 已取消并由 `failed` + reason 替代,`historical_ready` 由 `draft_history` 驱动;前端类型、Available Models provider tag、ProviderStateBadge、ProviderCard route tag 已同步六态(`apps/studio/backend/app/services/llm_state_projection.py:15-73`;`apps/studio/frontend/src/api/llm.ts:12-13`;`apps/studio/frontend/src/components/studio/settings/llm-roles/AvailableModelsSidebar.tsx:511-540`;`apps/studio/frontend/src/components/studio/settings/llm-roles/provider-state-badge.tsx:15-59`;`apps/studio/frontend/src/components/studio/api-keys/ProviderCard.tsx:348-378`)。

- **测试点**：
  - **6 态投影**:① 双 verified → `ready🟢`;② endpoint verified + draft 有历史连通证据 + 无 live verified → `historical_ready🔵`;③ 无任何证据 → `untested⚪`;④ 缺 key/base_url/protocol/model id → `failed🔴` reason=`missing_config`;⑤ route 真探挂 → `failed🔴` reason=`endpoint_unreachable`/`model_failed`;⑥ active circuit 未过期 → `cooling_down`(带 retry_at);⑦ disabled / 模型弃用 → `off`。
  - **取消 needs_setup(回归)**:任何旧产 `needs_setup` 的输入(配置缺口)现产 `failed` + reason;`ProviderUiState` Literal 不再含 `needs_setup`。
  - **蓝↔绿升级**:`historical_ready🔵` 的 route 真 route-probe 通 → 升 `ready🟢`(蓝是历史态,不替代 ready)。
  - **蓝判据从窄**:只 `probe-verified` 历史(真连通过)算蓝;doc-discovered / 没连过的 → 仍 `untested`(不冒充蓝)。
  - **投影优先级**:同时满足多态时按 `off > failed > cooling_down > ready > 蓝 > untested` 取最高优先。

- **归属**：**③b** = 6 态投影内核(`services/llm_state_projection.py`,待下沉);**③a** = 前端把 state 渲染成颜色/文案。

### F3 draft + evidence library 知识库

- **机制 / 数据流（draft + evidence library 的目标边界）**：

  1. Draft 输入:Agent/import 抓到的 endpoint_candidates 和 route_candidates 先进入 `ProviderImportDraft`(非可信导入草稿),不直接进入 active credentials(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:369-386`)。**判据:draft 数据结构 + 知识库内核 = ③b 公共;import/apply 工作流 UI = ③a。**

  2. Evidence 输入:probe / 文档 catalog 证据进入 `EvidenceRecord`(append-only 证据记录),保留 trust_state、scope、probe_attempts、successful_probe/failed_probe 等字段,供人工或后端决策复用(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:332-366`)。**PM 原话(ux-spec §1.4 #2.4)要求"探测结果含失败都写进 draft / 证据库,不浪费"**——失败也是历史(哪些模型抖动 / 超时 / 不可用),下次批量探测可优先跳过历史失败、优先试历史成功。

  3. Evidence 追加:`append_evidence_record`(证据追加入口)继续 append-only,给 evidence 补 observed_at/attempted_at、合并 route_candidates、把新 record 追加到尾部,避免新的单条证据覆盖旧观察;但它不能直接代表 UI ready 状态(`apps/studio/backend/app/services/llm_import_drafts.py:95-129`)。

  4. Draft 应用:`apply_draft`(draft 应用入口)继续要求显式应用和冲突处理;应用后的 route 默认 `unverified_manual`,必须再经过 route probe 或可信回写流程变成 active verified(`apps/studio/backend/app/services/llm_import_drafts.py:137-203`)。**判据:apply 的冲突处理工作流 = ③a;route 默认态 schema = ③b。**

  5. Remote library:`sync_remote_evidence_library`(远端证据同步入口)可以合并远端 evidence(拉远端 JSON、合并 route_candidates/capabilities/metadata、按 evidence_id 去重追加),但远端证据仍应作为 advisory library,不能越过 active credentials/status SSOT(`apps/studio/backend/app/services/llm_import_drafts.py:298-377`)。**判据:同步/合并/去重的知识库内核 = ③b;远端源选择/配置 = ③a(`module-disposition-revised.md:71`)。当前代码有默认 GitHub URL,也支持 `url` 参数或 `STUDIO_CATALOG_URL` 覆盖。**

  6. Draft probe worker:`probe_import_draft` 当前会把 draft 标为 `probing`,逐个 route candidate 执行 `_probe_import_draft_route`,写 `probe_results`,追加 probe evidence,并在 transient failure 时打开 route circuit;最后把 draft 标为 `probed`(`apps/studio/backend/app/routers/llm.py:899-972`)。

- **决策 + 动机**：
  - **draft + 证据库知识库内核 = ③b 公共内核(本轮反转)**:记住"哪些模型存在/可用/值得试"+ 每条路线探测证据 + 可远端共享,是 gateway 背后可沉淀可共享的知识资产;**被反转**:原 baseline 把它当"studio 隔离草稿 / advisory store"(隐性 ③a 后端);现知识库**内核** = ③b 下沉,**import/apply 工作流 + 远端源选择/配置 + 存储介质 = ③a**(`module-disposition-revised.md:51`, `module-disposition-revised.md:71`、gateway 包 `README.md:64`)。
  - **evidence library 不能直接驱动执行**:它可以来自远端 catalog 或历史观察、可信度不同;active route.status 必须由本地显式 probe/apply 写回决定(`apps/studio/backend/app/services/llm_import_drafts.py:95-129`,`:298-377`)。蓝态是历史/建议态,真 route-probe 通才升绿。
  - **draft 隔离能保护 active runtime**:import draft 来自非可信 Agent/onboarding 输入,`apply_draft` 已要求冲突处理、route 默认置 `unverified_manual`,这是防止未经验证候选直接进 ready 的关键(`apps/studio/backend/app/services/llm_import_drafts.py:137-203`)。

- **原话**：
  > **PM draft 赋能/写回 + 失败也是历史**(ux-spec §0.1 + §4.1 `00_settings-ux-spec.md:11`, `00_settings-ux-spec.md:259`)：原话"拉取draft API, 对比模型list diff, 把draft中已证实的资料填给 model list, model list标签变成蓝色, 表明以前联通过. 有新的模型, capability...把diff的部分写回draft";"这几次的 endpoint / 模型探测结果(含失败)都要写进 draft / 证据库,不浪费(失败也是历史:哪些模型抖动 / 超时 / 不可用;下次免重探、喂蓝态)"。（注:其中"标签变蓝色=以前联通过"喂 F2 蓝态;"写进 draft / 证据库含失败"是本功能知识库内核。）

- **status**：draft/evidence 知识库内核已有(create/load/append/apply/sync),真实 draft probe worker 已落地并会写 `probe_results`/evidence/circuit;剩余工程是把知识库内核从 Studio 后端下沉到 gateway 公共包,并明确 evidence library 到 active credentials 的晋升/回写规则。

- **测试点**：
  - **失败也写证据(PM #2.4)**:route 探测失败(含临时/确定)→ 失败证据写进知识库(下次批量探测可跳过历史失败)。
  - **draft apply 保守默认**:`apply_draft` 后 route = `unverified_manual`(非直接 verified),必须再 probe 才升 active verified。
  - **draft probe worker**:`probe_import_draft` 对 route candidate 真探测,成功/失败都写 `probe_results` 和 evidence;transient failure 打开 cooling_down circuit。

- **归属**：**③b** = draft + 证据库知识库内核(`services/llm_import_drafts.py` 的创建/读取/追加/合并去重 + `ProviderImportDraft`/`EvidenceRecord` 数据结构,数据结构归 04,知识库内核待下沉);**③a** = import/apply 工作流(`apply_draft` 冲突处理 + 录入 UI)+ 远端源选择/配置(当前默认 GitHub URL 可被 `url` 参数 / `STUDIO_CATALOG_URL` 覆盖)+ 存储介质(draft/证据存哪个文件)。

### F4 后端 SSOT 回写规则（四类结果）

- **机制 / 数据流**：**SSOT 写回路径(四类结果,当前语义)**:① endpoint models-list 成功 → 写 `endpoint.status` + last_test 字段,并追加模型列表观察 evidence;② model/profile/draft probe 成功 → 写 active route/profile(适用时) + **写成功 probe evidence**;③ 临时失败(网络/限流/超时/配额)→ 写 health store circuit(`cooling_down`),**不**把 route 永久 failed,并在 draft/model probe 路径写失败 evidence;④ 确定失败 → 写 `route.status=failed` 或 probe result error/reason,并写失败 evidence(适用路径)。投影再把 ④ 变成 `failed🔴`(带 reason,旧 `needs_setup` 已被替代)。逐条回写规则:

  1. 成功的 endpoint models-list 测试回写 endpoint.status 与 last_test 字段;若发现官方 endpoint 的模型列表,可 upsert route,但 route 仍需按 probe 语义决定 verified;同时追加模型列表观察 evidence(`apps/studio/backend/app/routers/llm.py:561-600`,`:2748-2765`)。

  2. 成功的 model/profile probe 回写 route.status、capabilities、verified_profiles 和 probe metadata,并写成功 probe evidence;`_force_probe_route` 的 success path 会写 route verified + clear circuit(`apps/studio/backend/app/routers/llm.py:669-708`,`:748-807`,`:2017-2056`,`:2605-2745`)。

  3. 临时失败回写 health store,不写 route failed;当前 `_force_probe_route` 和 `probe_import_draft` 都对 timeout/rate_limited/quota/network_error 打开 circuit,这是 cooling_down SSOT(`apps/studio/backend/app/routers/llm.py:960-965`,`:2057-2063`,`:2079-2095`)。

  4. 确定失败回写 route.status failed 和 metadata reason,或写入 draft probe result / probe evidence reason;projection 再把它变成 `failed🔴`(带 reason),旧 `needs_setup` 已被替代(`apps/studio/backend/app/routers/llm.py:995-1030`,`:2064-2076`,`:2687-2745`;`apps/studio/backend/app/services/llm_state_projection.py:37-39`,`:66-73`)。

- **决策 + 动机**：**cooling_down 不应写成 failed**:临时网络/限流问题会过期,health store 的 retry_at 能表达"暂时不要用",而 route.status failed 会表达"配置或模型不可用"(`apps/studio/backend/app/routers/llm.py:960-965`,`:2057-2063`;`apps/studio/backend/app/services/llm_health_store.py:70-101`)。**probe evidence 成功+失败都要保留**(PM #2.4):成功证据喂蓝态历史 + 下次免重探,失败证据让下次批量探测可跳过历史失败。evidence 何时能晋升/覆盖 active credentials 仍需规则化。

- **原话**：见 F3 PM #2.4 原话(失败也写证据)+ F2 PM 取消 needs_setup 原话(④ 确定失败投影成 `failed` 而非 `needs_setup`)。

- **status**：endpoint test、endpoint model test、draft probe worker、route force probe 已分别具备 active status / evidence / circuit 的写回基础;`failed` 六态投影已落地。剩余不是旧态改造,而是把 evidence library 回写 active credentials 的晋升规则写清楚。

- **测试点**：四类回写规则结果可经 F2「6 态投影」测试点验证(② 成功→verified、③ 临时失败→circuit/cooling_down 不 failed、④ 确定失败→failed+reason);**失败也写证据**见 F3 测试点。

- **归属**：**③a 壳触发,③b 内核回写**:HTTP `/api/llm/*` 探测端点(③a 薄壳,归 14)触发,`test_endpoint` / `_force_probe_route` 的回写内核 + status 字段 schema = ③b;落盘到哪个文件 = ③a 注入。

### F5 capability 就绪投影（D2 第二轴,与 availability 正交）

- **机制 / 数据流**：除 `ui_state`(能不能用,6 态),投影**第二条轴 `capability_state`(四态:unknown/callable_only/partial/known,见 [[05-orch-capabilities-and-models]] 回填)**,与 availability 分开;`_capability_state` 已按 capabilities 中 `probed_verified` 覆盖比例产四态(`apps/studio/backend/app/routers/llm.py:1932-1947`)。

- **决策 + 动机**：**正交轴(ux-spec §4.2 `00_settings-ux-spec.md:279-282`)**:`ui_state`(能不能用,6 态)≠ `capability_state`(了解多少能力)≠ `role_fit`(适不适合本角色,4 态,归 02)≠ `admission`(运行期 3 态)。可用性与能力了解程度是两个独立问题,不能塞成一态。

- **原话**：（capability_state 第二轴投影本身无独立 PM 原话;正交分轴依据 ux-spec §4.2 状态分层,见上 §决策。）

- **status**：已落地:`_capability_state` 当前产 `unknown/callable_only/partial/known`,与 `ui_state` 正交(`apps/studio/backend/app/routers/llm.py:1932-1947`)。

- **测试点**：**capability_state 第二轴(D2)**:`_capability_state` 四态(unknown/callable_only/partial/known)与 `ui_state` 正交。

- **归属**：**③b**(capability 投影内核,与 6 态投影同处 `services/`,字段权威源 + 第二轴归 [[05-orch-capabilities-and-models]] 回填);**③a** = 前端渲染。

### F6 版本-stale + 历史证据两轴合成（D1 交叉）

- **机制 / 数据流**：版本-stale(见 [[04-orch-registry-schema]] 回填)的"曾 verified"route 在 resolver 侧**不再算 live ready**:registry resolver 会把版本不一致的 `verified_profiles/capabilities` 从 live evidence 中剥离,并把当前 `snapshot.snapshot_version` 传给 `ResolvedRoute`(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:150-183`,`:258-264`)。投影层已经能把 draft 历史证据合成为 `historical_ready🔵`;版本-stale 若要稳定进入蓝态,需要 loader/materializer/host 填充 `snapshot_version` 并把旧 verified 事实保留/转写为可消费的历史证据来源。

- **决策 + 动机**：版本-stale 与 draft 历史是两条独立来源(D1 版本失效 / E1 draft 历史),但 UI 语义都指向"以前 verified、现未重验"。resolver 先保证旧 live evidence 不误当 ready;投影层用 `historical_ready` 表达历史建议态,真重验通才升绿(与 F2 蓝判据一致)。

- **原话**：（两轴合成为投影层内部一致性收敛,无独立 PM 原话;依据 ux-spec §4.2 状态分层 + [[04-orch-registry-schema]] 版本-stale 回填。）

- **status**：registry schema/resolver 的版本-stale 降级已落地;`project_provider_model_state` 的 draft 历史蓝态已落地。仍需明确的是 `snapshot_version` 由 loader/materializer/host 填充,以及版本-stale 的旧 verified 事实如何进入历史证据来源。

- **测试点**：registry resolver:当前 snapshot 有版本而 route evidence 版本不同 → 旧 ready verified profile 不再被选成 live ready(`packages/graph-agent-gateway/tests/test_registry_resolver.py:119-184`)。UI projection:有历史证据且当前无 live verified 的 route → `historical_ready🔵`;真重验通 → 升 `ready🟢`(复用 F2 蓝↔绿升级测试点)。

- **归属**：**③b**(两轴合成投影内核,与 6 态投影同处);版本-stale 字段权威源归 [[04-orch-registry-schema]],draft 历史归 F3 知识库;本模块只链接不复制。

---

## gaps / 待设计

- ⚠️ **Finding C + C-2（2026-06-04 实查代码，状态真实性，强化本模块"后端 SSOT / 前端不持第二份真相"论点）**：
  - **C（probe ≠ runtime）**：Studio endpoint test 走 raw HTTP（探测段经 `_join_base_url_and_endpoint` 会 dedup `/v1`），但 SDK runtime 不 dedup → 同一 base_url，probe 通过、runtime 404（实证见 [[03-orch-credentials-endpoints]] F3 + [chatx-provider-patterns.md](../references/chatx-provider-patterns.md)）。**后果：route 可能 probe 显 verified/绿、runtime 实际挂 = false-positive verified。**
  - **C-2（API Keys 页 Connected 仍需独立收口）**：实查——third-party/custom 的 `Connected` 文案仍由 API Keys 前端 `testStatus` 自算（`ProviderCard.tsx:783-813`，取持久化 `available_models`/`last_test_status`），不等同于 LLM Roles/provider model 的六态投影。Get Models 失败路径目前 catch 只 toast、不会改写持久化状态(`apps/studio/frontend/src/components/studio/settings/SettingsPage.tsx:698-700`);`upsertProviderModelsListResponse` 仍会保留旧 ok/provider models(`apps/studio/frontend/src/components/studio/settings/SettingsPage.tsx:247-275`)。
  - **设计结论（要求）**：① 可用性状态（含 API Keys 页 Connected）由**后端 6 态投影**驱动，前端只读、不自持第二份；② **探测 / Get Models 失败必须回写状态**（降级，而非保留旧 ok）；③ probe 尽量贴 runtime 路径，或显式区分 `HTTP-reachable` / `SDK-runtime-verified` 两态。
- **代码下沉**(后续工程,非本轮):6 态投影内核 + draft/证据知识库内核 + 熔断持久化内核 → gateway 包;颜色渲染 / import-apply 工作流 / 存储介质 / 远端源配置留 ③a。
- **待办(evidence 回写规则)**:为 evidence library 回写 active route status 制定规则,例如仅本地成功 probe 才能写 `verified`、远端 evidence 只能作为建议;当前 `append_evidence_record` 只追加证据,不直接改 active route.status(`apps/studio/backend/app/services/llm_import_drafts.py:95-129`,`:298-377`)。
- **待办(snapshot_version 填充边界)**:`ProviderRoute`/`RegistrySnapshot`/`ResolvedRoute` schema 与 resolver 降级已支持 `snapshot_version`,但 Studio `RolesData.to_registry_snapshot` 当前不填该字段;填充仍由 loader/materializer/host 侧负责(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:207-221`,`:404-442`;`apps/studio/backend/app/models/llm_config.py:279-296`)。
- **待办(远端源配置边界)**:`sync_remote_evidence_library` 当前有默认 GitHub URL,并支持 `url` 参数或 `STUDIO_CATALOG_URL` 覆盖;下沉 ③b 时远端源选择仍应由 ③a 注入,不要把默认源固化成公共内核事实(`apps/studio/backend/app/services/llm_import_drafts.py:298-377`;`module-disposition-revised.md:71`)。
- **疑点(circuit 排序)**:`_select_active_circuit`(active circuit 选择 helper)当前用 `-retry_at.timestamp()` 排序、倾向选更晚 retry_at 的 circuit;如果 UI 想展示"最具体 scope 优先"或"最快可重试",需要调整排序规则(`apps/studio/backend/app/services/llm_state_projection.py:76-95`)。

## 交叉引用（双向，回写）

- [[02-orch-role-resolution]]:materialize 消费 6 态投影排 fallback_chain（已取消 needs_setup,跳过 `failed`/`off`）
- [[05-orch-capabilities-and-models]]:`capability_state` 第二轴 + identity/notable/model_groups 同属下沉知识库
- [[07-orch-fallback-circuit-probe]]:probe 产证据 + 熔断写 health store（`SqliteLlmHealthStore` 同源反转 ③b）
- [[04-orch-registry-schema]]:`ProviderImportDraft`/`EvidenceRecord`/`ProviderRoute`/`ProviderEndpoint` 字段权威源（本模块只链接）
- [[03-orch-credentials-endpoints]]:endpoint test 回写 active credentials + base_url 归一化
- studio `llm-copilot-http-api`（`docs/studio/mvp1/04_platform/llm-copilot-http-api/`）:HTTP `/api/llm/*` 探测/draft 端点 = ③a 薄壳
- ux-spec §4.1(draft)/§4.2(6 态体系)/§4.3(测试落点)/§6.0(判据)/§6.4(横切四层) · 归属表 `module-disposition-revised.md`（08 行两处反转 + 远端源可配置）· gateway 包 `README.md` §3 B/D

---

## 附录 A — 涉及 region / platform（模块级 ③a/③b/② 总表）

> 各功能段已带各自 归属;此处保留跨功能完整 ③a/③b/② 清单作模块级总览。

- **③b** `packages/graph-agent-gateway`(**待下沉**):6 态投影内核(现 `services/llm_state_projection.py`)、draft+证据库知识库内核(现 `services/llm_import_drafts.py`)、熔断持久化内核(现 `services/llm_health_store.py`,与 07 同)、`ProviderImportDraft`/`EvidenceRecord`/`ProbeResult` 数据结构(已在 `registry/schema.py` + `registry/probe_contracts.py`,归 04)、list-models 解析 + 批量探测编排内核(现 `routers/llm.py` 探测段)。
- **③a** `apps/studio/backend` + 前端:import/apply 工作流(`apply_draft` 冲突处理 + 录入 UI)、状态颜色/文案渲染、远端源选择/配置(当前默认 GitHub URL 可被 `url` 参数 / `STUDIO_CATALOG_URL` 覆盖)、存储介质(draft/证据/健康库存哪个文件 / SQLite 路径)、HTTP `/api/llm/*` 探测/draft 端点薄壳(归 14)、批量探测进度 UI。
- **② Rust**:N/A(凭证/角色/证据/健康数据永不 Rust)。

## 附录 B — 已实现 / 与 baseline 差异

1. 已实现:后端已有 `project_provider_model_state`,并且 router 与 materializer 都在调用它,说明 UI 与编排已经共享同一投影口径(`apps/studio/backend/app/services/llm_state_projection.py:26-52`;`apps/studio/backend/app/routers/llm.py:1862-1907`;`apps/studio/backend/app/services/llm_role_materializer.py:142-170`)。**归属:投影内核 = ③b(待下沉)。**
2. 已实现:route force probe 对 success、temporary failure、hard failure 三类结果有不同持久化路径,这是 SSOT 回写的基础(`apps/studio/backend/app/routers/llm.py:2017-2076`)。
3. 已实现:runtime circuit 是 SQLite 持久化,不是前端内存态(`apps/studio/backend/app/services/llm_health_store.py:26-101`)。**归属:熔断持久化内核 = ③b(待下沉,与 07 同);SQLite 路径 = ③a 注入。**
4. 已实现:旧 `needs_setup` 已取消并由 `failed` + reason 取代,`ProviderUiState` 当前为六态,`historical_ready🔵` 已由 `draft_history` 驱动(`apps/studio/backend/app/services/llm_state_projection.py:15-73`)。
5. 已实现:compact model status 旧事实已被替代,当前 DTO status 是六态加 `testing`,并通过 `_provider_model_projection(...).ui_state` 复用同一投影(`apps/studio/backend/app/routers/llm.py:196-209`,`:4353-4401`)。
6. 已实现:import draft probe 已是真实 worker,会写 `probe_results`、append evidence,并对 transient failure 打开 circuit(`apps/studio/backend/app/routers/llm.py:899-972`)。
7. 已实现:前端 `ProviderUiState` / `ModelGroupStatusSummary` / ProviderCard route tag / LLM Roles provider badge 已同步六态(`apps/studio/frontend/src/api/llm.ts:12-13`,`:109-116`;`apps/studio/frontend/src/components/studio/api-keys/ProviderCard.tsx:348-378`;`apps/studio/frontend/src/components/studio/settings/llm-roles/provider-state-badge.tsx:15-59`)。
8. 差异(**判据反转**):baseline 的实现仍散在 Studio 后端;MVP1 归属要求投影内核 + 知识库内核 = ③b 公共(待下沉),仅 UI 颜色 / import 工作流 / 远端源 / 存储介质留 ③a。
9. 差异:baseline `apply_draft` 把 route 写成 `unverified_manual`;MVP1 应保持这个保守默认,并要求后续真实探测或明确规则回写 active route status(`apps/studio/backend/app/services/llm_import_drafts.py:183-203`)。
10. 差异:`snapshot_version` schema/resolver 已支持,但填充仍属于 loader/materializer/host 侧责任,不是 08 投影内核自动生成(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:207-221`,`:404-442`;`apps/studio/backend/app/models/llm_config.py:279-296`)。

## 附录 C — 决策原因（保留 baseline 原文,补反转 + 6 态对齐）

1. UI state 投影内核必须存在,原因是 ready/failed/cooling_down 需要同时看 endpoint、route、secret、runtime circuit(+ 历史证据);这些数据前端不应自己拼(`apps/studio/backend/app/services/llm_state_projection.py:26-73`)。**反转补:此"投影"的内核 = ③b 公共(可下沉 gateway),原 baseline 隐含的"必须 studio 后端"只是相对前端的 SSOT 表述,不与下沉冲突;前端只渲染颜色。**
2. runtime circuit 单独持久化,原因是限流/网络冷却不等于 route 永久 failed;`_force_probe_route` 对 timeout/rate_limited/network_error 打开 circuit,但返回原 route,就是这个语义(`apps/studio/backend/app/routers/llm.py:2057-2063`)。**反转补:熔断持久化内核 = ③b(与 07 同),SQLite 路径 ③a 注入。**
3. draft 必须隔离,原因是 import draft 来自非可信 Agent/onboarding 输入;`apply_draft` 需要显式处理 endpoint collisions,且 route 应用后仍是 `unverified_manual`(`apps/studio/backend/app/services/llm_import_drafts.py:137-203`)。**反转补:隔离/冲突处理工作流 = ③a;draft 数据结构 + 知识库内核 = ③b 公共。**
4. evidence library 适合作为建议材料,原因是它是 append-only 并可远端同步,但不应替代 active credentials 的可执行状态(`apps/studio/backend/app/services/llm_import_drafts.py:95-129`,`:298-377`)。**反转补:append-only 知识库内核 + 远端合并去重 = ③b 公共;远端源选择/配置 = ③a。当前代码有默认 GitHub URL,也支持 `url` 参数 / `STUDIO_CATALOG_URL` 覆盖。**

**判据反转 + 6 态对齐(2026-06 第四轮)**:6 态标准总结 `state_projection` + draft/证据库 `import_drafts` 从"隐性 ③a 后端 SSOT/投影"反转为"③b 公共能力内核(待下沉)";`needs_setup` 取消并入 `failed`+reason、新增蓝态 `historical_ready`,正文从旧 5 态对齐到 canonical 6 态(消除与文末回填段的自相矛盾);权威源 ux-spec §4.2 + §6.0 + §6.4 + 归属表 `module-disposition-revised.md:50-51` + gateway 包 `README.md:64,74`。

## 附录 D — 代码索引 clues

- `apps/studio/backend/app/services/llm_state_projection.py:15`:`ProviderUiState` Literal 已是六态;旧 `needs_setup` 已被 `failed`+reason 替代。
- `apps/studio/backend/app/services/llm_state_projection.py:26-52`:6 态投影流程——**= ③b 公共内核(本轮反转,待下沉)**;当前已含 `draft_history` 入参。
- `apps/studio/backend/app/services/llm_state_projection.py:55-73`:`has_historical_probe_verified` / `_setup_reason`。
- `apps/studio/backend/app/services/llm_state_projection.py:76-116`:circuit 匹配/scope priority。
- `apps/studio/backend/app/routers/llm.py:488-600`:endpoint test 回写 active credentials 并追加模型列表观察 evidence(③a 壳 + ③b 写回内核)。
- `apps/studio/backend/app/routers/llm.py:609-807`:endpoint model test 写 route/profile probe evidence。
- `apps/studio/backend/app/routers/llm.py:810-846`:route probe 回写 verified/capabilities。
- `apps/studio/backend/app/routers/llm.py:899-972`:`probe_import_draft` 真实 worker,写 `probe_results`/evidence/circuit。
- `apps/studio/backend/app/routers/llm.py:2017-2095`:force route probe 回写 missing_key/success/circuit/failed。
- `apps/studio/backend/app/routers/llm.py:196-209`,`:4353-4401`:compact model status 六态(+`testing`)收口。
- `apps/studio/backend/app/services/llm_health_store.py:34-101`:runtime circuit 写入和读取——**熔断持久化内核 = ③b(待下沉);SQLite 路径 ③a 注入**。
- `apps/studio/backend/app/services/llm_role_materializer.py:48-90`:projection 影响 fallback_chain 物化(跳过 `failed`/`off`、`cooling_down` warning)——旧 `needs_setup` 已并入 `failed`。
- `apps/studio/backend/app/services/llm_import_drafts.py:55-128`:draft/evidence 创建、读取、追加——**知识库内核 = ③b 公共(待下沉)**。
- `apps/studio/backend/app/services/llm_import_drafts.py:137-203`:draft apply 到 active credentials——apply 工作流 ③a;route 默认态 schema ③b。
- `apps/studio/backend/app/services/llm_import_drafts.py:298-377`:remote evidence library merge——合并去重内核 ③b;远端源选择/配置 ③a(当前有默认 GitHub URL,并支持 `url` 参数 / `STUDIO_CATALOG_URL` 覆盖)。
- `apps/studio/frontend/src/api/llm.ts:12-13`,`:109-116`:前端 ProviderUiState / status summary 六态。
- `apps/studio/frontend/src/components/studio/api-keys/ProviderCard.tsx:348-378`:ProviderCard 以 `historical_ready` 状态渲染蓝色 Tag variant,不输出旧状态值。
- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:150-183`,`:258-264`:snapshot_version 透传与 stale live evidence 降级。

## 附录 E — 覆盖率

本 alignment 覆盖 08 brief 的全部要求:`services/llm_state_projection.py:project_provider_model_state`(6 态投影)+ `services/llm_import_drafts.py`(draft + 证据库)两个核心对象已落到真实 `file:line`,并补齐两处判据反转(6 态投影内核 = ③b、draft 知识库内核 = ③b)+ 6 态对齐(取消 needs_setup、补蓝态)。为说明"探测→持久化→投影→复用",额外引用 router、health store、role materializer 作为证据线索,均标注 ③a/③b 归属。
