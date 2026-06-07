---
module: 08-orch-test-status-ssot
doc: baseline
status: drafted
binds_design: ./mvp1-alignment.md
binds_code: apps/studio/backend/app/services/llm_state_projection.py:ProviderUiState/ProviderModelStateProjection/project_provider_model_state/has_historical_probe_verified/_setup_reason/_select_active_circuit · apps/studio/backend/app/services/llm_import_drafts.py:create_draft/load_draft/load_evidence_library/append_evidence_record/apply_draft/sync_remote_evidence_library/DraftNotFound/DraftExpired/DraftApplyConflict/DEFAULT_CATALOG_URL · packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:EvidenceRecord/ProviderImportDraft/ProbeResult
units: [test-status-ssot-evidence]
aligns_with: ../README.md · ../DESIGN_UNITS_INDEX.md
---

# 08-orch-test-status-ssot — Baseline(现状)

本文件只描述现状:后端已经有 endpoint/route 状态、runtime circuit、6 态 UI projection、import draft/evidence store 和真实 draft probe worker。当前代码已把 provider model 主投影改为 `ready/historical_ready/untested/failed/cooling_down/off` 六态,把 draft 历史证据接入 registry/materializer 投影,把 compact model status 收口到六态(+`testing`),前端类型与 ProviderCard/LLM Roles 展示也已同步六态；registry resolver 已接入版本-stale 的 live evidence 降级。真实尾债是:`state_projection` / `import_drafts` 内核仍在 Studio 后端、尚未下沉 gateway 公共包；evidence library 如何回写 active credentials 的规则仍待明确；`snapshot_version` 填充仍由 loader/materializer/host 侧负责。

## 覆盖代码(含覆盖率)

覆盖率:brief 要求的 2 个核心对象已覆盖 2/2,为 100%。为解释探测到复用的完整链路,额外引用 router 与 health/materializer 代码作为 clues。

| 覆盖对象 | 现状职责 |
|---|---|
| `services/llm_state_projection.py:project_provider_model_state` | `project_provider_model_state` 把 endpoint/route 持久化状态、runtime circuit 和已加载的 draft 历史证据布尔量合成 Studio UI state(`apps/studio/backend/app/services/llm_state_projection.py:15-52`)。**判据归属:6 态标准总结(投影内核)= ③b 公共内核(本轮反转,原隐性 ③a 后端 SSOT);颜色渲染留前端 ③a。当前已落地六态 `ready/historical_ready/untested/failed/cooling_down/off`:旧 `needs_setup` 已取消并入 `failed`+reason,蓝态 `historical_ready` 已由 `draft_history` 驱动。** |
| `services/llm_import_drafts.py` | `llm_import_drafts.py` 是 import draft 与 append-only evidence library 的文件存储模块,负责 draft 创建/读取/应用、probe evidence 追加、远端 evidence 同步(`apps/studio/backend/app/services/llm_import_drafts.py:1-20`,`:56-203`,`:298-377`)。**判据归属:draft + 证据库知识库内核 = ③b 公共内核(本轮反转,原隐性 ③a 隔离草稿/advisory store,待下沉 gateway);import/apply 工作流 + 远端源选择/配置 + 存储介质留 ③a。当前远端源有 `DEFAULT_CATALOG_URL` 默认 GitHub URL,并可通过 `url` 参数或 `STUDIO_CATALOG_URL` 覆盖。** |
| supporting clue | `SqliteLlmHealthStore` 是 runtime circuit 的 SQLite store;`materialize_role` 会复用 projection 跳过 `failed`/`off` route,并把 cooling_down 写进 warning(`apps/studio/backend/app/services/llm_health_store.py:26-101`;`apps/studio/backend/app/services/llm_role_materializer.py:35-170`)。**判据归属:熔断持久化内核 = ③b(与 07 同一反转,待下沉;SQLite 路径 ③a 注入)。** |

## 现状逻辑

### 1. UI state projection 的判定顺序

> **判据 + 6 态对齐(本轮反转)**:本节描述的投影**内核 = ③b 公共**(待下沉 gateway),前端只渲染颜色。WS-3 后端已落地 canonical **6 态**:`ready/historical_ready/untested/failed/cooling_down/off`。`needs_setup` 已取消并入 `failed🔴`+reason:`missing_config`/`endpoint_unreachable`/`model_failed`;`historical_ready🔵` 表示 endpoint 已验证且该 route 有 probe-verified 历史证据,但当前 route 还没有 live verified。

