# Tasks — Studio LLM credentials/catalog SSOT 重构

> 严格 TDD:每个任务先写**会失败**的测试(证明坏链路/锁目标契约),跑红,再写实现转绿。
> 引用编号见 `requirements.md`(R*) 与 `design.md`(§*)。仅后端逻辑,无 UI 手工验证。
> 顺序按依赖:模型 → hash/merge → 投影 → Test → 同步 → 上传 → 迁移 → 守卫 → 接线 → 全量门禁。

## Phase 0 — 准备

- [ ] **T0.1** 通读本 spec 三文件,确认对齐;在 `apps/studio/backend/app/models/llm_config.py`
  与 gateway `registry/schema.py` 标出改动锚点(不改代码)。
- [ ] **T0.2** 跑一遍现状基线:`uv run pytest apps/studio/backend/tests/routers/test_llm_registry_api.py
  packages/graph-agent-gateway/tests/test_productization_route_state_contracts.py`,记录绿基线。

## Phase 1 — evidence 模型 + content_hash(R2,§2.1/§3)

- [ ] **T1.1 (red)** gateway 新测试 `packages/graph-agent-gateway/tests/test_evidence_content_hash.py`:
  - 同语义、仅时间戳不同的两条 `EvidenceRecord` → `compute_evidence_content_hash` 相等(R2.1-AC1)。
  - 任一语义字段(`normalized_public_base_url`/provider_model_id/method_id/probe_status…)不同 → hash 不同(R2.1-AC2)。
  - **endpoint 公网身份用正式字段 `normalized_public_base_url`**(problem 3):本地构造 + 远端
    `parse_catalog_evidence` 填同字段 → 算出同一 hash;改 `metadata` 不影响 hash。
  - `EvidenceRecord` 带默认 `content_hash=None` / `normalized_public_base_url=None` 仍可正常序列化/校验(向后兼容)。
- [ ] **T1.2 (green)** gateway `registry/schema.py`:加 `EvidenceRecord.content_hash` +
  `normalized_public_base_url` 两字段 + `compute_evidence_content_hash`(§2.1/§3,problem 3)。
  跑 gateway evidence/schema 相关测试确认不回归。

## Phase 2 — credentials schema v5 + merge helper(R1/R2.2,§2.2/§4.1)

- [ ] **T2.1 (red)** studio 新测试 `tests/services/test_llm_credentials_evidence.py`:
  - `LLMCredentialsFile` v5 含 `provider_routes[id].evidence` 往返(load→save→load)一致、顺序稳定(R1.2-AC1)。
  - `merge_route_evidence`:同 content_hash 重复写只留 1 条且保留最新 observed_at(R2.2-AC1)。
  - 删除 route 后其 evidence 不残留(R1.3-AC1)。
  - `last_remote_catalog_sync` 只存 3 标量,sync 不撑大文件(R1.4-AC1,占位断言)。
- [ ] **T2.2 (red)** `tests/services/test_credentials_schema_migration.py`:v4 文件加载后就地升级为 v5
  (补 `evidence=[]`/`last_remote_catalog_sync=None`/版本 5),不丢原 endpoints/routes(§2.3)。
- [ ] **T2.3 (green)** 实现:`models/llm_config.py`(schema v5、`ProviderRoute.evidence`、
  `RemoteCatalogSyncMarker`、`_gateway_route` exclude `"evidence"`);新建
  `services/llm_credentials_evidence.py`(`merge_route_evidence`);`services/llm_credentials.py`
  加 v4→v5 加载升级 + 迁移前 `.bak` 备份(§12 R-C)。

## Phase 3 — 投影 refs 从 route.evidence 派生(R6,§4.3)

- [ ] **T3.1 (red)** studio 新测试 `tests/core/adapters/test_route_evidence_projection.py`:
  - route 有 probe-verified `evidence`、凭证可用、未 verified → 投影 `historical_ready`(R6-AC1)。
  - route `evidence` 为空 → 不投影蓝(回落 untested,R6-AC2)。
  - route 只有 `probe-failed` evidence → 不投影蓝(§4.3,失败不变蓝)。
  - **route 只有 `provider-list-observed` evidence(无 probe-verified)→ 不投影蓝**(problem 4,
    严格沿用旧 spec community-probe-catalog-service-phase2a `requirements.md:43`)。
