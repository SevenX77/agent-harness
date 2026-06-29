# Design — Studio LLM credentials/catalog SSOT 重构

> 落地"做法"。需求/验收见 `requirements.md`,现状审计见 `research.md`。
> 设计目标:让带 `content_hash` 的 `EvidenceRecord` 成为**唯一 evidence 模型**,
> credentials 内嵌它、catalog 交换它、远端沿用现有 `batch_idempotency_key` 幂等去重(content_hash 只做本地键、不进 wire);两个本地
> catalog 文件退出运行期 truth。

## 1. 总览:一个 evidence 模型,三处用途

```
                    ┌─────────────────────────────────────────┐
                    │  EvidenceRecord (gateway, +content_hash) │  ← 唯一格式
                    └─────────────────────────────────────────┘
                       ▲              ▲                 │
            (1) Test/probe 写入   (2) 远端验签后 merge   (3) 派生上传候选
                       │              │                 ▼
        ┌──────────────┴──────────────┴───────┐   ┌──────────────────┐
        │  llm_credentials.json  (SSOT, v5)    │   │ 远端 community     │
        │  provider_routes[id].evidence: [...] │   │ catalog gate       │
        │  last_remote_catalog_sync: {etag,…}  │   │ (content_hash 去重)│
        └──────────────────────────────────────┘   └──────────────────┘
                       │
            (4) 投影 refs = route.evidence 中"正向"evidence 的 content_hash
                       ▼
            registry response → UI 蓝色 historical_ready
```

- 不再有 `llm_probe_catalog.json` / `community_catalog_cache.json` 参与 (1)(2)(3)。
- (1)(2) 都按 `content_hash` 去重 merge 进同一份 `route.evidence`;(3) 从它派生;
  (4) 从它投影。一份 truth,四向自洽。
- **读写对称(P7)**:(1)(2) 写、(3)(4) 及所有其它读者都只经 `llm_credentials_evidence.py`
  一道门(§4)。model-list **不进 evidence**——它的真相就是 routes,溶解成 `provider_routes`
  + runtime activity 诊断(§5.1)。

## 2. 数据模型变更

### 2.1 gateway(唯一获授权的冻结区改动)

文件:`packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py`

- `EvidenceRecord` 新增**两个字段**:`content_hash: str | None = None` 与
  `normalized_public_base_url: str | None = None`。后者把 endpoint 公网身份**升为正式
  字段**(过去只塞在 `metadata`,见 problem 3),让本地/远端算 hash 时取同一正式字段。
  > **KEEP-MAIN 例外(problem 2)**:原口径是"gateway 只加 `content_hash` 一字段 + 算法"。
  > 但 content_hash 的确定性**必须**以 endpoint 公网身份做正式输入,故 `normalized_public_base_url`
  > 是为 hash 稳定性必需的最小 schema 扩大,与 content_hash 同属这**一个**授权改动,一并纳入
  > 冻结区例外;除这两字段 + `compute_evidence_content_hash` 外,不动 gateway evidence schema。
- 新增伴生纯函数(与 `EvidenceRecord` 同模块,保证本地/远端同算法):
  ```python
  def compute_evidence_content_hash(record: EvidenceRecord) -> str
  ```
  返回 `"sha256:" + hexdigest`。**输入仅 §3 列的语义正式字段**(含
  `normalized_public_base_url`),排除时间戳、api_key、随机 evidence_id、随机本地
  endpoint_id、任意 `metadata`。
- 不动 `new_evidence_id`(保留随机 id 生成),不动 `state_projection` 契约。
- 影响:gateway 现有测试需确认 `EvidenceRecord` 加可选字段不破坏序列化/校验
  (新增字段有默认值,向后兼容)。

### 2.2 studio credentials schema(v4 → v5)

文件:`apps/studio/backend/app/models/llm_config.py`

