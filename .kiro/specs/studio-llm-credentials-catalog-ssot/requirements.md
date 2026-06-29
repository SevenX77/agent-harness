# Requirements — Studio LLM credentials/catalog SSOT 重构

> 本文件锁"做什么"与"必须满足的契约",不写实现。实现见 `design.md`,审计见
> `research.md`。所有需求以可验收标准(Acceptance Criteria, AC)表述,供 TDD 直接转成测试。

## 0. 锁定原则(不可动摇)

- **P1 — credentials 是 UI 唯一运行期真相源**。`llm_credentials.json` 持有
  credentials + route runtime status + **evidence 本体**。UI/registry 的任何状态
  (含蓝色 `historical_ready`)只能从 credentials / registry response 投影。
- **P2 — catalog 是远端交换格式,不是本地 truth**。`llm_probe_catalog.json` 与
  `community_catalog_cache.json` 不再作为运行期 truth/cache;仅允许一次性
  migration/import,迁移后不再被正常 Test/sync 写入,可删除。
- **P3 — evidence 内部统一为单一 `EvidenceRecord` 模型;与远端之间保留 wire 映射**。
  credentials 内嵌的 evidence、本地 probe 产生的 evidence、远端下载后转回的 evidence
  都收敛为同一个内部 `EvidenceRecord`(带 `content_hash`),消除"本地 probe library ↔
  credentials"之间的格式转换——这是本 spec 真正要砍的那层。与远端 community gate 之间
  **仍保留既有 wire 映射**:上传 sanitize 成 `EvidenceUpload`(脱敏 allowlist 子集)、
  下载 `parse_catalog_evidence` 转回 `EvidenceRecord`;远端协议不改(见 §9)。
  `content_hash` 是**本地**稳定幂等键(credentials 去重 + 上传候选集稳定);它**不进 wire**,
  远端幂等沿用现有 `batch_idempotency_key`,不改远端协议(见 P5/§9/design §8)。
- **P4 — 写一次 truth**。Test/probe 一次性把结果(routes/models/evidence)落
  credentials;上传失败不把 pending queue 塞回 credentials,下次从 credentials
  重新派生候选。
- **P5 — content_hash 是本地稳定键;远端去重不改协议**。`content_hash` 由内容确定性算出,
  用于**本地**:credentials 内同 route 去重(R2.2)+ 保证从 credentials 派生的上传候选集稳定。
  **远端去重沿用现有机制**:本地 `batch_idempotency_key`(整条 sanitized upload payload 的稳定 JSON
  批次键,排除 `observed_at`)+ gate 现有 record 级去重;**不**给 wire/gate 新增 content_hash 字段
  (P3:不改远端协议)。
- **P6 — 本地不做 catalog diff**。不用本地 community cache 比对远端;远端验签后
  直接 merge,本地只在 credentials 存极小的 last-sync metadata。
- **P7 — 读写对称:所有运行期 evidence 读者也只认 credentials**。SSOT 不是"写进去
  就行"——evidence 的**每一次读**都必须经 credentials evidence 访问层从
  `route.evidence` 派生;正常运行**不得**读 `llm_probe_catalog.json` /
  `community_catalog_cache.json`(见 research §4 读者表)。要 routes 而非 evidence 的
  读者(model 发现、列表计数)直接从 `provider_routes` 取(**溶解**),不在 credentials
  另造一份 evidence。`load_evidence_library()` 仅 §8 一次性迁移可读。
- **P8 — 不向后兼容,旧 catalog 数据可清空**。最新决策:`llm_probe_catalog.json` /
  `community_catalog_cache.json` / `metadata["evidence_refs"]` 的历史数据**可直接清空**,
  **不做 catalog→credentials 的 legacy bridge**。两个推论:(a) promotable 运行期链路整体
  退役(R9.5),不再从 catalog 推 route 的 capabilities/profiles/refs;(b) §8 的 legacy 迁移
  (R8)**降级为可选**——既然旧数据可弃,正常落地可"清空而非迁移",迁移仅在确需保留历史时才跑。

## 1. credentials schema 承载 evidence(P1, P3)

**R1.1** `LLMCredentialsFile.schema_version` 从 `4` 升到 `5`。

**R1.2** `ProviderRoute` 新增正式字段 `evidence: list[EvidenceRecord]`(默认空 list),
作为该 route evidence 本体的唯一持久化处。
- **AC1**:加载/保存一个含 `evidence` 的 v5 credentials 往返(load→save→load)后,
  `route.evidence` 内容与 content_hash 完全一致、顺序稳定。