- [ ] **T3.2 (green)** `core/adapters/gateway.py:_route_credential_evidence_refs` 改为从
  `route.evidence` 派生(仅 `PROJECTABLE_TRUST_STATES`)。**不改** gateway `project_route_state`。
- [ ] **T3.3 (verify)** gateway `tests/test_productization_route_state_contracts.py`(38-51 refs→蓝、
  235-247 无 refs→untested)保持绿——证明 gateway 投影契约未变(R6-AC3)。

## Phase 4 — Test 流程读写都只认 credentials(R3/R9,§4/§5)

> **不再是"只写"。** 按读写对称拆四步:建门 → 写者接门 → 读者接门/溶解 → 失败/route-probe。
> 这样每步红测都能独立证伪一类旧链路,避免 Phase 4 反复补洞(见 research §4 更正)。

### T4.0(前置)role-test 边界确认
- [ ] 确认 role-test 编排**不另读** `load_evidence_library` / 写 `append_evidence_record`
  (已查:role-test 代码不直接调二者;唯一交点是共用写者 `_append_official_profile_probe_evidence`)。
  若发现其它 library 依赖,先记录再定边界(§10:不改编排,只改 evidence sink)。

### T4a — 建访问门读侧(R9,§4.2)
- [ ] **T4a.1 (red)** `tests/services/test_credentials_evidence_readers.py`(新):给定含
  probe-verified/probe-failed evidence 的 credentials(**无 probe catalog 文件**),
  `route_is_probe_verified` / `route_probe_history` / `collect_uploadable` /
  `probe_evidence_counts` / `endpoint_probe_priority` 全从 `route.evidence` 派生出正确值。
- [ ] **T4a.2 (green)** `services/llm_credentials_evidence.py` 增读门查询(§4.2),门内只读 credentials。

### T4b — 写者接门(R3.1/R3.2/R3.3,§5)
- [ ] **T4b.1 (red)** `tests/routers/test_llm_endpoint_test_evidence.py`(新):
  - 第三方 endpoint Test 成功 → `route.evidence` 含 probe-verified;`llm_probe_catalog.json`
    未被创建/写(R3.1-AC1)。
  - manual model Test(official + 第三方各一)→ route.evidence 含本次结果,probe catalog 未写(R3.1-AC2)。
  - official role-test profile-ensure:profile persist + profile-probe evidence(成功/失败)在
    **同一次 save** 落 credentials(R3.3-AC2)。
  - 预置含匹配 records 的 `community_catalog_cache.json`,Test 后 credentials evidence **只**来自
    本次 Test,runtime activity 无 `promoted_catalog_records`(R3.2-AC1)。
- [x] **T4b.2 (green)** `routers/llm.py`:`_build_model_probe_evidence`(原 `_append_*`)经
  `merge_route_evidence` **赋回** `credentials.provider_routes[id]`(endpoint + manual 第三方,merge
  在 save 前);**删除** `_apply_cached_community_evidence` + `_append_model_list_observation_evidence`;
  promotable 运行期链路**整体退役**(R9.5,no backward compat:删 `_apply_promotable_route_update`
  + 调用 + `load_evidence_library` promote 读);失败 probe 带回真实 failed model 写 `probe-failed`;
  model-list **溶解**为 runtime activity diff;source_id → `llm_credentials`。
  - **official-profile 写者(contract 4,已完成)**:`_append_official_profile_probe_evidence` →
    `_build_official_profile_probe_evidence`;manual-official(merge 在 1050 save 前)与 role-test
    profile-ensure(两个 `_persist_*` 内 merge,profile+evidence 同次 save,R3.3-AC2)都接门;
    `_ensure_*` 删 append 调用。红测 `test_official_role_test_profile_ensure_writes_evidence_to_route_not_catalog`。
  - **T4e(adjust)**:catalog→蓝旧契约改写——`...promotes_probe_verified_draft...` 改为预置
    `route.evidence` 测 projection;model-list / manual / role-test 用例断言改 credentials;
    community-promote 蓝 + `..._carries_cached_community_evidence...`(T5.1 replace target)`skip` 留 Phase 5。
  - **完成标准达成**:`append_evidence_record` 在 `llm.py` **已无引用**(Test 写侧零 catalog 写)。
    门禁:routers+services 中 0 个 evidence/credential/community 失败;ruff + mypy clean。