- `LLMCredentialsFile.schema_version: Literal[4] = 4` → `Literal[5] = 5`。
- `LLMCredentialsFile` 顶层新增:
  ```python
  last_remote_catalog_sync: RemoteCatalogSyncMarker | None = None
  ```
  其中 `RemoteCatalogSyncMarker(BaseModel)` 仅 3 个标量:
  `etag: str | None`、`generated_at: str | None`、`last_synced_at: str | None`。
  (P6/R1.4:极小 metadata,禁止存完整 cache / queue / receipt 历史。)
- `ProviderRoute(GatewayProviderRoute)` 子类新增:
  ```python
  evidence: list[EvidenceRecord] = Field(default_factory=list)
  ```
  evidence 单条复用 gateway `EvidenceRecord`(已带 content_hash),满足"格式与
  catalog 同构"。
- `_gateway_route()`(`llm_config.py:99`)的 `exclude` 集合加入 `"evidence"`——
  gateway runtime route 不认 Studio-only 的 evidence(与 `display_name` 同处理)。
- `evidence_refs` 不再作为持久化字段;`route.metadata["evidence_refs"]` 仅作
  迁移读取来源,不再写。

### 2.3 schema 迁移(v4 → v5,加载即升级)

- credentials 加载器(`app/services/llm_credentials.py:load_credentials`)对
  `schema_version == 4` 的文件做就地升级:补 `evidence=[]`、
  `last_remote_catalog_sync=None`、版本号→5。纯结构升级,不触网。
- 真正的 evidence 数据回填由 §7 的一次性 legacy 迁移完成(可触文件,不触网)。

## 3. content_hash 定义(R2.1)

确定性输入(canonical JSON,`sort_keys=True, ensure_ascii=False`):

| 字段 | 取值 | 说明 |
| --- | --- | --- |
| `evidence_type` | record.evidence_type | probe / model_list_observation / ... |
| `trust_state` | record.trust_state | probe-verified / probe-failed / ... |
| `normalized_public_base_url` | record.normalized_public_base_url(**正式字段**) | endpoint 公网身份;本地从 credentials endpoint 规范化填、远端 parse 时填,跨机一致 |
| `provider_model_id` | record.provider_model_id | |
| `model_id` | record.model_id | |
| `method_id` | record.method_id | official call method,可空 |
| `request_mapper_id` | record.request_mapper_id | 可空 |
| `probe_status` | record.probe_status | ok / invalid_model / ... |
| `capability_family` | record.capability_family | 可空 |

- 算法:`content_hash = "sha256:" + sha256(canonical.encode()).hexdigest()`。
- **排除**:`observed_at`/`attempted_at`(时间戳)、`api_key`、`evidence_id`、本地随机
  `endpoint_id`、`display_name`、任意 `metadata`。注意 endpoint 公网身份用的是 R2.1 升级后的
  **正式字段** `normalized_public_base_url`(不读 `metadata`),故"排除 metadata"与"hash 含
  endpoint 身份"不再矛盾(problem 3 的修复点)。
- 结果:同语义 evidence 跨多次 Test / 跨机器 / 本地↔远端 hash 一致(R2.1-AC1),
  任一语义字段不同则 hash 不同(R2.1-AC2)。

## 4. 统一 evidence 访问服务(读 + 写,P7)

> SSOT 的执行结构:`app/services/llm_credentials_evidence.py` 是 evidence 的**唯一一道门**
> ——既 owns 写(merge),也 owns 所有读查询(scope 化)。外部一切读写只经它,门内只碰
> credentials(`route.evidence` / `provider_routes`),从构造上保证 research §4 读者表里
> 的"接门"项不再触 catalog;"溶解"项根本不调它(直接取 routes)。**早先只设计了写门
> 而散落读侧,正是 Phase 4 反复补洞的根**(见 research §4 更正)。

### 4.1 写入门:merge_route_evidence(R2.2/R3.1 核心)

```python
def merge_route_evidence(route: ProviderRoute, record: EvidenceRecord) -> ProviderRoute
# 1) 计算/回填 record.content_hash
# 2) 在 route.evidence 中按 content_hash 查重:
#    - 命中 → 用新 record 替换(保留较新的 observed_at)
#    - 未命中 → append
# 3) 返回更新后的 route(不可变风格 model_copy);调用方必须把返回值赋回
#    credentials.provider_routes[route_id](never mutates,见 §5 codex-1)
```