1. `ProviderUiState` 是六态 Literal:`ready`、`historical_ready`、`untested`、`failed`、`cooling_down`、`off`(`apps/studio/backend/app/services/llm_state_projection.py:15`)。
2. `ProviderModelStateProjection` 是 UI 状态投影结果:它包含 `ui_state`、`reason_code`、`retry_at`、`ui_detail` 四个字段(`apps/studio/backend/app/services/llm_state_projection.py:18-23`)。
3. `project_provider_model_state` 是投影入口:它接收 endpoint、route、runtime circuits、当前时间和 `draft_history` 布尔量,输出 Studio UI state(`apps/studio/backend/app/services/llm_state_projection.py:26-52`)。
4. 第一步,disabled 优先:如果 endpoint 或 route 状态是 `disabled`,直接返回 `off`(`apps/studio/backend/app/services/llm_state_projection.py:35-36`)。
5. 第二步,failed 优先:如果 `_setup_reason` 返回原因,投影为 `failed` 并带 reason_code(`apps/studio/backend/app/services/llm_state_projection.py:37-39`)。
6. `_setup_reason` 是失败原因收敛 helper:缺 API key 返回 `missing_config`,endpoint failed 返回 `endpoint_unreachable`,route failed 返回 `model_failed`(`apps/studio/backend/app/services/llm_state_projection.py:66-73`)。
7. 第三步,circuit 冷却:如果 `_select_active_circuit` 找到未来才到期的 circuit,投影为 `cooling_down`,并带上 retry_at/message(`apps/studio/backend/app/services/llm_state_projection.py:40-47`)。
8. `_select_active_circuit` 是 active circuit 选择 helper:它只看 `retry_at > now` 且匹配当前 endpoint/route/bucket 的 circuit,再按 retry_at 和 scope priority 排序(`apps/studio/backend/app/services/llm_state_projection.py:76-95`)。
9. `_circuit_matches` 是 circuit 匹配 helper:route scope 匹配 route_id,endpoint scope 匹配 endpoint_id,rate_limit_bucket scope 匹配 endpoint.rate_limit_bucket 或 endpoint_id(`apps/studio/backend/app/services/llm_state_projection.py:98-108`)。
10. 第四步,ready:只有 endpoint.status 和 route.status 都是 `verified`,才返回 `ready`(`apps/studio/backend/app/services/llm_state_projection.py:48-49`)。
11. 第五步,historical_ready:如果 endpoint.status 是 `verified`、`draft_history` 为真且 route.status 不是 `verified`,返回 `historical_ready`(`apps/studio/backend/app/services/llm_state_projection.py:50-51`)。
12. 默认,untested:其它情况返回 `untested`(`apps/studio/backend/app/services/llm_state_projection.py:52`)。
13. `has_historical_probe_verified` 是纯 helper:输入已加载的 `EvidenceRecord` 列表和 route_id,只在 `trust_state == "probe-verified"` 且 `record.route_id` 或 `record.scope["route_id"]` 匹配时返回真(`apps/studio/backend/app/services/llm_state_projection.py:55-63`)。

### 2. 探测到持久化的现状链路