- **AC2**:`route.evidence` 内每条都是合法 `EvidenceRecord`(可被 gateway 模型校验)。

**R1.3** evidence 本体不再依赖 `route.metadata["evidence_refs"]` 作为存储;
`evidence_refs`(若仍出现在 response)只能是从 `route.evidence` **派生**的投影产物。
- **AC1**:删除一个 route 后,它的 evidence 随之消失,credentials 中不留游离 evidence。

**R1.4** credentials 顶层新增极小的远端同步 metadata(P6),仅含
`etag / generated_at / last_synced_at`(可为 null),**不得**存完整远端 catalog cache、
pending upload queue、或大量 receipt 历史。
- **AC1**:一次远端 verified sync 后,credentials 顶层 metadata 只更新这三个标量,
  字节增量为常数级(不随 catalog 记录数增长)。

## 2. evidence 的稳定身份 content_hash(P5)

**R2.1** `EvidenceRecord` 新增两个字段:`content_hash` 与 `normalized_public_base_url`
(endpoint 公网身份升为正式字段,不再只藏在 `metadata`)。`content_hash` 由 evidence 的
**语义正式字段**确定性算出(含 `normalized_public_base_url` / `provider_model_id` /
`method_id` / `request_mapper_id` / `probe_status` / `trust_state` 等),**不含**
api_key、随机 uuid、本地随机 endpoint_id、observed_at/attempted_at、任意 `metadata`。
本地构造 evidence 时从 credentials endpoint 规范化填 `normalized_public_base_url`,远端
`parse_catalog_evidence` 时填同字段,使本地↔远端算出同一 hash。
- **AC1**:对同一语义的两条 evidence(同 endpoint 公网身份 + provider_model_id +
  method + probe_status,仅时间戳不同),`content_hash` 相等。
- **AC2**:任一语义字段不同 → `content_hash` 不同。

**R2.2** credentials 内同一 route 的 evidence 按 `content_hash` 去重:写入同 hash 的
evidence 时替换旧条(保留最新 observed_at),不追加重复。
- **AC1**:同一 route 连续两次产生同语义 probe-verified evidence,`route.evidence`
  中该语义只保留 1 条,且 observed_at 为最新。

## 3. Test 流程只写 credentials(P1, P4)

**R3.1** endpoint Test / manual model Test / route probe / official profile probe 产生的
probe evidence(**成功 `probe-verified` 与失败 `probe-failed` 都算**),**直接 append 到
对应 route 的 `credentials.provider_routes[route_id].evidence`**(按 R2.2 去重),不再写
`llm_probe_catalog.json`。model-list observation **不再产 evidence**(见 R3.4 溶解)。
- **AC1**:跑一次第三方 endpoint Test(get-models + probe 成功),其后
  `route.evidence` 含至少一条 probe-verified evidence;`llm_probe_catalog.json`
  **不被创建/写入**(文件不存在或 mtime 不变)。
- **AC2**:跑一次 manual model Test(official 与第三方各一例),对应 route 的
  `evidence` 含本次结果;probe catalog 文件不被写。
- **AC3(失败也是 evidence,problem codex-3)**:第三方 endpoint Test **get-models
  成功、但 generation/protocol probe 失败**时,失败模型对应 route 的 `evidence` 含一条
  `probe-failed` evidence;该 route 不投蓝(§6),但失败本体落 credentials 供诊断。
  (official profile probe 的失败本体现已产出,见 `llm.py:2875-2880`,只需改落点;
  第三方 probe 失败链路当前**不带回失败结果**,需补。)
- **AC4(route-probe)**:`/routes/{route_id}/probe?force=true` 触发的 route probe,
  成功/失败结果都 append 到该 route 的 `evidence`,probe catalog 不被写。

**R3.2** endpoint Test **不得**从 `community_catalog_cache.json` promote evidence 到
credentials(删除 `_apply_cached_community_evidence` 链路)。
- **AC1**:即便 `community_catalog_cache.json` 存在且含匹配 records,跑 endpoint
  Test 后 credentials 的 evidence **只**来自本次 Test,不含来自 cache 的记录;
  runtime activity 不再出现 `promoted_catalog_records`。

**R3.3** Test 一次性保存 truth:routes/models/route.status/evidence 在同一次
`save_credentials` 落盘。
- **AC1**:Test 成功路径中 credentials 落盘次数与现状契约一致(不因 evidence 改动
  引入额外的中间态写)。