- 所有 Test/probe/sync/migration 写入 evidence **只走这一个 helper**,保证去重一致。
- **成功(probe-verified)与失败(probe-failed)都经它写**(R3.1-AC3),失败本体留存供诊断、
  不投蓝(§4.3)。
- 可选保险上限:每 route evidence 上限(如 64 条);超限时按 observed_at 淘汰最旧的
  非 verified evidence(避免无界增长,P4)。

### 4.2 读门:scope 化查询(R9,replace 散落的 load_evidence_library)

同一服务暴露所有 evidence 读查询,**逐个替换 research §4 读者表里的"接门"项**;门内只读
credentials,正常运行不再 `load_evidence_library()`:

```python
# 已在 app/services/llm_credentials_evidence.py 实现(T4a,红→绿):
def route_is_probe_verified(route) -> bool              # R9.3 替 llm.py:4507
def route_probe_history(route) -> list[EvidenceRecord]  # 诊断/last-result(probe verified+failed)
def probe_evidence_counts(credentials) -> ProbeEvidenceCounts  # R9.2,**只数 probe 类**(legacy observation 不计)
def collect_uploadable(credentials) -> list[EvidenceUpload]    # R9.1/R5;排除 community-provenance + **无 fingerprint(非公网/空)**
def endpoint_listed_model_ids(credentials, endpoint_id) -> list[str]  # R3.4 routes=model-list 真相,替 known_model_ids_for_endpoint
def endpoint_probe_priority(credentials, endpoint_id, candidates) -> list[str]
    # R9.4 **4 档**:当前 verified route(green)→ historical probe-verified(blue)→ unknown → failed 最后。
    # 镜像 llm.py:_endpoint_probe_order;**不跳过 verified**——跳过是 gateway probe_priority 的"发现新能力"
    # 排序,endpoint Test 要的是"用已知好模型最快确认 endpoint"(Qiniu 修复逻辑)。tier 由 route.status + route.evidence 派生。
# 投影 refs:`route_projectable_refs` 当前是 adapter 的 `_route_credential_evidence_refs`(Phase 3 已对齐),T4c 统一进本服务。
```

- **溶解项不进这道门**(R3.4/R9):endpoint 列出的 models = `credentials.provider_routes`
  下该 endpoint 的 routes(`endpoint_listed_model_ids` 只对 routes 过滤,不读 evidence);
  model-list 的 added/removed/unchanged 是 routes 快照 diff → runtime activity 诊断。
- **gateway 侧的第二条读路径**(`role_materialization._route_credential_evidence_refs`)因
  KEEP-MAIN 不能 import studio,保留其 duck-typing 同算法实现;§4.3 锁两条对齐。

### 4.3 投影 refs 派生(R6,读门的一种,两条读路径对齐)

文件:`apps/studio/backend/app/core/adapters/gateway.py:403 _route_credential_evidence_refs`

```python
def _route_credential_evidence_refs(self, route) -> list[str]:
    return [
        ev.content_hash or ev.evidence_id
        for ev in getattr(route, "evidence", []) or []
        if ev.trust_state in PROJECTABLE_TRUST_STATES   # 仅"正向"evidence
    ]
```

- `PROJECTABLE_TRUST_STATES = {"probe-verified"}` **仅此一个**(problem 4 收紧):本地
  probe-verified 与远端 community probe-verified 都是这个 trust_state,故都能投蓝。
  **`provider-list-observed` / `probe-failed` / `stale` / `deprecated` 一律不投蓝**——
  严格沿用 community-probe-catalog-service-phase2a `requirements.md:43`
  ("provider-list-observed never contributes to historical_ready")。
- gateway `project_route_state` 入参/逻辑完全不变(R6.3):仍是"refs 非空 +
  credential_available → historical_ready"。变化只在 refs 来源:
  `route.metadata["evidence_refs"]` → `route.evidence` 派生。
- failed evidence 仍保留在 `route.evidence` 中,供 UI 展示 last-result / 诊断,但
  不进 refs。