### T4c — 读者接门 / 溶解(R9,R3.4)
- [ ] **T4c.1 (red)** `tests/routers/test_llm_readers_from_credentials.py`(新):**删空/不预置
  probe catalog**,以下仍正确——
  - registry `probe_catalog` 计数 = credentials evidence 条数(R9.2-AC1)。
  - compact model info `is_probe_verified` 从 route.evidence 判(R9.3)。
  - 第三方 probe 候选/排序优先 verified、押后 failed,顺序同现状(R9.4-AC1)。
  - 上传/分享候选从 credentials 派生(R9.1,接 Phase 6)。
  - model-list:Test 后**无** `provider-list-observed` evidence;added/removed 进 runtime activity;
    `previous_model_ids` 据 credentials routes 算(R3.4-AC1/AC2)。
- [x] **T4c.2 (green, 已完成)** `routers/llm.py` 6 个生产读者全部接读门:`/catalog/share`(599)→
  route.evidence 派生(排除 community provenance);`_probe_catalog_summary`(2169)→ `probe_evidence_counts`
  + community summary 空化(Phase 5);compact model `is_probe_verified`(4507)→ `route_is_probe_verified`;
  probe 候选/排序(4833)→ `endpoint_listed_model_ids` + `endpoint_probe_priority`(删 `verified_model_ids`
  贯穿);上传候选(192/663)→ `collect_uploadable(credentials)`。删死代码 `_endpoint_probe_order` /
  `_endpoint_probe_model_ids_by_trust` / `_community_catalog_summary` + 8 个 unused import。
  - **完成标准达成**:`load_evidence_library` 在 `llm.py` **零调用**(仅余 store 定义 + `runtime_truth_init`
    建文件[Phase 9] + `new_evidence_id` 工具 + `/catalog/sync` R9.6 入口)。registry **display** 不再读 catalog。
  - **T4e**:3 个 probe-order 单测改种 credentials routes;`...exposes_verified_community_cache` `skip`(Phase 5)、
    `...last_remote_catalog_source` 改数 credentials;autoshare(5)/contribute(3)改 mock `collect_uploadable` +
    种 route.evidence。门禁:routers+services 0 个 evidence/credential/community 失败;ruff+mypy clean。
  - **R9.6(已完成)**:`/catalog/sync` 改为退役 no-op(不读不写 catalog、不投 source);删
    `_sync_remote_probe_catalog_on_startup`(main.py 启动不再同步旧 probe catalog);registry
    `catalog_source` / `probe_catalog.remote_catalog_source` 恒为 None(不再投旧远端源);删
    `_remote_catalog_sync_inputs` + 5 个 unused import。旧测试改新契约
    (`test_sync_catalog_endpoint_is_retired_and_disabled` / `..._does_not_project_legacy_remote_catalog_source` /
    `test_lifespan_does_not_sync_legacy_remote_probe_catalog`)。门禁绿。
    **前端 follow-up**(非本 spec):`api/llm.ts` 的 `catalog_source`/syncCatalog 类型与按钮可后续清理。

### T4d — 失败 evidence + route-probe(R3.1-AC3/AC4,codex-3)
- [ ] **T4d.1 (red)** `tests/routers/test_llm_failed_probe_evidence.py`(新):
  - 第三方 endpoint Test **get-models 成功、generation/protocol probe 失败** → 失败 model 的 route
    含 `probe-failed` evidence,不投蓝(R3.1-AC3)。
  - `/routes/{id}/probe?force=true` 成功/失败都写 route.evidence(R3.1-AC4)。