- **AC2(official role-test profile)**:`_ensure_official_role_test_verified_profile`
  的 profile persist 与 profile-probe evidence(成功/失败)在**同一次 `save_credentials`**
  落 credentials,不得 profile 落 credentials、evidence 落 catalog 两段写。

**R3.4(model-list 溶解进 routes,problem 6,已拍板)** model-list observation **不再写
`provider-list-observed` evidence**,也不在 credentials 造 endpoint-level observation truth:
- endpoint 当前列出的 models = 该 endpoint 下的 `provider_routes`(列表即真相,无需另存)。
- added / removed / unchanged → 本次 Test 的 **runtime activity 诊断**(非 truth)。
- `previous_model_ids` 从 **credentials 当前 routes** 取,不再读 `llm_probe_catalog.json`
  的 `route_candidates`。
- legacy 里已有的 `provider-list-observed` evidence:迁移/读侧做**防御性**处理(可读、可
  忽略),但**不投蓝、不上传、不作为正常写入目标**。
- **AC1**:跑一次 endpoint Test(get-models 返回新增 + 移除若干 model),credentials
  不出现任何 `provider-list-observed` evidence;added/removed 出现在该次 runtime activity。
- **AC2**:删空 `llm_probe_catalog.json` 后再跑 Test,added/removed 仍据 credentials 现有
  routes 正确算出(previous 来源是 routes,不是 catalog)。

## 4. 远端下载:验签后直接 merge 进 credentials(P1, P2, P6)

**R4.1** `sync_verified_community_catalog`(startup + API 触发)拉远端 verified catalog,
完成 Ed25519 验签 + shard SHA256 + protocol 版本校验后,把 verified evidence
(`EvidenceRecord`)按 route 匹配**直接 merge 进 credentials 对应 route 的 evidence**
(按 R2.2 去重),并更新 R1.4 的 last-sync metadata。**不写**
`community_catalog_cache.json`。
- **AC1**:配置好 manifest+pubkey、本地已有匹配 route 时,一次 sync 后该 route 的
  `evidence` 含远端 verified evidence;`community_catalog_cache.json` 不被创建/写。
- **AC2**:验签/分片/协议校验失败时 fail-closed:credentials 完全不被改动,且抛出
  对应错误(沿用现有 `VerifiedSyncError` 家族语义)。
- **AC3**:远端无匹配本地 route 的 evidence 被安全忽略,不在 credentials 留游离条目。

**R4.2** 旧 remote probe catalog 链路(`_sync_remote_probe_catalog_on_startup` →
`llm_probe_catalog.json`)在正常运行中停用;不再作为 startup 的运行期 truth 同步。
- **AC1**:startup 后 `llm_probe_catalog.json` 不被该链路写入。

**R4.3** 删除本地 community cache 后,"先 sync 后建 provider/route"场景靠**触发点**补回:
endpoint Test 成功后 best-effort 触发一次 `sync_verified_community_catalog`,把匹配新建/
验证 route 的远端 verified evidence merge 进 credentials——无缝替换旧的"Test 时 carry
cached community evidence"能力;显式 sync 入口保留。
- **AC1**:先跑 verified sync(此时无匹配 route,远端 evidence 被忽略)→ 再建 provider +
  跑 endpoint Test → Test 后该 route 的 `evidence` 含匹配的远端 verified evidence,投影
  `historical_ready`。
- **AC2**:该触发是 best-effort——sync 失败(网络/验签)不影响 endpoint Test 本身结果。

## 5. 上传:从 credentials 派生候选(P2, P4, P5)

**R5.1** 上传候选收集改为**从 credentials 派生**:遍历
`credentials.provider_routes[*].evidence`,筛 uploadable(probe + probe-verified)
**且 provenance 非 community**(只上传本地 Test/probe 产生的 evidence),用 route 所属
endpoint 做公网脱敏,产出上传批次。不再依赖 `load_evidence_library()` /
`llm_probe_catalog.json`,也不依赖 community cache 做 diff。
- **AC1**:给定一份含本地 probe-verified evidence 的 credentials(无 probe catalog 文件),
  上传候选收集返回对应 sanitized 批次。
- **AC2**:不可上传(非 probe-verified)evidence 被排除;**非公网 / 空 base_url** 的
  endpoint 经脱敏后无 `endpoint_fingerprint`(无法被 gate 匹配)而被丢弃,不上传(沿用
  现有 allowlist 脱敏,候选侧加 fingerprint 过滤)。
- **AC3**:**远端下载 merge 进来的 community evidence(`provenance="community"`)绝不被重新
  上传**——即便它也是 `probe`+`probe-verified`,杜绝远端→本地→远端的回环放大。