1. `test_endpoint` 是 endpoint 探测 API:它调用 provider 的 models-list 最小请求,根据结果写 endpoint.status、last_test_at、last_test_message,保存 credentials,并把模型列表观察写进 evidence library(`apps/studio/backend/app/routers/llm.py:488-600`)。
2. `test_endpoint` 用 `endpoint_fingerprint` 防并发污染:测试开始和回写前 fingerprint 不一致时,它丢弃测试结果并写入“Endpoint changed...”消息(`apps/studio/backend/app/routers/llm.py:495-560`)。
3. `test_endpoint_models` 是按模型 ID 探测的入口:官方 provider 会写 profile probe evidence,third-party/custom probe 会写 model probe evidence;成功时 upsert verified route,失败时也保留 probe evidence(`apps/studio/backend/app/routers/llm.py:609-807`,`:2605-2745`)。
4. `probe_route` 是 route 探测 API:非 force 模式把请求中的 capability/runtime_settings 标成 `probed_verified`,并把 route.status 写成 `verified`(`apps/studio/backend/app/routers/llm.py:810-846`)。
5. `_force_probe_route` 是真实 route 探测 helper:缺 key 时写 route failed/missing_key,成功时写 route verified 并清 circuit,网络/限流/超时类结果打开 route circuit 而不改 route status,其它失败写 route failed 和 reason metadata(`apps/studio/backend/app/routers/llm.py:2017-2076`)。
6. `probe_import_draft` 是真实 draft probe worker:它把 draft 标为 `probing`,逐个 route candidate 调 `_probe_model`,写入 `probe_results`,通过 `_append_model_probe_evidence` 追加成功/失败 evidence,并对 transient failure 打开 route circuit(`apps/studio/backend/app/routers/llm.py:899-972`)。
7. `SqliteLlmHealthStore.open_circuit` 是 runtime health 持久化入口:它把 route/endpoint/rate_limit_bucket scope 的 circuit upsert 到 SQLite(`apps/studio/backend/app/services/llm_health_store.py:26-62`)。
8. `SqliteLlmHealthStore.get_active_circuits` 是 circuit 读取入口:它按 route_id、endpoint_id、rate_limit_bucket 查 circuit,只返回 retry_at 仍在未来的记录(`apps/studio/backend/app/services/llm_health_store.py:70-101`)。

### 3. 投影到复用的现状链路

1. `_model_groups_response` 是 registry model group 构造入口:它读取 evidence library 一次,把 `evidence_records` 传给每个 group 的 provider model 投影消费点(`apps/studio/backend/app/routers/llm.py:1633-1650`)。
2. `_provider_model_option` 是 registry provider model row 构造 helper:它从 health store 取 active circuits,用 `has_historical_probe_verified` 计算 `draft_history`,调用 `project_provider_model_state`,再把六态投影结果带进 provider model UI 数据(`apps/studio/backend/app/routers/llm.py:1862-1907`)。
3. `_model_group_response` 的 `status_summary` 已是六态键集合:`ready/historical_ready/untested/failed/cooling_down/off`,避免新态出现时 KeyError(`apps/studio/backend/app/routers/llm.py:1763-1787`)。
4. `_provider_model_projection` 是 router 内部复用 helper:它同样从 health store 读取 circuits,从 evidence library 算 `draft_history`,再调用 `project_provider_model_state`(`apps/studio/backend/app/routers/llm.py:4575-4598`)。
5. `_admission_decision` 对 `cooling_down` 返回 `temporary_skip`,对 `failed`/`off` 返回 `block`,其它状态返回 `admit`(`apps/studio/backend/app/routers/llm.py:4600-4605`)。
6. `materialize_role` 是 role authoring 到 gateway fallback_chain 的物化函数:它复用投影,遇到 `failed` 或 `off` 就跳过,遇到 `cooling_down` 就写 warning,只有 fit 的 route 才进入 fallback_chain(`apps/studio/backend/app/services/llm_role_materializer.py:35-107`)。
7. `llm_role_materializer._projection` 是 materializer 的投影 helper:它根据 route_id 找 route/endpoint,从 health store 取 active circuits,用已加载 evidence records 算 `draft_history`,再调用 `project_provider_model_state`(`apps/studio/backend/app/services/llm_role_materializer.py:142-170`)。

### 4. draft + evidence library 的现状链路

> **判据(本轮反转)**:draft + append-only 证据库的**知识库内核**(记录/复用/共享探测证据、远端同步)= **③b 公共内核**(待下沉 gateway,gateway 包 `README.md:64` B 节);本节下文的 `apply_draft` 冲突处理工作流 + `sync_remote_evidence_library` 的**远端源选择/配置**(当前有 `DEFAULT_CATALOG_URL` 默认 GitHub URL,并支持 `url` 参数或 `STUDIO_CATALOG_URL` 覆盖)+ 存储介质(`_save_all` 写哪个目录)留 **③a**。`ProviderImportDraft`/`EvidenceRecord` 数据结构权威源已在 `registry/schema.py`(归 04)。