- [ ] **T4d.2 (green)** 扩展 `_verify_third_party_endpoint_by_probe`(`llm.py:4933+`)带回失败
  `RouteProbeResult`;Test / route-probe 失败路径 `merge_route_evidence` 写 `probe-failed`。

### T4e (adjust) 现有用例
- [ ] 现有 `tests/routers/test_llm_registry_api.py`:
  - `test_endpoint_test_promotes_probe_verified_draft_capabilities_and_profiles`(~2229):保留
    "Test 后 route historical_ready",来源断言改 `route.evidence`(非 probe draft/metadata refs)。
  - 其余 endpoint-test 用例(protocol detect / verified 等)仍绿,**不得**误删 Qiniu/notable 行为(§10 非目标)。

## Phase 5 — 远端下载直接 merge 进 credentials(R4,§6)

- [ ] **T5.1 (red)** `tests/routers/test_community_catalog_sync_endpoint.py` 改 + 增:
  - **反转** `test_verified_sync_caches_without_promoting_credentials`(120/135):sync 后本地有匹配
    route 时,该 route.evidence 含远端 verified evidence;`community_catalog_cache.json` 未被创建/写(R4.1-AC1)。
  - **替换** `test_endpoint_test_carries_cached_community_evidence_for_new_routes`:改为"sync 时即
    merge 进 credentials",而非 Test 时 carry。
  - 新增 fail-closed:验签/分片/协议校验失败 → credentials 不变 + 抛 `VerifiedSyncError`(R4.1-AC2)。
  - 新增:远端 evidence 无匹配本地 route → 忽略,无游离条目(R4.1-AC3)。
- [ ] **T5.2 (green)** `community_catalog_runtime.py` + `community_catalog.py`:验签后
  `parse_catalog_evidence` → `merge_route_evidence` 进 credentials + 更新 `last_remote_catalog_sync`;
  删除写 cache 文件;`apply_community_evidence_to_credentials` 改写 route.evidence(§6.1)。
- [ ] **T5.3 (adjust)** 现有 `tests/routers/test_llm_registry_api.py:404-466` community promote 两用例:
  改为经"sync→merge route.evidence"达成 `historical_ready`;保留"observed-only/unmatched host 被跳过"语义。
- [ ] **T5.4 (red)** problem 6 触发(R4.3),`tests/routers/test_endpoint_test_triggers_verified_sync.py`(新):
  - 先跑 verified sync(无匹配 route → 远端 evidence 被忽略)→ 再建 provider + 跑 endpoint Test →
    Test 后该 route 的 `evidence` 含匹配的远端 verified evidence,投影 `historical_ready`(R4.3-AC1)。
  - 触发是 best-effort:mock sync 抛错 → endpoint Test 结果不受影响(R4.3-AC2)。
- [ ] **T5.5 (green)** `routers/llm.py:test_endpoint` 成功落盘后 best-effort 触发
  `sync_verified_community_catalog`(§6.3,try/except 包裹、失败仅 log)。

## Phase 6 — 退役 OfflineUploadQueue 运行期写路径(R5,§8)

> 上传候选「从 credentials 派生」已在 **T4c**(Phase 4)落地:autoshare/contribute 都走
> `llm_credentials_evidence.collect_uploadable(load_credentials())`(排除 community-provenance +
> 无 fingerprint)。Phase 6 只剩把**持久化重试队列**拔掉 + 失败措辞改真,不再有新的"派生"工作。

- [x] **T6.1 (red→green)** `tests/test_community_catalog_upload.py` 重写为无 queue 契约:
  上传失败 `raise CommunityUploadError` 且**不落盘**(`tmp_path` 为空);`upload_batch(..., queue=)`
  关键字被拒(TypeError);删 `drain_queue` / `collect_uploadable_uploads` 死代码测试;
  `batch_idempotency_key` 用 `build_upload_record` 直接造样本(content 派生 → 重派生稳定,R5.2-AC1)。
