---
module: 08-orch-test-status-ssot
doc: baseline
status: drafted
---

# 08-orch-test-status-ssot — Baseline(现状)

本文件只描述现状:后端已经有 endpoint/route 状态、runtime circuit、UI projection、import draft/evidence store,但“测试状态唯一事实源”仍有分散和易失的展示口径。

## 覆盖代码(含覆盖率)

覆盖率:brief 要求的 2 个核心对象已覆盖 2/2,为 100%。为解释探测到复用的完整链路,额外引用 router 与 health/materializer 代码作为 clues。

| 覆盖对象 | 现状职责 |
|---|---|
| `services/llm_state_projection.py:project_provider_model_state` | `project_provider_model_state` 把 endpoint/route 持久化状态和 runtime circuit 合成 Studio UI state(`apps/studio/backend/app/services/llm_state_projection.py:23-46`)。**判据归属:6 态标准总结(投影内核)= ③b 公共内核(本轮反转,原隐性 ③a 后端 SSOT);颜色渲染留前端 ③a。6 态对齐:现产旧 5 态含 `needs_setup`,MVP1 取消 `needs_setup`(并入 `failed`+reason)+ 补蓝态 `historical_ready`,详见 `mvp1-alignment.md` §2.2/§5。** |
| `services/llm_import_drafts.py` | `llm_import_drafts.py` 是 import draft 与 append-only evidence library 的文件存储模块,负责 draft 创建/读取/应用、probe evidence 追加、远端 evidence 同步(`apps/studio/backend/app/services/llm_import_drafts.py:1-20`,`:55-202`,`:297-376`)。**判据归属:draft + 证据库知识库内核 = ③b 公共内核(本轮反转,原隐性 ③a 隔离草稿/advisory store,待下沉 gateway);import/apply 工作流 + 远端源选择(GitHub repo 改可配置)+ 存储介质留 ③a。** |
| supporting clue | `SqliteLlmHealthStore` 是 runtime circuit 的 SQLite store;`materialize_role` 会复用 projection 跳过 needs_setup/off route,并把 cooling_down 写进 warning(`apps/studio/backend/app/services/llm_health_store.py:26-101`;`apps/studio/backend/app/services/llm_role_materializer.py:27-96`)。**判据归属:熔断持久化内核 = ③b(与 07 同一反转,待下沉;SQLite 路径 ③a 注入)。6 态对齐:materialize 跳过的 `needs_setup` 已并入 `failed`,改为跳过 `failed`/`off`。** |

## 现状逻辑

### 1. UI state projection 的判定顺序

> **判据 + 6 态对齐(本轮反转)**:本节描述的投影**内核 = ③b 公共**(待下沉 gateway),前端只渲染颜色。下文产的是**旧 5 态**(ready/untested/cooling_down/`needs_setup`/off);MVP1 对齐 canonical **6 态**——**取消 `needs_setup`**(并入 `failed🔴`+reason:`missing_config`/`endpoint_unreachable`/`model_failed`)、**新增 `historical_ready🔵`(以前联通过)**。目标 6 态 = `ready/historical_ready/untested/failed/cooling_down/off`,详见 `mvp1-alignment.md` §2.2。

1. `ProviderModelStateProjection` 是 UI 状态投影结果:它包含 `ui_state`、`reason_code`、`retry_at`、`ui_detail` 四个字段(`apps/studio/backend/app/services/llm_state_projection.py:15-20`)。
2. `project_provider_model_state` 是投影入口:它接收 endpoint、route、runtime circuits 和当前时间,输出 Studio UI state(`apps/studio/backend/app/services/llm_state_projection.py:23-29`)。
3. 第一步,disabled 优先:如果 endpoint 或 route 状态是 `disabled`,直接返回 `off`(`apps/studio/backend/app/services/llm_state_projection.py:30-32`)。
4. 第二步,setup 问题优先:如果 `_setup_reason` 返回原因,投影为 `needs_setup`(`apps/studio/backend/app/services/llm_state_projection.py:33-35`)。**6 态对齐:`needs_setup` 取消,MVP1 改产 `failed🔴` + reason(配置缺口=`missing_config`);`_setup_reason` 同步改产 failed+reason。**
5. `_setup_reason` 是 setup 缺口判断 helper:缺 API key 返回 `missing_key`,endpoint failed 返回 endpoint metadata 的 reason_code 或 `invalid_endpoint`,route failed 返回 route metadata 的 reason_code 或 `invalid_model`(`apps/studio/backend/app/services/llm_state_projection.py:49-56`)。
6. 第三步,circuit 冷却:如果 `_select_active_circuit` 找到未来才到期的 circuit,投影为 `cooling_down`,并带上 retry_at/message(`apps/studio/backend/app/services/llm_state_projection.py:36-43`)。
7. `_select_active_circuit` 是 active circuit 选择 helper:它只看 `retry_at > now` 且匹配当前 endpoint/route/bucket 的 circuit,再按 retry_at 和 scope priority 排序(`apps/studio/backend/app/services/llm_state_projection.py:59-78`)。
8. `_circuit_matches` 是 circuit 匹配 helper:route scope 匹配 route_id,endpoint scope 匹配 endpoint_id,rate_limit_bucket scope 匹配 endpoint.rate_limit_bucket 或 endpoint_id(`apps/studio/backend/app/services/llm_state_projection.py:81-91`)。
9. 第四步,ready:只有 endpoint.status 和 route.status 都是 `verified`,才返回 `ready`(`apps/studio/backend/app/services/llm_state_projection.py:44-45`)。
10. 默认,untested:其它情况返回 `untested`(`apps/studio/backend/app/services/llm_state_projection.py:46`)。**6 态对齐:MVP1 在 ready(第四步)与 untested 兜底之间插入 `historical_ready🔵`——endpoint verified + draft 有历史连通证据但当前无 live verified 时投影为蓝(投影需新增读 draft 历史证据入参)。**