- **两条读路径必须对齐**:`evidence_refs` 在 gateway 调用链上有**两个**派生点——(1) Studio
  adapter `core/adapters/gateway.py:_route_credential_evidence_refs`(UI 投影);(2) gateway SDK
  `role_materialization.py:_route_credential_evidence_refs`(fallback_chain 物化)。**两者都必须从
  `route.evidence` 的 probe-verified 派生**。只改其一会留暗坑:endpoint-failed + probe-verified
  `route.evidence` 的 route 会 UI 投蓝、却被 role 物化当 failed 跳过(fallback_chain 空洞,Phase 3 实测)。
  gateway SDK 用 duck-typing(`_value`)读 `route.evidence`,materialize_role 收到的是 Studio route
  (带 evidence、不经 filter strip),故读得到。

## 5. Test 流程改造(R3)

文件:`apps/studio/backend/app/routers/llm.py`(`test_endpoint` / `test_endpoint_models`
/ `probe_route` / promotable update)。

| 现状(坏) | 改为 |
| --- | --- |
| `_append_model_probe_evidence` → probe catalog (`llm.py:3025`,调用 867/904/1176) | 构造 `EvidenceRecord`(成功 `probe-verified` / 失败 `probe-failed`)→ `merge_route_evidence`,返回值**赋回** `credentials.provider_routes[id]` |
| `_append_official_profile_probe_evidence` → probe catalog (`llm.py:2955`,调用 1054 手动 + 2866/2876 role-test) | 同上。手动 Test 与 role-test profile-ensure **共用此写者**,改的是 sink 不是编排;`_ensure_official_role_test_verified_profile` 的 profile persist + evidence **同一次 `save_credentials`**(R3.3-AC2) |
| `_append_model_list_observation_evidence` → probe catalog (`llm.py:3079`,调用 815) | **溶解**(R3.4/§5.1):**不再产 evidence**;added/removed/unchanged → runtime activity;`previous_model_ids` 从 credentials 现有 routes 取 |
| `_apply_cached_community_evidence(latest_credentials)` (`llm.py:920/2161`) | **删除**(R3.2):Test 不再从 community cache promote |
| promotable update 写 `metadata["evidence_refs"]` (`llm.py:5392`,5411-5421) | **整体退役**(R9.5,no backward compat):删 `_apply_promotable_route_update` + `_upsert_discovered_routes` 对它的调用,不再 `load_evidence_library()` 推 route 的 capabilities/profiles/refs。**不做 catalog→route.evidence 的 legacy bridge**;capabilities/profiles 只来自本次 Test(SSOT),蓝色只来自 `route.evidence`(§4.3) |

- Test 仍按现有"重读 latest_credentials → 校验 fingerprint → 更新 route/status →
  `save_credentials`"骨架;evidence 在同一次 save 落盘(R3.3),不引入额外中间写。
- runtime activity:`endpoint_test` 不再带 `promoted_catalog_records`;evidence 写者的
  `source_id` 从 `llm_probe_catalog` 改为 `llm_credentials`;model-list 的 added/removed/
  unchanged 改进 runtime activity 诊断(R3.4,不再是 evidence)。
- **失败 evidence(codex-3,R3.1-AC3)**:official profile probe 的失败本体现已产出
  (`llm.py:2875-2880`),只需改落点经 merge 写 credentials。但**第三方 endpoint probe**
  `_verify_third_party_endpoint_by_probe`(`llm.py:4933+`)失败时**只返回 message、不带回失败
  `RouteProbeResult`**(`ThirdPartyEndpointVerification` 无失败结果字段);需**扩展其返回**带回
  失败 probe 结果,Test 失败路径据此 `merge_route_evidence` 写 `probe-failed`。

### 5.1 model-list 溶解进 routes(R3.4,problem 6,已拍板)

> 早先此处写"每 route 存一条 `provider-list-observed` evidence",**已废弃**——那既丢了
> endpoint 级的 removed 语义,又为删一个 catalog truth 而造一份 route evidence truth,违背
> 最小结构。正解:**model-list 真相就是 routes 本身**,不另存 evidence。