- [x] **T6.2 (green)** `community_catalog_upload.py`:删 `OfflineUploadQueue` / `QueuedBatch` /
  `DrainResult` / `UploadDeferred` / `drain_queue` / `collect_uploadable_uploads`(死,基于已退役 library)/
  `_now_iso` 及无用 import;`upload_batch` 去 `queue` 形参、失败 `raise CommunityUploadError`(§8/D4)。
  `llm.py`:autoshare 去 queue 直接上传;contribute `except CommunityUploadError` → `status:"failed"`
  (非 `deferred`/`queued`)+ 如实说"evidence 留在 credentials、下次从 credentials 重派生重试";
  移除 `OfflineUploadQueue` / `community_upload_queue_path` import。幂等沿用 content 派生的
  `batch_idempotency_key`(**不改 wire schema**)。
- [x] **T6.3 (adjust)** `test_community_catalog_contribute.py`(deferred→failed)/
  `test_community_catalog_autoshare.py`(fake 去 queue 形参)更新为新契约;
  `runtime_truth_init.py:_ensure_upload_queue_file` 从**已删的类**解耦成通用 JSON writer 写 `[]`
  (inert 空文件留到 Phase 9 退役 — `OfflineUploadQueue` 类本身已在 T6.2 删除),
  `test_runtime_truth_init.py` 改普通 json 读断言。

### Phase 5 顺手清理(随 Phase 6 带上)

- [x] **C1 (sync 改名 + source 统一)** `community_catalog_runtime.py`:
  `sync_verified_community_catalog_cache` → `sync_verified_community_catalog_into_credentials`
  (名字不再带"cache",改 docstring);两处 runtime-activity source 从
  `community_catalog_cache`/`community_catalog` 统一为 `llm_credentials`(数据落地处、显示已注册、
  Phase 9 不退役)。callers 同步:`main.py:40/73`、`llm.py:78/703`(顺带清掉 `/catalog/sync-verified`
  endpoint docstring 的旧 "read/cache only…applied later during Test" 模型)、
  `test_main_remote_catalog_sync.py`。contribute 三个分支 source 一并归 `llm_credentials`。
- [x] **C2 (merged_route_count 收紧)** `merge_community_evidence_into_credentials`:只在
  `after != before`(`merge_route_evidence` 实际改变 route)时计数+回写 → 重复同步同一 catalog
  返回 0,runtime-activity `merged_route_count` 不再按匹配次数虚高(测试
  `test_merge_is_idempotent_by_content_hash` 加断言第二次=0)。

### Phase 6 drift 修复(审计发现,进 Phase 9 前补)

- [x] **D6.1 (red→green,R5.2-AC2)** `batch_idempotency_key` 自称 content-derived,实则只吃
  `(provider_id, provider_model_id, endpoint_fingerprint, method_id)` 四元组 —— 同 endpoint+model+method
  下 `request_mapper_id`/`capability_family`/`model_type`/`input/output_modalities`/`probe_status`/
  `normalized_public_base_url` 变了 key 不变,远端会误判幂等去重。
  - 红测(`test_community_catalog_upload.py`):7 个语义字段任一变 → key 必须变(parametrize);
    顺序无关 → key 相同;`observed_at` 变 → key 相同(时间戳不进 key);同证据重派生 → key 相同。
  - 绿:`batch_idempotency_key` 改为对**整条 sanitized payload** `model_dump(mode="json",
    exclude={"observed_at"})` + `sort_keys` + batch 稳定排序 + sha256;不再手写四元组,不引入
    时间戳/receipt/随机字段;注释说明 key 从脱敏 payload 派生(非 credential secret / 本地路径)。

## Phase 7 — Legacy 一次性迁移(R8,§7)

- [ ] **T7.1 (red)** `tests/services/test_legacy_evidence_migration.py`(新):
  - 含 evidence 的两个 legacy 文件 + 匹配 route 的 credentials → 迁移后 evidence 入 credentials;
    重复运行幂等(content_hash 去重,R8-AC1)。
  - 无匹配 route 的 evidence 被忽略,无游离条目(R8-AC2)。
  - 迁移内部异常仅 log、不抛(best-effort,R8-AC3)。