### 2. 探测到持久化的现状链路

1. `test_endpoint` 是 endpoint 探测 API:它调用 provider 的 models-list 最小请求,根据结果写 endpoint.status、last_test_at、last_test_message,并保存 credentials(`apps/studio/backend/app/routers/llm.py:460-567`)。
2. `test_endpoint` 用 `endpoint_fingerprint` 防并发污染:测试开始和回写前 fingerprint 不一致时,它丢弃测试结果并写入“Endpoint changed...”消息(`apps/studio/backend/app/routers/llm.py:467-527`)。
3. `probe_route` 是 route 探测 API:非 force 模式把请求中的 capability/runtime_settings 标成 `probed_verified`,并把 route.status 写成 `verified`(`apps/studio/backend/app/routers/llm.py:782-818`)。
4. `_force_probe_route` 是真实 route 探测 helper:缺 key 时写 route failed/missing_key,成功时写 route verified 并清 circuit,网络/限流/超时类结果打开 route circuit 而不改 route status,其它失败写 route failed 和 reason metadata(`apps/studio/backend/app/routers/llm.py:1818-1886`)。
5. `SqliteLlmHealthStore.open_circuit` 是 runtime health 持久化入口:它把 route/endpoint/rate_limit_bucket scope 的 circuit upsert 到 SQLite(`apps/studio/backend/app/services/llm_health_store.py:26-62`)。
6. `SqliteLlmHealthStore.get_active_circuits` 是 circuit 读取入口:它按 route_id、endpoint_id、rate_limit_bucket 查 circuit,只返回 retry_at 仍在未来的记录(`apps/studio/backend/app/services/llm_health_store.py:70-101`)。

### 3. 投影到复用的现状链路

1. `_provider_model_ui_row` 是 registry UI row 构造 helper:它从 health store 取 active circuits,调用 `project_provider_model_state`,再把投影结果带进 provider model UI 数据(`apps/studio/backend/app/routers/llm.py:1708-1723`)。
2. `_provider_model_projection` 是 router 内部复用 helper:它同样从 health store 读取 circuits 并调用 `project_provider_model_state`(`apps/studio/backend/app/routers/llm.py:4270-4282`)。
3. `materialize_role` 是 role authoring 到 gateway fallback_chain 的物化函数:它对每个 provider model 取 projection,遇到 `needs_setup` 或 `off` 就跳过,遇到 `cooling_down` 就写 warning,只有 fit 的 route 才进入 fallback_chain(`apps/studio/backend/app/services/llm_role_materializer.py:27-96`)。
4. `llm_role_materializer._projection` 是 materializer 的投影 helper:它根据 route_id 找 route/endpoint,从 health store 取 active circuits,再调用 `project_provider_model_state`(`apps/studio/backend/app/services/llm_role_materializer.py:131-154`)。

### 4. draft + evidence library 的现状链路

> **判据(本轮反转)**:draft + append-only 证据库的**知识库内核**(记录/复用/共享探测证据、远端同步)= **③b 公共内核**(待下沉 gateway,gateway 包 `README.md:64` B 节);本节下文的 `apply_draft` 冲突处理工作流 + `sync_remote_evidence_library` 的**远端源选择**(现硬编码 GitHub repo,**应改可配置**)+ 存储介质(`_save_all` 写哪个目录)留 **③a**。`ProviderImportDraft`/`EvidenceRecord` 数据结构权威源已在 `registry/schema.py`(归 04)。