1. `ProviderImportDraft` 是非可信导入草稿:它保存 endpoint_candidates、route_candidates、probe_results、evidence_records、agent_notes 和 diff(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:369-386`)。
2. `EvidenceRecord` 是 append-only 证据记录:它保存 evidence_type、trust_state、scope、endpoint_id、route_id、model_id、probe_status、probe_attempts 等字段(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:332-366`)。
3. `create_draft` 是 draft 创建入口:它直接调用 `save_draft` 写入草稿 store(`apps/studio/backend/app/services/llm_import_drafts.py:55-62`)。
4. `load_draft` 是单 draft 读取入口:找不到 draft_id 时抛 `DraftNotFound`(`apps/studio/backend/app/services/llm_import_drafts.py:65-71`)。
5. `load_evidence_library` 是 durable evidence library 读取入口:找不到默认 `studio-evidence-library` 时返回一个空 library draft(`apps/studio/backend/app/services/llm_import_drafts.py:74-81`)。
6. `append_evidence_record` 是证据追加入口:它给 evidence 补 observed_at/attempted_at,合并 route_candidates,并把新 record 追加到 evidence_records 尾部,不替换旧证据(`apps/studio/backend/app/services/llm_import_drafts.py:95-129`)。
7. `apply_draft` 是 draft 应用入口:它把 endpoint_candidates 和 route_candidates 写入 active credentials,route 应用后状态固定为 `unverified_manual`,并把 draft.status 改成 `applied`(`apps/studio/backend/app/services/llm_import_drafts.py:137-203`)。
8. `_save_all` 是 draft/evidence store 原子写 helper:它写 `drafts` object,设置目录 `0700` 和文件 `0600`(`apps/studio/backend/app/services/llm_import_drafts.py:220-244`)。
9. `sync_remote_evidence_library` 是远端证据同步入口:它拉取远端 JSON,合并 route_candidates/capabilities/metadata,并按 evidence_id 去重追加远端 evidence(`apps/studio/backend/app/services/llm_import_drafts.py:298-377`)。

### 5. compact status 与前端展示的现状

1. provider model 主投影已经从 evidence library 的 `probe-verified` 历史证据推出 `historical_ready`:endpoint verified + route 非 verified + matching `probe-verified` evidence → 蓝态;route live verified 时仍升 `ready`(`apps/studio/backend/app/services/llm_state_projection.py:48-52`,`:55-63`)。
2. compact endpoint test DTO 的 `status` Literal 已收口为六态加 `testing`,不再把 `probe-verified` 当作 status 输出(`apps/studio/backend/app/routers/llm.py:196-209`)。
3. `_compact_model_info_for_listed_official_route` 对已有 route 调 `_provider_model_projection(...).ui_state`,所以 compact model status 与 provider model projection 使用同一六态口径;active job 只在进行中的模型上临时写 `testing`(`apps/studio/backend/app/routers/llm.py:4353-4401`,`:4428-4450`)。
4. 前端 API 类型已同步六态:`ProviderUiState` 和 `ModelGroupStatusSummary` 都是 `ready/historical_ready/untested/failed/cooling_down/off`(`apps/studio/frontend/src/api/llm.ts:12-13`,`:109-116`)。
5. API Keys `ProviderCard` 把 `historical_ready` 渲染成蓝色 `Tag variant="probe-verified"`,但数据状态仍是 `historical_ready`,不会把 `probe-verified` 暴露成 route status(`apps/studio/frontend/src/components/studio/api-keys/ProviderCard.tsx:348-378`;`apps/studio/frontend/src/components/studio/api-keys/ProviderCard.test.tsx:752-780`)。
6. LLM Roles 的 Available Models sidebar 和 provider badge 已消费六态,按 Ready / Previously Connected / Untested / Cooling Down / Failed / Off 排序和渲染(`apps/studio/frontend/src/components/studio/settings/llm-roles/AvailableModelsSidebar.tsx:511-540`;`apps/studio/frontend/src/components/studio/settings/llm-roles/provider-state-badge.tsx:15-59`)。
7. evidence library 仍是 append-only advisory store,不是 active credentials 的状态字段;`append_evidence_record` 追加证据但不直接更新 route.status(`apps/studio/backend/app/services/llm_import_drafts.py:95-129`)。

### 6. snapshot_version 与版本-stale 的现状

