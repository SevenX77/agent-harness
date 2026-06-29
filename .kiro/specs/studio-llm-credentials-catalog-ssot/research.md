# Research — Studio LLM credentials/catalog SSOT 重构

> 短篇审计记录。目的:在动手前查清现有真实链路、点出"坏链路"的精确证据,
> 说明为什么把 `llm_probe_catalog.json` 与 `community_catalog_cache.json`
> 从运行期 truth 降级/移除。本文件只记录"现状与原因",契约见 `requirements.md`,
> 落地见 `design.md`。

## 1. 一句话结论

Studio 想让 `llm_credentials.json` 成为 UI 唯一运行期真相源,但**当前 evidence 本体
根本不在 credentials 里**:credentials 只在 `route.metadata["evidence_refs"]` 存了一串
evidence_id 字符串,而 evidence 本体(`EvidenceRecord`)散落在 `llm_probe_catalog.json`
和 `community_catalog_cache.json` 两个外部文件里,再由 Test 流程"promote"回 credentials。
这套"本体在外、引用在内、Test 时回填"的链路就是要拆掉的对象。

## 2. 三个运行态文件现状角色

运行态路径(`app/services/llm_paths.py`,根目录 `APP_SETTINGS_DIR/llm/`):

| 文件 | 当前角色 | 期望角色 |
| --- | --- | --- |
| `llm_credentials.json` | credentials + route runtime status 的 SSOT;但 evidence 只有 refs,无本体 | **唯一运行期真相源**:credentials + route status + evidence 本体 |
| `llm_probe_catalog.json` | 本地 probe/model-list evidence 本体存储(gateway `ProviderImportDraft`);Test 写它,上传读它 | 仅 migration/import 来源,正常 Test/sync 不再写;迁移后可删 |
| `community_catalog_cache.json` | 远端 verified community catalog 的"一次性 cache",但 Test 又从它 promote 进 credentials,事实上参与了 truth | 不再存在;远端 verified evidence 验签后直接 merge 进 credentials |

## 3. 坏链路的精确证据(file:line)

### 3.1 community cache → credentials 的 promote(最该删)
- `app/routers/llm.py:920` — `test_endpoint` 成功后调用 `_apply_cached_community_evidence(latest_credentials)`。
- `app/routers/llm.py:2161-2165` — 该函数从 `DisposableCatalogCacheStore(community_catalog_cache_path()).load()` 读 cache records,再 `apply_community_evidence_to_credentials`。
- `app/services/community_catalog.py:249-306` — 按 `(endpoint_host, provider_model_id)` 匹配 route,把 community evidence_id append 进 `route.metadata["evidence_refs"]`(line 298)并打 `community_evidence: True`(line 303)。
- 运行态证据:日志 `endpoint_test source_id=llm_credentials message="...applied matching cached community evidence." changes 含 promoted_catalog_records`;现象为"local catalog 没有,credentials 却凭空多出 evidence"。

### 3.2 probe/model-list evidence 写 llm_probe_catalog.json
- `app/routers/llm.py:815-820` — `_append_model_list_observation_evidence`(model-list 观察)。
- `app/routers/llm.py:867-874` / `1175-1180` — `_append_model_probe_evidence`(probe 结果)。
- `app/routers/llm.py:1053-1058` — `_append_official_profile_probe_evidence`(official profile)。
- 这些最终走 gateway `append_evidence_record` 写入 `llm_probe_catalog.json`(`ProviderImportDraft.evidence_records`)。

### 3.3 远端 verified catalog → community_catalog_cache.json
- `app/services/community_catalog_runtime.py:20-83` — `sync_verified_community_catalog_cache(trigger=...)`:拉远端 manifest+shard、Ed25519 验签、SHA256 校验分片,写 `community_catalog_cache.json`(`CommunityCatalogCache`:`manifest_etag/generated_at/protocol_major/records`)。
- `app/services/community_catalog_sync.py:64-72`(模型)/`152-177`(`DisposableCatalogCacheStore` 读写)。
- `app/main.py:86-90` startup `_sync_verified_community_catalog_on_startup` + `app/main.py:76-83` `_sync_remote_probe_catalog_on_startup`(旧 remote probe catalog → `llm_probe_catalog.json`)。两套 catalog 概念在启动时并存。