1. `ProviderImportDraft` 是非可信导入草稿:它保存 endpoint_candidates、route_candidates、probe_results、evidence_records、agent_notes 和 diff(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:369-386`)。
2. `EvidenceRecord` 是 append-only 证据记录:它保存 evidence_type、trust_state、scope、endpoint_id、route_id、model_id、probe_status、probe_attempts 等字段(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:332-366`)。
3. `create_draft` 是 draft 创建入口:它直接调用 `save_draft` 写入草稿 store(`apps/studio/backend/app/services/llm_import_drafts.py:55-62`)。
4. `load_draft` 是单 draft 读取入口:找不到 draft_id 时抛 `DraftNotFound`(`apps/studio/backend/app/services/llm_import_drafts.py:65-71`)。
5. `load_evidence_library` 是 durable evidence library 读取入口:找不到默认 `studio-evidence-library` 时返回一个空 library draft(`apps/studio/backend/app/services/llm_import_drafts.py:74-81`)。
6. `append_evidence_record` 是证据追加入口:它给 evidence 补 observed_at/attempted_at,合并 route_candidates,并把新 record 追加到 evidence_records 尾部,不替换旧证据(`apps/studio/backend/app/services/llm_import_drafts.py:94-128`)。
7. `apply_draft` 是 draft 应用入口:它把 endpoint_candidates 和 route_candidates 写入 active credentials,route 应用后状态固定为 `unverified_manual`,并把 draft.status 改成 `applied`(`apps/studio/backend/app/services/llm_import_drafts.py:136-202`)。
8. `_save_all` 是 draft/evidence store 原子写 helper:它写 `drafts` object,设置目录 `0700` 和文件 `0600`(`apps/studio/backend/app/services/llm_import_drafts.py:220-244`)。
9. `sync_remote_evidence_library` 是远端证据同步入口:它拉取远端 JSON,合并 route_candidates/capabilities/metadata,并按 evidence_id 去重追加远端 evidence(`apps/studio/backend/app/services/llm_import_drafts.py:297-376`)。

### 5. 前端易失态 / 展示状态分散的现状

1. active endpoint/route 状态是持久化的,但 compact model 展示可以从 evidence library 推导 `probe-verified`:当 route 还是 `unverified_manual` 且 evidence 有 `probe-verified`,UI model status 会显示为 `probe-verified`(`apps/studio/backend/app/routers/llm.py:4076-4106`)。**6 态对齐:这条"从历史证据推导可用"正是 MVP1 蓝态 `historical_ready🔵`(以前联通过)的来源——收口进 `project_provider_model_state` 第 6 态(读 draft 历史证据),不再是游离的展示标签。**
2. draft probe 当前不是实际 probe worker:`probe_import_draft` 只把 draft.status 改成 `probed`,注释也说明真实 agent probing 由后续 worker 处理(`apps/studio/backend/app/routers/llm.py:871-876`)。
3. evidence library 是 append-only advisory store,不是 active credentials 的状态字段;`append_evidence_record` 追加证据但不回写 route.status(`apps/studio/backend/app/services/llm_import_drafts.py:94-128`)。
4. 因此 baseline 下 UI 看到的“ready/untested/cooling_down/needs_setup”主要来自后端 projection,但“probe-verified”这类展示增强还可能来自 evidence library,不是 active route SSOT(`apps/studio/backend/app/services/llm_state_projection.py:23-46`;`apps/studio/backend/app/routers/llm.py:4093-4106`)。**6 态对齐:此处的旧 5 态(含 `needs_setup`)→ MVP1 取消 `needs_setup`(并入 `failed`);游离的 `probe-verified` 展示 → 收口为 projection 第 6 态蓝 `historical_ready`。两改后 UI 状态全部来自 6 态投影 SSOT(投影内核 = ③b),前端只渲染颜色。**

## Baseline / Alignment 差异

1. baseline 已经有后端 projection 函数,但它只是把多个事实源投影给 UI;alignment 要求 probe/test 结果统一回写后端 SSOT,再由 UI 只读投影(`apps/studio/backend/app/services/llm_state_projection.py:23-46`)。
2. baseline 的 endpoint/route probe 会写 active credentials,但 evidence library 的 `probe-verified` 可作为展示状态存在,没有强制同步为 active route.status(`apps/studio/backend/app/routers/llm.py:782-818`,`:4076-4106`)。
3. baseline 的 import draft 是隔离草稿:apply 后 route 状态仍是 `unverified_manual`,说明 draft evidence 不等于 runtime-ready 事实(`apps/studio/backend/app/services/llm_import_drafts.py:182-194`)。
4. alignment 需要明确“探测→持久化→投影→复用”的唯一写回路径:probe 成功/失败/cooling_down 都应写入 active backend store 或 health store,UI 不自行持有易失判断。

## 决策原因