- [ ] **T7.2 (green)** 新建 `services/llm_legacy_evidence_migration.py`
  (`migrate_legacy_catalog_evidence_into_credentials`),读两文件 → `merge_route_evidence`(§7)。

## Phase 8 — 空 Base URL 守卫测试(R7,§9,实现已在)

- [ ] **T8.1 (red→已绿)** gateway `tests/`:空 base_url endpoint/route probe → `status="error"` +
  `error_code="missing_config"`,无出站 HTTP(R7-AC1);覆盖 `provider_probe`。
- [ ] **T8.2 (red→已绿)** studio `tests/routers/`:空 base_url 走 legacy adapter 同样 missing_config
  (R7-AC2)。若实现已满足则为回归锁定测试。

## Phase 9 — 退役 legacy catalog/cache/queue(不创建、不展示、不作为产品概念)

> 锁定范围 = 让三类 legacy 文件(`llm_probe_catalog.json` / `community_catalog_cache.json` /
> `community_upload_queue.json`)不再被创建、不再被展示、不再作为产品入口概念存在。startup 的
> remote-probe-catalog sync 早在 R9.6/Phase 5 退役;本阶段是文件/显示/入口的物理退役。

- [x] **T9.1 (red→green,point 1)** `runtime_truth_init` 不再创建三类文件:删
  `_ensure_probe_catalog_file` / `_ensure_community_catalog_cache_file` / `_ensure_upload_queue_file`
  + 调用 + import(`ImportDraftStore` / cache store / 三个 path helper)。红测:干净 startup 后三者不在
  `created`、`probe_catalog_path()` 不存在。
- [x] **T9.2 (red→green,point 2)** `runtime_truth_sources` 不再展示三项:删整个 "catalog" section 的
  三个 TruthSource;幸存的 `llm_canonical_rules` 并入 "LLM runtime truth" section。红测:
  `/api/system/truth-sources` 不返回三者。
- [x] **T9.3 (green,point 3 干净的那半)** `llm_paths`:删 `community_catalog_cache_path` /
  `community_upload_queue_path` + `__all__`(points 1/2 后零生产用途)。
- [x] **T9.4 (green,point 4)** `community_catalog_sync`:删 `CommunityCatalogCache` /
  `DisposableCatalogCacheStore` + `__all__` + 失用 import(`os`/`tempfile`/`Path`),docstring 改 no-cache;
  `sync_verified_catalog` 早已 no-cache,cache store 模型不再作为运行期概念。删 `test_disposable_cache_path_*`。
- [x] **T9.5 (red→green,point 5)** `/catalog/repository/ensure` retire 成 disabled no-op:删
  `ensure_catalog_repository` helper + `github_catalog` import;endpoint 直接回 `{"status":"disabled"}`,
  不碰 GitHub、不建 repo。红测:endpoint 回 disabled、无 token check、无 `repository_created`。
- [x] **T9.6 (point 7)** mojibake 清查:后端 app/ + 本链路前端文件零 mojibake;唯一命中
  `GraphCanvas.tsx` 不属本链路(无关 dirty 改动),不碰。

### Phase 9 紧邻任务(列出,不漏)