### 3.4 上传候选来源是 probe catalog,不是 credentials
- `app/routers/llm.py:192` / `663` — `collect_uploadable_uploads(load_evidence_library(), load_credentials())`:**主输入是 evidence library(probe catalog)**,credentials 只用来查 endpoint base_url 做脱敏。
- `app/services/community_catalog_upload.py:48-67` — 遍历 `library.evidence_records`,筛 `is_uploadable`(probe + probe-verified),sanitize 成 `EvidenceUpload`。
- `app/services/community_catalog_upload.py:70-84` — `batch_idempotency_key` 用 `(provider_id, provider_model_id, endpoint_fingerprint, method_id)` 四元组 SHA256;**evidence 自身无 content hash / stable id**。

## 4. SSOT 的真正含义:读者与写者都必须只认 credentials

> **更正前一版判断(根因)。** 本节早先写作"投影侧其实已经对齐 SSOT,写入侧才是
> 问题"——**这是错判**,且是整份 spec 漂移的根。当时只看了**一个**读者(gateway
> `state_projection`,它确实只认 credentials 里的 refs),就归纳成"所有读侧已对齐"。
> 这是从一个样本推全体的跳跃。**第一性原理下,SSOT 不是"写进去就行",而是
> evidence 的每一次读和每一次写都只认 credentials**;读和写对称。穷举之后,除
> `state_projection` 外还有 8+ 个生产读者直接吃 `llm_probe_catalog.json`,它们才是
> 后续 Phase 4 不断"补洞"的来源。下面两张表把读者、写者各自列全,逐个归类为
> **接门 / 溶解 / 退役**,作为后续 requirements/design/tasks 的唯一现状底稿。

分类口径:
- **接门**:它真的需要 evidence,改成只经"credentials evidence 访问服务"(scope 化的
  读写门)从 `route.evidence` 派生,不再碰 catalog 文件。
- **溶解**:它要的根本不是 evidence,而是 routes / 诊断信息——直接从 credentials 的
  `provider_routes` 取或进 runtime activity,**不在 credentials 里再造一份 evidence**。
- **退役**:它是旧 truth 链路本身,Phase 4/7/9 删除或停用。

### 4.1 写者表(evidence 如何进入)

| 写者 file:line | 现状 sink | 归类与做法 |
| --- | --- | --- |
| `_append_model_probe_evidence`(`llm.py:3025`,调用 867/904/1176) | probe catalog,probe-verified/failed | **接门**:`merge_route_evidence` → `credentials.provider_routes[id].evidence` |
| `_append_official_profile_probe_evidence`(`llm.py:2955`,调用 **1054 手动 official Test** + **2866/2876 role-test profile-ensure**) | probe catalog,official profile probe(**成功+失败都已写**,2866/2876) | **接门**:同上。**它被手动 Test 与 role-test profile-ensure 共用**——改的是 evidence 落点(catalog→credentials),**不是 role-test 编排**,不违 role-test 编排边界(requirements §10 非目标);`_ensure_official_role_test_verified_profile` 的 profile persist(2861)+ evidence 写入需**同一次 `save_credentials` 落盘**(避免两段写) |
| `_append_model_list_observation_evidence`(`llm.py:3079`,调用 815) | probe catalog,**endpoint 级** provider-list-observed(`scope={endpoint_id}`,无 model_id)+ route_candidates,载 observed/added/removed/unchanged(`llm.py:3105-3124`) | **溶解**(已拍板):**不再写 provider-list-observed evidence**;endpoint 当前列出的 models = 该 endpoint 下的 `provider_routes`;added/removed/unchanged → 本次 Test 的 **runtime activity 诊断**;不在 credentials 造 endpoint-level observation truth |
| `/catalog/sync` → `sync_remote_probe_catalog_with_metadata`(`llm.py:532-537` → `llm_import_drafts.py:300`) | 远端旧 probe catalog merge 进本地 evidence library,`source_id="llm_probe_catalog"` | **退役**:P2 下 `llm_probe_catalog.json` 不再是运行期 truth,这个**手动 API 不能继续作为正常入口**——删除或改成 credentials merge 语义(R4.2 原只停了 startup,漏了它) |
| `_apply_cached_community_evidence`(`llm.py:2161`,Test 后 920 调用) | 从**社区 cache**(`DisposableCatalogCacheStore`)promote 进 credentials `metadata["evidence_refs"]` | **退役**:Phase 4 删(R3.2)。注:它读的是社区 cache,**不是** probe catalog |
| `ensure_runtime_truth_sources` 建空 probe catalog(`runtime_truth_init.py:108`) | startup 主动建三个退役文件 | **退役**:Phase 9 不再建(problem 7) |