1. UI state 必须后端投影,原因是 ready/needs_setup/cooling_down 需要同时看 endpoint、route、secret、runtime circuit;这些数据前端不应自己拼(`apps/studio/backend/app/services/llm_state_projection.py:23-56`)。**判据(本轮反转):此"投影"的内核 = ③b 公共能力(可下沉 gateway 包),"必须后端"只是相对前端的 SSOT 表述,与下沉到 ③b 不矛盾;前端只渲染颜色。6 态对齐:`needs_setup` 取消并入 `failed`。**
2. runtime circuit 单独持久化,原因是限流/网络冷却不等于 route 永久 failed;`_force_probe_route` 对 timeout/rate_limited/network_error 打开 circuit,但返回原 route,就是这个语义(`apps/studio/backend/app/routers/llm.py:1858-1873`)。
3. draft 必须隔离,原因是 import draft 来自非可信 Agent/onboarding 输入;`apply_draft` 需要显式处理 endpoint collisions,且 route 应用后仍是 `unverified_manual`(`apps/studio/backend/app/services/llm_import_drafts.py:136-202`)。
4. evidence library 适合作为建议材料,原因是它是 append-only 并可远端同步,但不应替代 active credentials 的可执行状态(`apps/studio/backend/app/services/llm_import_drafts.py:94-128`,`:297-376`)。**判据(本轮反转):append-only 知识库内核 + 远端合并去重 = ③b 公共能力(待下沉 gateway);远端源选择(GitHub repo 改可配置)+ 存储介质 = ③a。"建议材料、不替代可执行状态"的语义不变——蓝态(历史/建议)真探通才升绿(active verified)。**

## 代码索引 clues

- `apps/studio/backend/app/services/llm_state_projection.py:23-46`: UI state 判定顺序。**判据:6 态投影内核 = ③b 公共(本轮反转,待下沉);6 态对齐取消 needs_setup、补蓝态。**
- `apps/studio/backend/app/services/llm_state_projection.py:49-99`: setup reason、circuit 匹配、scope priority。**`_setup_reason` 改产 `failed`+reason(非 needs_setup)。**
- `apps/studio/backend/app/routers/llm.py:460-567`: endpoint test 写回 endpoint status。
- `apps/studio/backend/app/routers/llm.py:782-818`: route probe 写回 route verified/capabilities。
- `apps/studio/backend/app/routers/llm.py:1818-1886`: force route probe 的 success/failed/cooling_down 写法。
- `apps/studio/backend/app/services/llm_health_store.py:26-101`: runtime circuit SQLite store。**判据:熔断持久化内核 = ③b(与 07 同一反转,待下沉);SQLite 路径 ③a 注入。**
- `apps/studio/backend/app/services/llm_role_materializer.py:27-96`: projection 被 fallback_chain 物化复用。**6 态对齐:跳过 `needs_setup` → 跳过 `failed`(已并入)。**
- `apps/studio/backend/app/services/llm_import_drafts.py:55-202`: draft 创建/读取/应用。**判据:知识库内核 = ③b 公共(本轮反转,待下沉);apply 工作流 + 存储介质 ③a。**
- `apps/studio/backend/app/services/llm_import_drafts.py:94-128`: evidence append-only 追加。**判据:= ③b 知识库内核。**
- `apps/studio/backend/app/routers/llm.py:4076-4106`: compact model status 可由 evidence library 推导 `probe-verified`。**6 态对齐:收口为投影第 6 态蓝 `historical_ready`。**

## 待办/疑点

1. 待办:明确 `probe-verified` 是 UI 展示标签还是 active route status;当前 compact model 会从 evidence 推导它,但 `project_provider_model_state` 的 state 集合没有 `probe-verified`(`apps/studio/backend/app/services/llm_state_projection.py:12`;`apps/studio/backend/app/routers/llm.py:4093-4106`)。**已定调(6 态对齐):收口为投影第 6 态蓝 `historical_ready🔵`(以前联通过,历史/建议态)——`ProviderUiState` Literal 加 `historical_ready`,投影读 draft 历史证据(`EvidenceRecord.trust_state`)产蓝;蓝真探通才升 `ready🟢`。详见 `mvp1-alignment.md` §2.2/§8。**
2. 待办:把 import draft probe 从“标记 probed”升级为真实 worker 或明确保留为占位;当前 `probe_import_draft` 没有实际探测逻辑(`apps/studio/backend/app/routers/llm.py:871-876`)。
3. 待办:约束 evidence library 如何回写 active credentials;当前 `append_evidence_record` 不替换旧证据,也不更新 route.status(`apps/studio/backend/app/services/llm_import_drafts.py:94-128`)。
4. 疑点:`_select_active_circuit` 对 relevant circuits 用 `-retry_at.timestamp()` 排序会优先选更晚到期的 circuit,是否符合“最近/最具体失败”的展示预期需要产品确认(`apps/studio/backend/app/services/llm_state_projection.py:72-78`)。