- endpoint 当前列出的 models = `credentials.provider_routes` 下该 endpoint 的 routes;每个
  列出的 model 已落成一条 route,**无需平行的 observation evidence**。
- added / removed / unchanged = 两次 routes 快照的 diff,是**诊断**,进本次 Test 的 runtime
  activity,不是 truth。
- `previous_model_ids`(原 `llm.py:3085` 读 `library.route_candidates`)改从 credentials 现有
  routes 取。
- legacy 里已有的 `provider-list-observed` evidence:§7 迁移与读侧做**防御性容忍**(可读、可
  忽略),但**不投蓝、不上传、不作为正常写入目标**(沿用 `is_uploadable=False` + §4.3 只认
  probe-verified)。

## 6. 远端同步改造(R4)

### 6.1 下载 verified catalog → 直接 merge 进 credentials

文件:`app/services/community_catalog_runtime.py:sync_verified_community_catalog_into_credentials`
+ `merge_community_evidence_into_credentials`(合并逻辑在 runtime;`community_catalog.py` 是纯
wire/privacy/mapping 工具层,旧 `apply_community_evidence_to_credentials` 已删)。

- 保留拉取 + Ed25519 验签 + shard SHA256 + protocol 校验(fail-closed,R4.1-AC2),
  这些来自 `community_catalog_sync.sync_verified_catalog`,**只去掉写 cache 文件那步**。
- 验签通过后:`parse_catalog_evidence(wire)` → `EvidenceRecord` → 按 route 匹配
  (复用现有 `(host, provider_model_id)` 匹配,`community_catalog.py:271-288`)→
  `merge_route_evidence` 写进 credentials(content_hash 去重)。
- `merge_community_evidence_into_credentials`(runtime):不写 `metadata["evidence_refs"]`
  + `community_evidence` marker,改为 merge 进 `route.evidence`(旧 `apply_*` 写法已删)。
  **每条远端 evidence 必须带 `metadata["provenance"]="community"`**
  (`parse_catalog_evidence` 已设此值,community_catalog.py:222)——这是 §8 上传侧排除
  回环(problem 5)的依据,也供 UI 区分本地/社区来源。
- 同步末尾更新 `credentials.last_remote_catalog_sync`(etag/generated_at/
  last_synced_at),`save_credentials` 一次。
- 退役:`DisposableCatalogCacheStore` / `CommunityCatalogCache` 不再写;仅 §7 迁移读。
- 无匹配本地 route 的远端 evidence 忽略(R4.1-AC3)。

### 6.2 startup 同步

文件:`app/main.py:57-90`。

- `_sync_verified_community_catalog_on_startup`:保留,但走 §6.1 的"merge 进
  credentials"路径(不写 cache)。
- `_sync_remote_probe_catalog_on_startup`(旧 remote probe catalog →
  `llm_probe_catalog.json`,`main.py:76-83`):**停用/移除**(R4.2)。其内存
  `RemoteCatalogSourceMetadata` 链路一并退役。
- 新增:在 startup 调用一次 §7 的 legacy 迁移(幂等、best-effort)。

### 6.3 endpoint Test 后触发 verified sync(problem 6,补"先 sync 后建 route")

删掉本地 community cache 后,"先 sync 后建 provider/route"不再能靠 cache 暂存 + Test carry
补蓝。改由**触发点**补回(R4.3):

- `test_endpoint` 成功落盘后,best-effort 触发一次 `sync_verified_community_catalog_into_credentials`
  (§6.1 路径),把匹配刚建/验证 route 的远端 verified evidence merge 进 credentials。
- best-effort:与 `_autoshare_after_probe_best_effort` 同款——包在 try/except,失败仅 log,
  绝不影响 endpoint Test 结果。
- 这无缝替换旧的"Test 时从 community cache carry 已下载 evidence"能力(原
  `test_endpoint_test_carries_cached_community_evidence_for_new_routes` 覆盖的场景)。
- 显式 sync API(`/catalog/sync-verified`)保留,供用户手动刷新。