**R5.2** 上传幂等沿用 `batch_idempotency_key`(**整条 sanitized `EvidenceUpload` payload 的稳定 JSON
批次键**——每条 `model_dump(mode="json")` 排除时间戳 `observed_at`、`sort_keys`、batch 稳定排序;
**不是手写四元组**)+ gate 现有 record 级去重,**不改远端协议、不给 wire 加 content_hash**;
content_hash 在此只保证候选集稳定(同语义不重复派生)。上传失败时**不**把 pending queue 写进 credentials。
- **AC1**:上传失败后 credentials 不新增任何 pending/queue 字段;再次触发上传时,候选从
  credentials 重新派生且 `batch_idempotency_key` 稳定不变。
- **AC2**(drift 修复):同 endpoint+model+method 下,只要 `request_mapper_id` / `capability_family` /
  `model_type` / `input_modalities` / `output_modalities` / `probe_status` / `normalized_public_base_url`
  任一变化,`batch_idempotency_key` 必须变(远端不会误判幂等去重);batch 内 records 顺序不影响 key;
  `observed_at` 时间戳不进 key(同证据再观测仍幂等)。

## 6. 投影:蓝色只来自 credentials evidence(P1)

**R6.1** registry/UI 投影的 `historical_ready`(蓝)只能由 `route.evidence` 中
**`trust_state == "probe-verified"`** 的条目(经派生的 refs)驱动,且仍受
`credential_available` 约束(空配置优先 `missing_config`)。本地 probe-verified 与远端
community probe-verified 都是这个 trust_state,故都能投蓝;**`provider-list-observed` 等
非 probe-verified evidence 一律不投蓝**(严格沿用 community-probe-catalog-service-phase2a
`requirements.md:43`)。
- **AC1**:route 有 `probe-verified` evidence 且凭证可用、当前未 verified → 投影 `historical_ready`。
- **AC2**:route 只有 `provider-list-observed` / `probe-failed` evidence(无 probe-verified)→
  不得投影 `historical_ready`(回落 `untested`/对应态)。
- **AC3**:gateway `state_projection.project_route_state` 的既有契约(refs→蓝、无 refs→
  untested、missing_config 优先)保持不变;变化仅在"refs 从 route.evidence 的 probe-verified 派生"。

## 7. 空 Base URL 守卫(执行层不发网络)

**R7.1** credentials 允许存在空 Base URL 的 endpoint slot(用户已定:Add URL 空占位写
truth)。但 probe/执行层遇到空 base_url 必须直接返回 `missing_config`(error),
**不发任何 provider 网络请求**。
- **AC1**:对空 base_url endpoint 触发 endpoint probe / route probe,返回
  `status="error"` + `error_code="missing_config"`,无出站 HTTP。
- **AC2**:此守卫覆盖 gateway `provider_probe` 与 studio legacy adapter 两条路径
  (本 session 已实现,本 spec 补测试锁定契约)。

## 8. Legacy 迁移(一次性,P2)

**R8.1** 提供一次性 best-effort 迁移:把 `llm_probe_catalog.json` 与
`community_catalog_cache.json` 中的 evidence 导入 credentials 对应 route 的
`evidence`(按 R2.2 去重、按 route 匹配),迁移后这两个文件不再被读写,可删除。
- **AC1**:给定含 evidence 的两个 legacy 文件 + 匹配 route 的 v4/v5 credentials,
  运行迁移后 evidence 出现在 credentials,且重复运行迁移是幂等的(content_hash 去重)。
- **AC2**:迁移找不到匹配 route 的 evidence 被忽略,不创建游离条目。
- **AC3**:迁移失败不阻塞启动(best-effort,仅 log)。

## 9. 运行期读者全部从 credentials 派生(P7)

承接 research §4 读者表:除 §6 的投影(本就对齐)外,以下读者当前直接读
`llm_probe_catalog.json`,必须改为经 credentials evidence 访问层从 `route.evidence` /
`provider_routes` 派生(**接门**)或**溶解**,正常运行不再读 catalog 文件。

**R9.1(上传/分享候选)** `collect_uploadable_uploads`(`llm.py:192/663`)与
`/catalog/share`(`llm.py:602`)的可上传/可分享集从 credentials `route.evidence` 派生
(见 R5.1),不再 `load_evidence_library()`。