### 4.2 读者表(evidence 如何被读)

`load_evidence_library()` 的**生产**调用穷举(`llm.py`),逐个核过用途:

| 读者 file:line | 读 catalog 来做什么 | 归类与做法 |
| --- | --- | --- |
| `llm.py:192` / `663` | `collect_uploadable_uploads(library, …)` 上传候选 | **接门**:`collect_uploadable(credentials)` 从 `route.evidence` 筛 `probe`+`probe-verified`+非 community(R5) |
| `llm.py:602` | `/catalog/share` 导出 `probe`+`probe-verified`(605-606) | **接门**:从 credentials `route.evidence` 派生可分享集 |
| `llm.py:2169` | `_probe_catalog_summary` 数 local evidence/verified/failed/candidates → `ProbeCatalogSummary` → **`/api/llm/registry` → 前端 Settings**(`credentials.probe_catalog`,渲染于 `ApiKeysTab.tsx:69/198`) | **接门**:summary 从 credentials 派生(数 `route.evidence`)。**这是 UI 数据契约**——API 类型可不变,但来源必须换;否则 UI 继续展示旧 truth |
| `llm.py:3085` | model-list 观察读 `library.route_candidates` 算 `previous_model_ids`(3086-3090) | **溶解**:previous = 该 endpoint 当前 credentials `provider_routes`,不再读 catalog |
| `llm.py:4507` | compact model info 扫 `evidence_records` 判 `is_probe_verified` → 决定 model 状态显示(4508-4518) | **接门**:`route_is_probe_verified(route)` 从 `route.evidence` 判 |
| `llm.py:4833` | 第三方 probe 候选/排序 `known_model_ids_for_endpoint` + `_endpoint_probe_order`(4836-4841) | **接门/溶解**:候选 = credentials routes;排序优先级从 `route.evidence` 的 verified/failed 派生 |
| `llm.py:5228` | `_apply_promotable_route_update(route, library)`(5245/5293)的输入 | **退役**(R9.5,no backward compat):整条 promotable 运行期链路删除——不再 `load_evidence_library()` 推 route 的 capabilities/profiles/refs,不做 catalog→route.evidence bridge;route 能力只来自本次 Test |

**同理穷举社区 cache 读者(不重蹈 §4 的部分枚举)。** `community_catalog_cache.json`
(§6 同样退役)的生产读者:
- `_apply_cached_community_evidence`(`llm.py:2162`)→ **退役**(R3.2)。
- `_community_catalog_summary`(`llm.py:2133/2141`)→ 同一个 UI `ProbeCatalogSummary`
  的 `community_catalog` 字段(2183)→ **接门**:改从 credentials `last_remote_catalog_sync`
  marker + community-provenance 的 `route.evidence` 派生(与 R9.2 同类,别只改 probe 那半)。
- startup 建/列该文件(`runtime_truth_init.py:117` / `runtime_truth_sources.py:187`)→
  **退役**(Phase 9,problem 7)。

### 4.3 唯一本就对齐的读者:`state_projection`(保留)

- `graph-agent-gateway/.../state_projection.py:72-118` — `project_route_state`:蓝色
  `historical_ready`(106-111)只看入参 `credential_evidence_refs` 非空且
  `credential_available=True`(否则 88-91 先判 `missing_config`)。**这一个读者本就只认
  credentials refs**,契约正确、保留;变化只在 refs 来源:`metadata["evidence_refs"]` →
  `route.evidence` 的 probe-verified 派生(design §4.3)。
- gateway 契约测试 `tests/test_productization_route_state_contracts.py:38-51`(refs→
  historical_ready)、`235-247`(无 refs→untested)**目标契约保留**。
- **教训**:它是对齐的,但它**只是一个读者**;把它当成"读侧已全对齐"的证据,正是
  本节早先的错判。读者必须整表穷举,不能样本归纳。

## 5. 关键数据结构现状