## 7. Legacy 一次性迁移(R8)

新增 studio 模块(建议 `app/services/llm_legacy_evidence_migration.py`):

```python
def migrate_legacy_catalog_evidence_into_credentials() -> MigrationReport
```

- 读 `llm_probe_catalog.json`(`ProviderImportDraft.evidence_records`)+
  `community_catalog_cache.json`(`CommunityCatalogCache.records`)。
- 每条 evidence → 计算 content_hash → 按 route 匹配(host+provider_model_id /
  route_id)→ `merge_route_evidence` 写 credentials。
- 幂等:content_hash 去重,重复运行不增条目(R8-AC1)。
- 无匹配 route 的忽略(R8-AC2);任何异常仅 log,不阻塞启动(R8-AC3)。
- 迁移成功后两文件不再被读写;用户可删(远端有备份)。可选:迁移后重命名为
  `*.migrated` 或记一个 marker,避免每次启动重扫(非必须,因迁移本身幂等)。

## 8. 上传改造(R5)

文件(Phase 6 实改):`app/services/community_catalog_upload.py`(删 queue 机理)+
`app/routers/llm.py`(`_autoshare_after_probe_best_effort` / `contribute`)。

- 上传候选函数 = `llm_credentials_evidence.collect_uploadable(credentials)`(读门,**已在
  Phase 4/T4c 落地**):遍历 `credentials.provider_routes[*].evidence`,筛 `is_uploadable(ev)`
  (probe + probe-verified)且 `metadata.provenance != "community"`(problem 5 排回环)且
  endpoint 有 fingerprint(非公网/空被弃,R5.1-AC2),`build_upload_record(ev, base_url=endpoint.base_url)`
  脱敏。不再 `load_evidence_library()`、不读 probe catalog / community cache 做 diff。
  （旧 `community_catalog_upload.collect_uploadable_uploads(library, credentials)` 是 library 版,
  Phase 6 作为死代码删除。）
- 调用点(autoshare/contribute)已传 `collect_uploadable(load_credentials())`。
- **只上传本地产生的 evidence**(problem 5 / R5.1-AC3):远端 merge 进来的 community evidence
  带 `metadata.provenance="community"`,collect 时显式排除——否则下载的 probe-verified
  evidence 会被当本地 probe 再传回远端,形成回环放大。`is_uploadable` 只看 type+trust、不看
  provenance,故排除在 collect 侧加。
- 幂等(problem 1 拍死,**不留"或"**):`batch_idempotency_key` = **整条 sanitized `EvidenceUpload`
  payload 的稳定 JSON 派生 sha256**(每条 `model_dump(mode="json")` 排除时间戳 `observed_at`、
  `sort_keys`,batch 按规范化串稳定排序 → 顺序无关),**不再手写四元组**——否则同 endpoint+model+method
  下 `request_mapper_id`/`capability_family`/`model_type`/`input/output_modalities`/`probe_status`/
  `normalized_public_base_url` 变了 key 不变,远端会误判幂等去重(drift,已修)。key 纯从脱敏 payload 派生
  (不含 credential secret / 本地路径),故从 credentials 重派生稳定不变。配合 gate 现有 record 级去重。
  **不改 wire schema、不给 `EvidenceUpload`/gate 加 content_hash 字段**(P3/§9:不改远端协议);
  `content_hash` 只用于本地 credentials 去重(R2.2),不进 wire(R5.2)。
- **移除 `OfflineUploadQueue` 作为持久化重试队列**(P4/R5.2,**Phase 6 已实现**):`upload_batch` 去
  `queue` 形参、失败 `raise CommunityUploadError`,不落本地 queue;下次 Test/contribute 从 credentials
  重派生候选(候选集稳定 → `batch_idempotency_key` 稳定 → 远端幂等不重复计数)。contribute 失败回
  `status:"failed"`(非 `deferred`/`queued`),如实说"留在 credentials、下次重派生重试"。
  `OfflineUploadQueue`/`QueuedBatch`/`DrainResult`/`UploadDeferred`/`drain_queue` 全删;
  `community_upload_queue.json` 运行期不再写(startup 仍播 inert 空文件,Phase 9 退役整文件 + 显示)。