1. `snapshot_version` 字段已在 `ProviderRoute`、`RegistrySnapshot`、`ResolvedRoute` schema 上存在(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:207-221`,`:404-414`,`:417-442`)。
2. registry resolver 会把当前 `snapshot.snapshot_version` 传给 `ResolvedRoute`,并在 route.snapshot_version 与 snapshot 不一致时剥离 stale capabilities / verified_profiles,避免旧 verified profile 被当成 live ready(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:150-183`,`:258-264`)。
3. resolver 测试已覆盖 snapshot_version 透传和版本不一致时不再选中旧 profile(`packages/graph-agent-gateway/tests/test_registry_resolver.py:98-184`)。
4. Studio 当前 `RolesData.to_registry_snapshot(credentials)` 只把 credentials/roles join 成 snapshot,不填 `snapshot_version`;因此版本填充仍是 loader/materializer/host 侧责任,不是 08 投影函数内部自动生成(`apps/studio/backend/app/models/llm_config.py:279-296`;`apps/studio/backend/app/services/gateway_resolver.py:15-21`)。

## Baseline / Alignment 差异

1. baseline 已经有后端六态 projection 函数,并且 registry/materializer 已复用同一投影口径;alignment 的“后端投影为 SSOT、前端只渲染”在 provider model 主状态上已落地(`apps/studio/backend/app/services/llm_state_projection.py:15-73`;`apps/studio/backend/app/routers/llm.py:1633-1650`,`:1862-1907`,`:4575-4605`;`apps/studio/backend/app/services/llm_role_materializer.py:35-170`)。
2. compact model status 已改为同一六态 projection(+`testing`)输出;旧的 `probe-verified` 作为状态值的事实已被替代,现在只作为前端蓝色 Tag variant 名称存在(`apps/studio/backend/app/routers/llm.py:196-209`,`:4353-4401`;`apps/studio/frontend/src/components/studio/api-keys/ProviderCard.tsx:359-378`)。
3. import draft probe 已是真实 worker,会写 `probe_results`、append probe evidence,并对 transient failure 打开 cooling_down circuit(`apps/studio/backend/app/routers/llm.py:899-972`)。
4. baseline 的 import draft 仍是隔离草稿:apply 后 route 状态仍是 `unverified_manual`,说明 draft evidence 不等于 runtime-ready 事实(`apps/studio/backend/app/services/llm_import_drafts.py:183-203`)。
5. alignment 的剩余差异/尾债集中在归属和规则:6 态投影内核与 draft/evidence 知识库仍在 Studio 后端待下沉 gateway 公共包；evidence library 何时、如何回写 active credentials 仍需规则化；`snapshot_version` 填充由 loader/materializer/host 侧负责。

## 决策原因

1. UI state 必须后端投影,原因是 ready/failed/cooling_down/historical_ready 需要同时看 endpoint、route、secret、runtime circuit 和历史证据;这些数据前端不应自己拼(`apps/studio/backend/app/services/llm_state_projection.py:15-73`)。**判据(本轮反转):此"投影"的内核 = ③b 公共能力(可下沉 gateway 包),"必须后端"只是相对前端的 SSOT 表述,与下沉到 ③b 不矛盾;前端只渲染颜色。**
2. runtime circuit 单独持久化,原因是限流/网络冷却不等于 route 永久 failed;`_force_probe_route` 对 timeout/rate_limited/network_error 打开 circuit,但返回原 route,就是这个语义(`apps/studio/backend/app/routers/llm.py:2057-2063`)。
3. draft 必须隔离,原因是 import draft 来自非可信 Agent/onboarding 输入;`apply_draft` 需要显式处理 endpoint collisions,且 route 应用后仍是 `unverified_manual`(`apps/studio/backend/app/services/llm_import_drafts.py:137-203`)。
4. evidence library 适合作为建议材料,原因是它是 append-only 并可远端同步,但不应替代 active credentials 的可执行状态(`apps/studio/backend/app/services/llm_import_drafts.py:95-129`,`:298-377`)。**判据(本轮反转):append-only 知识库内核 + 远端合并去重 = ③b 公共能力(待下沉 gateway);远端源选择/配置 + 存储介质 = ③a。当前远端同步有默认 GitHub URL,也可通过 `url` 参数或 `STUDIO_CATALOG_URL` 覆盖。"建议材料、不替代可执行状态"的语义不变——蓝态(历史/建议)真探通才升绿(active verified)。**