**R9.2(probe catalog summary = UI 契约)** registry 的 `probe_catalog` summary
(`_probe_catalog_summary`,`llm.py:2169` → `ProbeCatalogSummary` → 前端 Settings
`ApiKeysTab.tsx:69/198`)的 local evidence / verified / failed 计数从 credentials 各
route 的 `evidence` 汇总,不再数 probe catalog。API 字段形状可不变(不算前端改版),仅
来源换。
- **AC1**:无 `llm_probe_catalog.json` 时,registry `probe_catalog` 的计数等于 credentials
  内对应 trust_state 的 evidence 条数。
- **AC2(社区 summary 同源)**:同一 `ProbeCatalogSummary` 的 `community_catalog` 字段
  (`_community_catalog_summary`,`llm.py:2133/2141` 读社区 cache)也改从 credentials
  `last_remote_catalog_sync` marker + community-provenance `route.evidence` 派生;退役
  `community_catalog_cache.json` 后该 summary 仍正确(别只改 probe 半边)。

**R9.3(model 状态显示)** compact model info 的 `is_probe_verified`(`llm.py:4507`)从该
route 的 `route.evidence` 是否含 `probe-verified` 判定,不再扫 evidence library。

**R9.4(probe 候选与排序)** 第三方 probe 候选/排序(`llm.py:4833`,
`known_model_ids_for_endpoint` / `_endpoint_probe_order`)候选集从 credentials routes 取
(`endpoint_listed_model_ids`,R3.4 routes=model-list 真相)、排序从 `route.status` +
`route.evidence` 派生,不再读 catalog。
- **AC1(4 档,不跳过 verified)**:删空 probe catalog 后,probe 顺序仍是
  **当前 verified route → historical probe-verified → unknown → probe-failed 最后**
  (镜像 `_endpoint_probe_order`,以已知好模型最快确认 endpoint;**不得**像 gateway
  `probe_priority` 那样跳过 verified——那会破坏 Qiniu 修复逻辑)。

**R9.5(promotable 运行期链路整体退役,no backward compat)** `_apply_promotable_route_update`
连同 `_upsert_discovered_routes` 对它的调用**整体退役**:不再 `load_evidence_library()` 推
capabilities/profiles、不再写 `metadata["evidence_refs"]`。**最新决策:不向后兼容**——旧
`llm_probe_catalog.json` / `metadata` refs 数据可清空,**不做 catalog→route.evidence 的 legacy
bridge**(不把旧 draft 的 probe-verified bodies 桥回 credentials)。route 的 capabilities/profiles
只来自**本次 Test**(SSOT);蓝色只来自 `route.evidence` 的 probe-verified(§6/§4.3)。
- **AC1**:endpoint Test 后 route 不再新增 `metadata["evidence_refs"]`;正常运行期不为 promote
  读 `llm_probe_catalog.json`。
- **AC2**:预置 `route.evidence` 的 probe-verified,re-run 官方 endpoint Test **保留**该 evidence
  并投影 `historical_ready`,且 catalog 不读不写。

**R9.6(旧远端 probe catalog 同步入口退役)** 手动 API `/catalog/sync`(`llm.py:532` →
`sync_remote_probe_catalog_with_metadata` → 写 evidence library)在 P2 下不能继续作为正常
入口:**退役**(删除/停用),或改成 credentials merge 语义。R4.2 原只停了 startup 链路,本
条补齐手动 API。
- **AC1**:正常运行下没有任何入口把远端旧 probe catalog 写进 `llm_probe_catalog.json`。

## 10. 非目标(Out of Scope)

- 不改远端 community gate / GitHub catalog 的服务端协议与签名机制(因此上传/下载的 wire
  映射层 `EvidenceUpload` / `parse_catalog_evidence` **保留**,见 P3——本 spec 只统一"本地
  侧"的 evidence 模型,不动 wire 协议)。
- 不改 roles/bundles 解析、copilot 测试、role-test **作业编排**。**边界澄清**:共享的
  official profile probe evidence 写者(`_append_official_profile_probe_evidence`,被手动
  Test 与 role-test profile-ensure 共用)其**落点从 catalog 改到 credentials 属本 spec 范围**
  (是 evidence 写,不是编排);改的只是 sink,不动 role-test 何时跑/怎么编排。
- 不引入 DB/KMS/多用户认证(远期独立 spec)。
- 不做前端 UI **改版**(不动组件布局/交互;既有 `historical_ready`、`probe_catalog`
  渲染照旧消费)。**边界澄清**:R9.2 把 `probe_catalog` summary 的**数据来源**从 catalog
  换成 credentials(API 字段形状不变),属本 spec 范围——这是后端投影来源改动,不是 UI 改版。
- 不在本 spec 内"优化" Qiniu/notable-models 等既有 probe 行为(保留现状,勿误删)。