## 9. 空 Base URL 守卫(R7,本 session 已实现,补测试锁定)

- gateway `provider_probe.py`:空 base_url → endpoint/route probe 返回
  `status="error"` + `error_code="missing_config"`,不发 HTTP(已实现)。
- studio legacy endpoint probe adapter(`llm.py`):同样 missing_config 守卫(已实现)。
- 本 spec 只补 R7 测试,锁定"空 base_url slot 可入 credentials,但执行层不出网"契约。

## 10. 关键决策与替代方案

- **D1 evidence 落点 = route 内嵌(选 A)**,单条 = gateway `EvidenceRecord`(格式与
  catalog 同构)。替代 B(顶层去重 list + refs)同步时 list↔list 更省一步,但要管理
  孤儿 evidence、投影要 join;route 内嵌让"删 route 自动清理、O(1) 投影、无游离
  数据",更贴 SSOT。同步所需的 flatten(credentials→候选)/scatter(catalog→route)
  是两个确定性纯函数,成本低。**采用 A。**
- **D2 content_hash 放 gateway**:用户授权;且 content_hash 是 evidence 固有属性,
  本地与远端必须同算法,放 gateway 与 `EvidenceRecord` 同源最稳。
- **D3 本地去重键 = content_hash;远端幂等 = 现有 `batch_idempotency_key`**(problem 1,
  不改远端协议)。`evidence_id` 保留为不透明 id(迁移的旧随机 id 不强改);content_hash 不进 wire。
- **D4 移除 OfflineUploadQueue**(见 §8),失败重派生。行为变化,已在 spec 标注。
- **D5 失败 evidence 留存但不投影蓝**(§4.3),用于 UI last-result/诊断。

## 11. KEEP-MAIN 边界与改动清单

gateway(冻结区,获授权最小改动):
- `registry/schema.py`:`EvidenceRecord` 加 `content_hash` + `normalized_public_base_url`
  两字段 + `compute_evidence_content_hash`(problem 3)。**两字段同属为 content_hash 稳定性必需
  的最小扩大,纳入 KEEP-MAIN 冻结区例外**(理由见 §2.1);不做其它 gateway evidence schema 改动。
- `resolver.py:_assert_v4_credentials`:放行 `schema_version in {4,5}`(原仅 `== 4`)。**credentials
  有两个 loader**——studio `load_credentials` 与 gateway `resolver`(后者在 endpoint Test 等走
  gateway 解析的路径上加载 credentials)。schema v4→v5 升级**必须同时放行这两道闸**,否则 gateway
  侧这道闸先拒(实测整条 Test 链路 422)。属 schema 升级的必然连带,纳入冻结区例外。
  - **gateway route 不吃 studio-only 字段(problem 2 修正)**:Studio 所有 gateway 入口
    (`engine.py` / `core/adapters/gateway.py` / `services/gateway_resolver.py`)在喂
    `RegistrySnapshot` 前都先经 `_filter_gateway_credentials` 把 `display_name`/`evidence` 等
    strip 掉(其 `route_keys` 白名单不含它们),gateway `ProviderRoute`(extra=forbid)因此不会被
    evidence 撞崩。契约是「Studio→gateway 入口必先 filter」,由测试锁定。**上轮我误述为
    'RegistrySnapshot 有容忍机制',实为入口 filter** —— 二者后果相同(resolver 拿到的永远是
    filtered route),但机制不同,据实更正。
- `role_materialization.py:_route_credential_evidence_refs`(Phase 3 / problem 4):从
  `route.metadata["evidence_refs"]` 改为 `route.evidence` 的 probe-verified 派生——evidence_refs 的
  **第二条读路径**(第一条是 Studio adapter 同名 helper);两条必须对齐,否则 endpoint-failed +
  probe-verified `route.evidence` 的 route 会 UI 投蓝却被 role 物化跳过(fallback_chain 空洞,见 §4.3)。
  gateway SDK duck-typing(`_value`)读,materialize_role 收到的是 Studio route(带 evidence、不经 filter)。