- `app/models/llm_config.py:167-179` — `LLMCredentialsFile{schema_version:4, provider_endpoints, provider_routes, runtime_policy}`,**无顶层 evidence、无 remote-catalog metadata 字段**。
- `app/models/llm_config.py:81-85` + gateway `registry/schema.py:208-247` — `ProviderRoute` **无正式 evidence 字段**;evidence_refs 只是塞在 `metadata: dict[str,Any]` 里。
- gateway `registry/schema.py:358-392` — `EvidenceRecord` 有 `evidence_id`(随机 `evidence-{uuid.hex}`)、`evidence_type`、`trust_state`、route/model 标识、probe 明细;**无 content_hash**。
- gateway `registry/schema.py:395-411` — `ProviderImportDraft`(= `llm_probe_catalog.json`)持有 `evidence_records: list[EvidenceRecord]`。
- `RemoteCatalogSourceMetadata`(`llm_import_drafts.py:56-69`)只活在**进程内存全局变量**,不持久化,不在 credentials。

## 6. 为什么必须移除两个本地 catalog 文件作为运行期 truth

1. **真相源唯一性**:同一份 evidence 同时存在 credentials(refs) + probe catalog(本体) + community cache(本体),三处可漂移;现象就是"cache 有、local 没有、credentials 凭空有"。第一性原则下,truth 只能有一份。
2. **不可变/投影原则**:UI 蓝色态依赖 evidence,evidence 若不在 credentials,则"UI 只能从 credentials 投影"无法成立。
3. **同步简化**:用户已定调"本地不做复杂 catalog diff、不用本地 community cache 比对远端"。只要 evidence 本体进 credentials 且单条格式与 catalog 同构,远端沿用现有 `batch_idempotency_key` 幂等去重即可(content_hash 只做本地键、不进 wire),本地无需 cache 文件做 diff。
4. **写一次 truth**:Test 应一次性把 probe/test/routes/models/evidence 落 credentials;上传失败不回灌 credentials(不存 pending queue),下次从 credentials 重新派生候选。

## 7. 与现有 4 个 spec 的衔接(含一处显式 supersede)

- `community-probe-catalog-service-phase2a`:本 spec **显式 supersede 它的一条 Non-Goal,并严格沿用另两条**——
  - **supersede**:其 `requirements.md:39` "No path that auto-applies remote evidence to active credentials"。本设计的核心正是远端 verified catalog 验签后**直接 merge 进 credentials**,即"自动应用远端 evidence 到 active credentials"。这是**有意反转**,不是无冲突:旧约束靠"本地 disposable cache + Test 时 carry"做间接应用;本 spec 删掉本地 cache、把 merge 收敛到验签后的同步点,truth 仍唯一(credentials)。理由是旧的间接链路恰恰造成"cache 有/local 没/credentials 凭空有"的漂移(见 §3.1)。
  - **继续有效、严格沿用**:其 `requirements.md:43` "`provider-list-observed` never contributes to `historical_ready`" 与 `:44-45` "remote/community artifacts 可 feed `historical_ready`、**never `ready`**"。本 spec 的投影只认 `probe-verified`(见 design §4.3),community evidence 只投蓝不投绿,完全一致。
- `studio-llm-remote-draft-catalog`:已统一 `route_id`、约束 `historical_ready` 仅来自 remote evidence + 非 verified。本 spec 沿用其 route_id/historical_ready 约束,只是把 evidence 本体从"远端 draft/本地 cache"收敛进 credentials。
- `studio-api-keys-redesign` / `studio-llm-gateway-redesign`:已确立 credentials 为 credentials + route status 的 SSOT、Test 状态后端原子回写、roles 与 credentials 解耦。本 spec 把"evidence 本体"也纳入这同一份 SSOT,补齐最后一块。

## 8. KEEP-MAIN 边界(改动范围预判)

- AGENTS.md 冻结 `packages/graph-agent` / `graph-agent-gateway`,studio 层改动走 adapter。
- 本次唯一获授权的 gateway 改动:给 `EvidenceRecord` 加 `content_hash` 字段 + 确定性生成 helper(用户已拍板)。`state_projection.py` 本 session 已在改、契约不变。
- 其余(credentials schema v5、`ProviderRoute.evidence`、Test/sync/upload 链路、migration)全部落在 **studio 层**(`apps/studio/backend`),evidence 单条复用 gateway 的 `EvidenceRecord` 类型。