- **A1 (point 3 余下)** 退役 probe-catalog 存储子系统。证据:`new_evidence_id` 是唯一活的生产导出
  (llm.py 经 facade 用);`apply_draft`/`create_draft`/`load_evidence_library`/`append_evidence_record`/
  `sync_remote_evidence_library`/`remember_remote_catalog_source` 全无生产调用方(只剩测试 + 内部自引用);
  `llm_stable_id_migration` 零生产调用方。gateway 的 `ProbeCatalogStore`/`ImportDraftStore` 是 KEEP-MAIN,**不碰**。
  - [x] **A1.1(关键第一步,本轮已做)** 新建中性 util `services/llm_evidence_ids.py`(`new_evidence_id`),
    `llm.py` 改从它 import → **不再 import `llm_probe_catalog`**。验证:ruff/mypy 绿、probe-flow 测试 10 passed。
  - [x] **A1.2(本轮已做)** 删除完全死、自包含的 `llm_stable_id_migration.py` + `test_llm_stable_route_id_migration.py`
    + `test_productization_import_boundary_red.py` 的 SDK-import 白名单条目(其 `expiry` 本就写"this module is removed")。
    验证:无残留引用、ruff/mypy 绿、boundary 测试 6 passed。
  - [x] **A1.3(本轮已做)** 删 `llm_import_drafts.py` + `llm_probe_catalog.py` + `llm_paths` 的
    `probe_catalog_path`/`import_drafts_path`(+ `__all__`)+ 删测试文件 `test_llm_import_drafts.py`/
    `test_llm_remote_catalog_seed.py`。消费测试更新:`test_llm_registry_api.py`(去 import + 8 处
    `load_evidence_library == []` 负向断言;**删** 2 个纯 catalog 负向测试 `..._historical_ready_from_catalog...` /
    `test_model_list_observation_keeps_registry_route_untested`;**改写** `..._reprobes_..._in_draft`(去 vestigial 播种,
    生产 probe 排序已读 credentials,断言由 fake gateway 驱动)+ `..._legacy_remote_catalog_source`(去 remember 机制,
    **保留** local-count 正向覆盖));`test_llm_endpoint_test_evidence.py`(去 import + 4 处负向断言,保留 route.evidence
    正向断言);`test_llm_active_paths.py`(去 probe/drafts 路径断言);`test_runtime_truth_init.py`(去 `probe_catalog_path`
    断言,`"llm_probe_catalog" not in created` 已覆盖)。
    - 完成标准(point 6)达成:生产 app/ **零** `llm_import_drafts`/`llm_probe_catalog`/`load_evidence_library`/
      `append_evidence_record`/`probe_catalog_path`/`import_drafts_path`/`remember_remote_catalog_source`/
      `sync_remote_evidence_library` **active 使用**(剩余仅注释 + A2 域的 GitHub config 字符串);测试侧零真实使用。
      `/catalog/sync` + `/catalog/repository/ensure` 仍 disabled no-op、不依赖删掉的模块。ruff/mypy 绿;
      A1.3 影响测试 117 passed;全量后端零新增失败(85 既有 Windows,passed 降 17 = 删掉的旧测试)。
      gateway `ProbeCatalogStore`/`ImportDraftStore` 全程未碰(KEEP-MAIN)。
- [x] **A2 (本轮已做)** 删死模块 `services/github_catalog.py` + `tests/services/test_github_catalog.py`
  + `BackendConfig` 里失用的 `github_token`/`github_owner`/`llm_catalog_repo`/`llm_catalog_branch`/`llm_catalog_path`
  字段(retire `/catalog/repository/ensure` 后全死,无 reader)。`/catalog/repository/ensure` 仍是 disabled no-op,
  不 import github_catalog、不读这些 config。`extra="ignore"` 保证旧 `STUDIO_GITHUB_*` env 不报错。
  - 完成标准达成:生产 app + 测试 **零** `github_catalog`/`GitHubCatalogClient`/`GitHubCatalogApiError`/
    `llm_catalog_path`;`catalog_source`/`remote_catalog_source` 响应兼容字段(恒 null)**保留未动**(point 5);
    `llm_probe_catalog`/`community_catalog_cache`/`community_upload_queue` 仅剩 disabled-endpoint 文案 + 退役断言/注释。
    其他 spec(`studio-llm-remote-draft-catalog`/`community-probe-catalog-service-phase2a`)的历史引用按提交纪律不碰。
    ruff/mypy 绿(112 files);A2 改动区零失败;全量后端零新增失败(86 既有 Windows flaky)。