studio(`apps/studio/backend`,主战场):
- `models/llm_config.py`:schema v5、`ProviderRoute.evidence`、`RemoteCatalogSyncMarker`、`_gateway_route` exclude。
- `services/llm_credentials.py`:v4→v5 加载升级 + `validate_credentials_payload`(统一"升级+校验"入口,P1)。
- `core/adapters/engine.py` + `core/adapters/gateway.py`(P1):所有 credentials validate 入口改走
  `validate_credentials_payload`,杜绝某入口裸 `model_validate` 把磁盘 v4 静默吞成空 credentials。
- `services/llm_credentials_evidence.py`(新):**evidence 访问服务**(§4)——写门
  `merge_route_evidence` + 读门 scope 化查询(`route_projectable_refs` /
  `route_is_probe_verified` / `route_probe_history` / `collect_uploadable` /
  `probe_evidence_counts` / `endpoint_probe_priority`)。
- `core/adapters/gateway.py`:`_route_credential_evidence_refs` 改从 route.evidence 派生。
- `routers/llm.py`(主改面):
  - **写者**接写门:probe 成功/失败、official profile(手动+role-test 共用)经 merge 赋回 credentials;
    删 `_apply_cached_community_evidence`;promotable 运行期链路**整体退役**(R9.5,no backward
    compat:删 `_apply_promotable_route_update` + 调用 + `load_evidence_library` promote 读);
    model-list **溶解**(R3.4)。
  - **读者**接读门或溶解(R9):上传/分享 192/602/663、summary 2169、model 状态 4507、
    probe 排序 4833 全改 credentials 派生;`/catalog/sync`(532)退役。
  - **失败 evidence**:第三方 `_verify_third_party_endpoint_by_probe` 扩展返回带回失败结果,
    失败路径写 `probe-failed`(codex-3)。
- `services/community_catalog.py` / `community_catalog_runtime.py`:下载 merge 进 credentials,不写 cache。
- `services/community_catalog_upload.py`:`collect_uploadable_uploads(credentials)`、移除 queue 依赖。
- `services/llm_legacy_evidence_migration.py`(新):一次性迁移。
- `services/runtime_truth_init.py`(problem 7):`ensure_runtime_truth_sources` 不再创建退役的
  `llm_probe_catalog.json` / `community_catalog_cache.json` / `community_upload_queue.json`
  (现状 `runtime_truth_init.py:103-126` 在主动建这三文件);只保留 credentials / roles /
  role-test-results / canonical-rules / activity-log 等仍在用的 truth source。
- `services/runtime_truth_sources.py`(problem 7):设置页 truth-source 列表的 "catalog"
  section(`runtime_truth_sources.py:169-211`)移除或标注这三个退役文件,避免 UI 仍把它们
  当 truth 展示。
- `main.py`:startup 接线(留 verified sync 走新路径、停旧 probe catalog sync、加 §6.3 的
  Test 后触发、加一次性迁移)。

## 12. 风险与回滚

- **R-A 远端无匹配 route**:verified evidence 当次无落点 → 忽略(不创建游离 route)。
  与现状"cache 先存着、Test 时再 carry"不同,但**不丢能力**:§6.3 让 endpoint Test 成功后
  best-effort 触发一次 verified sync,用户"先 sync 后建 route"时,建好/验证 route 的那次
  Test 会把匹配的远端 evidence 拉进来补蓝(R4.3)。代价:依赖一次"建 route 后的 sync 命中",
  而非本地 cache 暂存。若产品要"先到先存"再另设 pending(本 spec 不引入,符合 P4)。
- **R-B evidence 体积**:route 内嵌 + 去重 + 可选上限控制无界增长;迁移大文件时
  一次性 merge 需注意性能(可分批)。
- **R-C 回滚**:schema v5 向后不兼容 v4 读取(v4 加载器不认 evidence/marker);回滚
  需保留 v5→v4 降级或保留迁移前 credentials 备份。迁移前对 credentials 做一次
  `.bak` 备份(实现阶段加)。