## 代码索引 clues

- `apps/studio/backend/app/services/llm_state_projection.py:15-73`: 六态 UI state Literal、投影判定顺序、`has_historical_probe_verified`、failed reason 收敛。**判据:6 态投影内核 = ③b 公共(本轮反转,待下沉)。**
- `apps/studio/backend/app/services/llm_state_projection.py:76-116`: circuit 匹配、scope priority。
- `apps/studio/backend/app/routers/llm.py:488-600`: endpoint test 写回 endpoint status 并追加模型列表观察 evidence。
- `apps/studio/backend/app/routers/llm.py:609-807`: endpoint model test 写 route/profile probe evidence。
- `apps/studio/backend/app/routers/llm.py:810-846`: route probe 写回 route verified/capabilities。
- `apps/studio/backend/app/routers/llm.py:899-972`: import draft probe worker 写 `probe_results`、append evidence,transient failure 打开 circuit。
- `apps/studio/backend/app/routers/llm.py:2017-2095`: force route probe 的 success/failed/cooling_down 写法。
- `apps/studio/backend/app/services/llm_health_store.py:26-101`: runtime circuit SQLite store。**判据:熔断持久化内核 = ③b(与 07 同一反转,待下沉);SQLite 路径 ③a 注入。**
- `apps/studio/backend/app/services/llm_role_materializer.py:35-170`: projection 被 fallback_chain 物化复用;materializer 读取 evidence library 算 `draft_history`,跳过 `failed`/`off`,保留 `cooling_down` warning。
- `apps/studio/backend/app/services/llm_import_drafts.py:55-202`: draft 创建/读取/应用。**判据:知识库内核 = ③b 公共(本轮反转,待下沉);apply 工作流 + 存储介质 ③a。**
- `apps/studio/backend/app/services/llm_import_drafts.py:95-129`: evidence append-only 追加。**判据:= ③b 知识库内核。**
- `apps/studio/backend/app/routers/llm.py:1633-1650`: registry model group 读取 evidence library 一次,provider model 投影消费六态。
- `apps/studio/backend/app/routers/llm.py:1763-1787`: `status_summary` 暴露六态 key。
- `apps/studio/backend/app/routers/llm.py:1862-1907`: provider model option 用 `has_historical_probe_verified` 算 `draft_history` 后调用六态投影。
- `apps/studio/backend/app/routers/llm.py:196-209`,`:4353-4401`: compact model status 使用六态 projection(+`testing`)。
- `apps/studio/backend/app/routers/llm.py:4575-4605`: router 内部 projection helper 和 admission decision 适配六态;`failed`/`off` block,`cooling_down` temporary skip。
- `apps/studio/frontend/src/api/llm.ts:12-13`,`:109-116`: 前端类型同步六态。
- `apps/studio/frontend/src/components/studio/api-keys/ProviderCard.tsx:348-378`: ProviderCard 把 `historical_ready` 渲染成蓝色 Tag variant,不输出旧状态值。
- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:150-183`,`:258-264`: snapshot_version 透传与 stale live evidence 降级。

## 待办/疑点

1. 待办:6 态投影内核、draft/evidence 知识库内核仍在 Studio 后端,尚未下沉到 gateway 公共包(`apps/studio/backend/app/services/llm_state_projection.py`;`apps/studio/backend/app/services/llm_import_drafts.py`)。
2. 待办:约束 evidence library 如何回写 active credentials;当前 `append_evidence_record` 不替换旧证据,也不直接更新 route.status(`apps/studio/backend/app/services/llm_import_drafts.py:95-129`)。
3. 待办:`snapshot_version` 填充仍由 loader/materializer/host 侧负责;schema/resolver 已支持,但 Studio `RolesData.to_registry_snapshot` 当前不填该字段(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:207-221`,`:404-442`;`apps/studio/backend/app/models/llm_config.py:279-296`)。
4. 疑点:`_select_active_circuit` 对 relevant circuits 用 `-retry_at.timestamp()` 排序会优先选更晚到期的 circuit,是否符合“最近/最具体失败”的展示预期需要产品确认(`apps/studio/backend/app/services/llm_state_projection.py:89-95`)。