- [x] **A3 (point 6) 前端跟随清理(本轮已做)** `api/llm.ts`:删 `catalog_source`(RegistryResponse)/
  `remote_catalog_source`(ProbeCatalogSummary)/`CatalogSourceMetadata`/`CatalogSyncResponse` + 调已退役
  `/catalog/sync` 的 `syncRemoteModelCatalog`;`VerifiedCatalogSyncResponse.promoted_route_count`(死字段、
  且后端实为 `merged_route_count`)更名 + 注释改 Phase 5 语义;`syncVerifiedCommunityCatalog` docstring 去
  "disposable cache"。`GeneralTab`:删 `truthSourceCategory` 的 legacy "catalog" 分支。locales(en+zh):删
  `categories.catalog` / `sections.catalog` / 三个 `sources.*` legacy 标签。测试:删旧 `syncRemoteModelCatalog`
  测试 + 清 `api/llm.test.ts`、`SettingsPage.test.tsx` fixtures 里的 `remote_catalog_source`/`llm_probe_catalog.json` URL。
  - 验证:typecheck 新增错误 0、vitest 新增失败 0(stash 隔离确认 GeneralTab:354 动态 key typecheck 错 + 3 个
    vitest 失败均为 dirty 工作区**既有**,与本清理无关,按纪律不动)。后端 registry 仍回 `catalog_source/
    remote_catalog_source = null`,故前端不 break;清理纯属去死类型/文案,无视觉变化。

## Phase 10 — 全量门禁(CI Gates,推送前必绿)

- [ ] **T10.1** 后端 lint+types:`uv run ruff check <changed pkgs>` ·
  `uv run mypy --strict packages/graph-agent-gateway/src` · `uv run mypy apps/studio/backend/app`。
- [ ] **T10.2** 后端测试:`uv run pytest apps/studio/backend/tests` ·
  `uv run pytest packages/graph-agent-gateway/tests`(必要时 `packages/graph-agent/tests`)。
- [ ] **T10.3** 依赖审计:`uv run --with pip-audit pip-audit`(0 CVE)。
- [ ] **T10.4** 前端:仅当触碰 `apps/studio/frontend` 才跑;本 spec 默认不改前端逻辑。
- [ ] **T10.5** 全绿后回写长期文档(三模块设计/handbook 相关处),并按用户规则只提交本人改动。

## 验收映射(spec → 测试)速查

| 需求 | 主要测试任务 |
| --- | --- |
| R1.1/R1.2/R1.3/R1.4 schema v5 + evidence 字段 | T2.1/T2.2 |
| R2.1 content_hash 确定性 | T1.1 |
| R2.2 content_hash 去重 | T2.1 |
| R3.1 Test 写 credentials(成功+失败)不写 probe catalog | T4b.1/T4d.1 |
| R3.1-AC3 第三方 probe 失败写 probe-failed(codex-3) | T4d.1 |
| R3.1-AC4 route-probe `?force=true` 产 evidence | T4d.1 |
| R3.2 不从 community cache promote | T4b.1 |
| R3.3-AC2 official role-test profile+evidence 同次 save | T4b.1 |
| R3.4 model-list 溶解(不产 observation evidence,problem 6) | T4c.1 |
| R9 运行期读者从 credentials 派生(读写对称,P7) | T4a.1/T4c.1 |
| R9.2 probe_catalog summary = UI 契约,来源换 credentials | T4c.1 |
| R9.6 旧 `/catalog/sync` 远端 probe catalog 入口退役 | T4c.2 |
| R4.1 下载 merge 进 credentials/不写 cache/fail-closed | T5.1 |
| R4.2 旧 probe catalog startup 停用 | T9.1 |
| R5.1 上传从 credentials 派生 | T6.1 |
| R5.2 失败不入 credentials/重派生稳定 | T6.1 |
| R6.1 蓝色只来自 credentials evidence | T3.1/T3.3 |
| R7.1 空 base_url missing_config | T8.1/T8.2 |
| R8.1 legacy 一次性迁移幂等 | T7.1 |
| R2.1 endpoint 公网身份升正式字段(problem 3) | T1.1/T1.2 |
| R6.1 provider-list-observed 不投蓝(problem 4) | T3.1 |
| R5.1-AC3 community evidence 不回环上传(problem 5) | T6.1/T6.2 |
| R4.3 Test 后触发 verified sync 补蓝(problem 6) | T5.4/T5.5 |
| problem 7 退役文件不再创建/展示 | T9.3/T9.4 |
