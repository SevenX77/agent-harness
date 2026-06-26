---
module: 08-orch-test-status-ssot
doc: mvp1-alignment
status: drafted
binds_design: ./baseline.md
binds_code: packages/graph-agent-gateway/src/graph_agent_gateway/state_projection.py:ProviderModelStateProjection/project_route_state · packages/graph-agent-gateway/src/graph_agent_gateway/probe_catalog.py:ProbeCatalogStore/materialize_probe_catalog_candidates · apps/studio/backend/app/services/llm_probe_catalog.py:append_evidence_record/sync_remote_probe_catalog/DEFAULT_CATALOG_URL · packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:EvidenceRecord/ProviderImportDraft/ProbeResult
units: [test-status-ssot-evidence]
aligns_with: ../README.md · ../DESIGN_UNITS_INDEX.md · ../../../development/COMMUNITY_PROBE_CATALOG_SERVICE_DESIGN.md
---

# 08 — Test Status SSOT（测试状态唯一事实源:6 态投影 + Probe Knowledge Catalog）· MVP1 设计

> **组织方式**：**以每个功能为索引**（DESIGN-PROCESS §2.2 铁律）—— 每个功能(F1–F6)一段，把它的机制/数据流 · 决策+动机 · 原话 · 测试点 · status · 归属**全收在自己段里**；仅「定义」「接口契约」是模块级总览，证据附录(已实现/差异、决策原因、代码索引、覆盖率)留模块级末尾。现状基线见同目录 `baseline.md`。
> **Tier**：③b gateway 公共能力内核（6 态标准总结 `state_projection` + **Probe Knowledge Catalog / 探测知识库** 内核；UI 颜色渲染 / 远端源选择 / 存储介质 / 上传审批留 ③a）
> **Owns**：把"配置 + 健康 + 熔断 + 历史证据"总结成一套**标准 6 态**(`ready/historical_ready蓝/untested/failed带reason/cooling_down/off`)的投影内核 + 探测知识库内核（endpoint 形态、model list、route probe、capability evidence、probe priority、append-only evidence、远端共享）；**不渲染颜色、不自动上传、不绑定存储介质、不把远端 evidence 当 active verified**(归 ③a/active credentials 规则约束)
> **Status**：设计定稿（2026-06 重新定位：MVP1 不做 Import Draft 主线，`draft` 命名退役为 legacy；探测知识库改名为 Probe Knowledge Catalog）。代码已落地 canonical `graph_agent_gateway.probe_catalog` / `app.services.llm_probe_catalog` / `llm_probe_catalog.json`；底层仍保留 `llm_import_drafts.py` / `ProviderImportDraft` 作为历史存储兼容层；`snapshot_version` 填充仍由 loader/materializer/host 侧负责。
> **Related**：[[02-orch-role-resolution]]（materialize 消费 6 态投影排 fallback_chain，已取消 needs_setup）· [[05-orch-capabilities-and-models]]（`capability_state` 第二轴 + identity/notable/model_groups 同属探测知识库）· [[07-orch-fallback-circuit-probe]]（probe 产证据 + 熔断写 health store）· [[04-orch-registry-schema]]（`ProbeKnowledgeCatalog`/`EvidenceRecord`/`ProviderRoute` 字段权威源，现码仍有 legacy `ProviderImportDraft`）· [[03-orch-credentials-endpoints]]（endpoint test 回写 active credentials）· studio `llm-copilot-http-api`（HTTP 探测端点 = ③a 薄壳，`docs/studio/mvp1/04_platform/llm-copilot-http-api/`）· [Community Probe Knowledge Catalog Service Design](../../../development/COMMUNITY_PROBE_CATALOG_SERVICE_DESIGN.md)（阶段二托管 ingestion / 聚合 / artifact 发布设计；不改变 MVP1 local-first 合同）
> **决策日志**：`docs/studio/mvp1/01_workflows/00_settings-ux-spec.md` §4.1(Probe Knowledge Catalog)/§4.2(6 态体系)/§4.3(测试落点)/§6.0(判据)/§6.4(横切四层) + `docs/graph-agent-gateway/mvp1/module-disposition-revised.md`（08 行重新定位 + 下沉清单）+ gateway 包 `README.md` §3 D/B（6 态总结 + 探测知识库属公共）
> **现状**：见同目录 `baseline.md`

## 定义

MVP1 目标:测试状态以**active credentials / runtime health store 的后端 SSOT(单一事实源)**为准。Probe Knowledge Catalog 只提供候选、证据、能力回填、模型列表兜底和 probe 优先级,不能绕过 active credentials/status SSOT。

⚠️ **本模块重新定位最大**。旧文档把探测知识库混称为 `draft` / `import_drafts` / "导入草稿 + 证据库",导致"待导入草稿"与"可共享探测知识库"混在一起。MVP1 现在明确:

- **6 态标准总结** = **③b 公共内核**:把"配置 + 健康 + 熔断 + 历史证据"总结成一套标准状态集,是 gateway 从自身机制提炼的最佳状态方案,任何调模型 app 装上就能用;`module-disposition-revised.md:50` 08 行新判定 = "**③b 公共(标准总结),下沉 gateway;颜色渲染留前端**"。gateway 包 `README.md:74` D 节明确"标准状态总结(6 态)"属公共。
- **Probe Knowledge Catalog / 探测知识库内核** = **③b 公共内核**:记住"哪些 endpoint 形态连通过、哪些模型存在 / 可用 / 值得试、每条 route 历次探测证据、哪些 capability 来自 list/docs/probe、失败历史如何降权",并支持远端共享。这是 gateway 背后可沉淀、可共享的知识资产。
- **Import Draft 不属于 MVP1 主线**:MVP1 不做"待导入草稿 → apply 到 credentials"功能。旧 `ProviderImportDraft` / `create_draft` / `apply_draft` 只作为 legacy 代码名或后续功能候选,不得继续作为探测知识库的设计名。

**留在 ③a 的应用加工(四件事)**:① 状态颜色 / 文案渲染(展示)② 远端源选择/配置(当前有默认 GitHub URL,并支持 `url` 参数或 `STUDIO_CATALOG_URL` 覆盖；下沉后由应用注入)③ 存储介质(catalog / credentials / health store 存哪个文件 / SQLite 路径)④ evidence 分享/上传的用户审批与脱敏策略。Import/apply 工作流不是 MVP1 范围。

**阶段二托管社区目录设计入口**：MVP1 到此为止仍是 local-first：`/catalog/sync` 只拉取 read-only suggestion source，`/catalog/share` 只做 `local_export_only` 脱敏导出。大量用户贡献、托管 ingestion、反滥用、聚合索引、签名只读 artifact/CDN/GitHub mirror 的第二阶段设计登记在 [Community Probe Knowledge Catalog Service Design](../../../development/COMMUNITY_PROBE_CATALOG_SERVICE_DESIGN.md)。该设计是本模块 F3「Probe Knowledge Catalog」的后续扩展，不恢复 Import Draft，不允许远端 evidence 自动 apply 到 credentials，也不允许公共 catalog 直接写 `ready` 绿态。

> **阶段二 Phase 2a 收敛决策（post-MVP1，三方审核定稿 2026-06；非 MVP1 范围，登记于此供后续实施对齐）**
> 起步形态把托管服务塌缩到免费档，但守住所有 Non-Goal 与本模块合同。锁定决策（权威细节见上方设计文档「Phase 2a」两节）：
> 1. **唯一 ingestion 形态 = serverless 门卫**（如 Cloudflare Workers 免费档暴露 `POST /v1/evidence/batches`）。门卫只做鉴权/限流/服务端脱敏复校/入队，**不持有任何 catalog-repo 写 token**；写仓能力**只**存在于定时发布 GitHub Action（最小 `permissions: contents: write`），故门卫被打穿也写不了公共目录。客户端直接触发 Action（issue/`repository_dispatch`）的方案**已否决**（等价客户端持写入通道 + 破坏统一上传契约），仅可在真实 GitHub 身份的小范围可信 cohort 内作试验、绝不内嵌 trigger token。
> 2. **指纹隐私**：白名单知名公开服务商发 `normalized_public_base_url` 明文 + 指纹；非白名单/私有/未知 host **客户端上传前直接丢弃**，**永不发布原始不加盐 SHA-256**（可被字典枚举反推企业/个人/租户域名）；确需跨用户匹配非白名单公网站点时，唯一允许机制是**服务端加盐 HMAC**（pepper 门卫侧、可轮换、不公开原始哈希）+ 公网 host 审核，且为延后升级、不进 2a 基线。
> 3. **读取路径是迁移项，不是「不变」**：现状整包拉单文件 `llm_probe_catalog.json`；manifest + 分片 + ETag + 校验（fail-closed）+ 独立 disposable cache 是新客户端能力，按迁移设计。
> 4. **运维**：门卫不每请求直接 commit，写 KV/队列由 cron Action 批量提交（避免 git non-fast-forward 并发冲突）；分发走 GitHub **Pages（自带 CDN）**而非 raw（避免 429）。
> 5. **边界守恒**：`/catalog/share` 维持 `local_export_only` / `auto_upload_enabled=false`；自动上传是二期能力且必须**每次主动 opt-in**，不是全局开关翻 true。`/catalog/repository/ensure`（用用户自己 token 建仓）**不复用**作客户端→公共目录上传路径。
> 6. **schema 映射**：ingestion 的 `evidence_type:"probe_result"` 须映射到现有 `"probe"`（`registry/schema.py`；`/catalog/share` 按 `"probe"` 过滤）。
> 7. **进实现前补齐 gap**：匿名 token 生命周期/限流/吊销；撤回机制（上传返回一次性 `receipt_token`）；artifact `manifest.json` 协议主版本号（老客户端拒绝而非崩）；签名密钥保管/轮换/泄漏应急；GitHub 特有测试（Action 最小权限、签名 fail-closed、manifest 降级拒绝、限流响应、token 提取滥用模拟）。

不调真实模型;本模块定义"探测→持久化→投影→复用"的唯一写回路径与状态语义。本文只写文档目标,不改代码。

**判据(6 态投影 + 探测知识库归属，跨 F1/F2/F3 共用)**：

> **判据(6 态投影 + Probe Knowledge Catalog 归属)**："换个 app 还原样能用吗?能=③b,不能=③a。"(ux-spec §6.0 判据铁律) → 6 态标准总结 + 探测知识库是 gateway 机制衍生的最佳方案、任何调模型 app 可复用 → **③b 公共**;UI 颜色 / 远端源选择 / 存储介质 / 上传审批与脱敏 → **③a**。

## 接口契约

> 跨边界签名 / schema / 错误 / 归属。前端只投影、不持第二份真相(ux-spec §6.5 检查 2);③a↔③b 边界 = ③a 注存储介质 + 渲染颜色 + 配远端源 + 审批上传,③b 出标准 6 态 + Probe Knowledge Catalog 内核。

| 边界 | 契约 |
|---|---|
| **6 态投影输出（③b 内核 → ③a/前端）** | `project_route_state(endpoint, route, circuits, now, credential_evidence_refs) → ProviderModelStateProjection`{ `ui_state`: 6 态 Literal `ready/historical_ready/untested/failed/cooling_down/off`, `reason_code`(failed 时 `missing_config`/`endpoint_unreachable`/`model_failed`), `retry_at`(cooling_down 时), `ui_detail`, `evidence_refs` }。`credential_evidence_refs` 只来自 active credentials 的 `ProviderRoute.metadata.evidence_refs`;Probe Knowledge Catalog 中的孤立 evidence 不能被投影层直接读取。**前端只渲染 `ui_state`→颜色,不在组件态另存真值**(ux-spec §6.5 检查 2)。 |
| **`ProviderUiState` Literal（③b schema）** | 当前已是 6 态 `["ready","historical_ready","untested","failed","cooling_down","off"]`(`apps/studio/backend/app/services/llm_state_projection.py:15`)。旧 `needs_setup` 已被 `failed` + reason 取代;`_setup_reason` 当前返回 `missing_config`/`endpoint_unreachable`/`model_failed` 并由投影映射到 `failed`(`apps/studio/backend/app/services/llm_state_projection.py:37-39`,`:66-73`)。 |
| **Probe Knowledge Catalog（③b 内核 API）** | Canonical API: `ProbeCatalogStore` / `append_probe_evidence`(Studio facade 仍名 `append_evidence_record`) / `materialize_probe_catalog_candidates` / `known_model_ids_for_endpoint` / `known_verified_capabilities` / `probe_priority` / `sync_remote_probe_catalog`。目标核心对象: `ProbeKnowledgeCatalog`{ providers / endpoint_profiles / model_profiles / route_profiles / evidence_records / derived_indexes } + `EvidenceRecord`{ evidence_type / trust_state / provider_id / endpoint_fingerprint / route_key / provider_model_id / capability_profile / observed_at / share_policy }。当前实现已用 `llm_probe_catalog.json` 作为默认文件，底层 schema 暂由 legacy `ProviderImportDraft` 容器承载以兼容已有远端 catalog。 |
| **熔断持久化（③b 内核,与 07 同源）** | `SqliteLlmHealthStore.open_circuit(...)` / `get_active_circuits(route_id, endpoint_id, rate_limit_bucket) → RuntimeCircuit[]`(只返回 retry_at 未过);`RuntimeCircuit` 字段 `scope/scope_id/opened_at/retry_at/ttl_seconds/reason_code/failure_count/message`(`llm_health_store.py:14-101`)。SQLite 路径 ③a 注入。 |
| **SSOT 写回入口（③a 壳触发,③b 内核回写）** | endpoint test `test_endpoint` → 先写 `ProviderEndpoint.status`+last_test 和 credentials routes,再追加 `model_list_observation` evidence;endpoint model test / official profile probe → 先写 active route 状态、capabilities、verified_profiles、`metadata.evidence_refs`,再追加 `route_probe` / `capability_observation` evidence;route probe `_force_probe_route` → success 写 `route.status=verified`+clear circuit、temp-fail 开 circuit(不 failed)、hard-fail 写 `route.status=failed`+reason。Catalog evidence 可回填候选、能力、probe 优先级,但必须先晋升进 credentials 才能影响蓝态;它**不能直接把 active route 写绿**。 |
| **存储介质（③a 注入,不归 ③b）** | catalog / credentials / 健康库存哪个文件 / SQLite 路径 = ③a 提供(gateway 定 schema + 读写,studio 给位置)。MVP 小规模可用单文件 `llm_probe_catalog.json`;体量增大后切为 `index.json` + `providers/{provider_id}.json` + `evidence/{provider_id}/YYYY-MM.jsonl`。 |
| **错误** | catalog 缺失 → 空 catalog;provider 分片缺失 → 该 provider 仅无历史建议;投影对缺失输入有兜底(disabled→off 优先,无证据→untested 兜底)。 |
| **归属 / 稳定性** | `ProbeKnowledgeCatalog`/`EvidenceRecord`/`ProviderRoute`/`ProviderEndpoint` 字段权威源 = [[04-orch-registry-schema]];`RuntimeCircuit` 与 [[07-orch-fallback-circuit-probe]] 同源;`capability_state` 第二轴归 [[05-orch-capabilities-and-models]];本模块**只链接不复制**,防 drift。 |

---

## 功能逐项（每个功能为索引）

### F1 探测 → 持久化 → 投影 → 复用（唯一写回路径）

- **机制 / 数据流**：**上下游**:① 探测入口(endpoint test / route probe,③a HTTP 壳触发,内核 ③b)→ 写回 **active credentials(endpoint/route status/capabilities/verified_profiles/evidence_refs)+ health store(熔断 circuit)**,并把同一证据沉淀到 Probe Knowledge Catalog(probe 结果含失败)(③b 内核,③a 注存储介质)→ **6 态投影 `project_provider_model_state`(③b 内核)** 把 credentials status + key + circuit + credential evidence refs 合成 UI state → 两个消费方:前端 registry row(③a 渲染颜色)+ [[02-orch-role-resolution]] materialize(③b 编排,跳过 `failed/off`、`cooling_down` 写 warning、只把 fit route 进 fallback_chain)。逐步五段:

  1. 探测入口:Endpoint 探测由 `test_endpoint`(endpoint 探测 API,调 provider models-list 最小请求)发起,route 探测由 `probe_route` / `_force_probe_route`(route 探测 API + 真实探测 helper)发起,role/copilot 测试由各自 test job 对 route 批量 probe 发起;这些入口是真实测试状态的唯一写入点之一。MVP1 不再设计独立 `probe_import_draft` 主线。**判据:HTTP 端点 = ③a 薄壳;探测/拆分/匹配/记录 evidence 的内核 = ③b 公共。**

  2. 持久化 endpoint:Endpoint 成功/失败/空 key/并发变更结果写入 `ProviderEndpoint.status`、`last_test_at`、`last_test_message`,并通过 `save_credentials` 落盘;models-list 观察追加到 Probe Knowledge Catalog 的 `model_list_observation` evidence。**判据:status 字段 schema + 写回规则 = ③b;落盘到哪个文件(存储介质)= ③a 注入。**

  3. 持久化 route:Route 成功写 `status="verified"` 并写 capabilities/profile metadata;确定失败写 `status="failed"` 和 reason metadata;临时网络/限流/超时写 runtime circuit,不把 route 永久打 failed(`apps/studio/backend/app/routers/llm.py:843-846`,`:2017-2076`)。

  4. 持久化 circuit:`SqliteLlmHealthStore.open_circuit`(熔断持久化入口,upsert circuit 到 SQLite)把 cooling_down 事实写进 SQLite;`get_active_circuits` 只返回仍未到 retry_at 的 circuit(`apps/studio/backend/app/services/llm_health_store.py:34-62`,`:70-101`)。**判据:熔断持久化内核 = ③b(与 07 同一反转);SQLite 路径 = ③a 注入。**

  5. 投影:前端 registry row 和 role materializer 都调用 `project_provider_model_state`(6 态投影函数),由后端把 credentials status + key + circuit + route.metadata.evidence_refs 合成 UI state。**判据:6 态投影内核 = ③b;前端把 state 渲染成颜色 = ③a。**

  6. 复用:role 物化时跳过 `failed`(含原 needs_setup 配置缺口)/ `off`,对 `cooling_down` 写 warning,只把 fit 的 route 放进 fallback_chain;这使 UI test state 与实际编排共享同一判断(`apps/studio/backend/app/services/llm_role_materializer.py:48-90`)。**注**:此处旧文写"跳过 needs_setup",**6 态对齐后改为跳过 `failed`**(needs_setup 已并入 failed),与 [[02-orch-role-resolution]] §2 同步。

- **决策 + 动机**：**探测→持久化→投影→复用是唯一写回路径**——`test_endpoint` / `_force_probe_route` / role/copilot test job 是当前用户真实测试状态的写入入口,投影内核(③b)把 credentials 事实(endpoint status / route status / key / circuit / evidence_refs)合成 UI state,materialize 与 UI 共享同一投影口径,不各拼一份。**后端 SSOT 能避免前端易失态**:ready 不是单一字段,而是 endpoint status、route status、secret 存在性、runtime circuit(+ 已采纳历史证据引用)的组合;这些事实都在后端 credentials/health SSOT,前端只投影、不持第二份。**注**:SSOT 在"后端"是相对前端而言;后端里**投影内核**属 ③b(可下沉 gateway 包),与"前端不持第二份"不矛盾。

- **原话**：见 F2/F3 各功能原话(投影归属判据见模块级「定义」判据铁律)。

- **status**：`project_route_state`、Studio adapter、router/materializer 共享投影已落地；投影入参已从 `catalog_history` 收敛为 `credential_evidence_refs`,只读取 credentials route.metadata.evidence_refs。MVP1 剩余工程是把底层 legacy `ProviderImportDraft` 容器收敛为正式 `ProbeKnowledgeCatalog` schema，并继续清理旧模块名。

- **测试点**：
  - **前端不持第二份(ux-spec §6.5 检查 2)**:切 tab / 刷新后状态仍在(从后端投影读)= 对;丢 = 前端自持 = 错。
  - **credentials 喂投影**:`project_route_state` 入参含 `credential_evidence_refs`;回归点 = 必须读到 credentials route.metadata.evidence_refs 才出蓝,catalog-only 证据不能冒充蓝。

- **归属**：**③b** = 探测/拆分/匹配内核 + 6 态投影内核 + 熔断持久化内核(`services/llm_state_projection.py`、`services/llm_health_store.py`、`routers/llm.py` 探测段,待下沉 gateway);**③a** = HTTP `/api/llm/*` 探测端点薄壳(归 14)+ 存储介质(落盘到哪个文件 / SQLite 路径)+ 前端渲染颜色 + 批量探测进度 UI;**② Rust** = N/A(凭证/角色/证据/健康数据永不 Rust)。

### F2 6 态 UI state（取消 needs_setup + 蓝态 historical_ready）

> **本功能为 6 态对齐重写**。原文是旧 5 态(ready/untested/cooling_down/**needs_setup**/off),与文末 MVP1 回填段(蓝态 + 取消 needs_setup)自相矛盾。现按 ux-spec §4.2 canonical 6 态统一,**取消 `needs_setup`(并入 `failed` + reason)、新增 `historical_ready`(🔵 蓝=以前联通过)**。颜色心智(ux-spec §2.1 `00_settings-ux-spec.md:114`):**红=出错要你修;灰=非错误的不可用(untested 没测 / cooling 熔断中 / off 关了);绿=好;蓝=以前好。**

- **机制 / 数据流（UI state 的唯一语义,6 态）**：

  1. `ready`(🟢 绿):endpoint.status 和 route.status 都是 `verified`(真 probe 过);这是唯一绿色可用状态(`apps/studio/backend/app/services/llm_state_projection.py:48-49`)。

  2. `historical_ready`(🔵 蓝=以前联通过):endpoint verified + Probe Knowledge Catalog 显示该 route **历史连通过**,但当前无 live `route.status=verified`;介于 untested 与 ready 之间的历史态。**蓝判据**:只 `route_probe/probe_verified` 历史(真连通过)算蓝,贴合"以前联通过";`provider-list-observed` / `doc-discovered` / 没连过的不算。**蓝不替代 ready**:当前用户当前 key 真 route-probe 通 → 升 🟢;model/role/copilot probe 会写历史连通证据供蓝态消费。投影插点 = `ready` 检查之后、`untested` 兜底之前。

  3. `untested`(⚪ 灰):没有 disabled、没有配置缺口、没有 active circuit、也没有历史连通证据、但也不是双 verified;通常对应 `unverified_manual` 或待验证 route(`apps/studio/backend/app/services/llm_state_projection.py:52`)。

  4. `failed`(🔴 红,带 reason,**取代旧 `needs_setup`**):出错了要你修,两类经 `reason` 区分——① **配置缺口**(缺 key / base_url / protocol / model id,旧 `needs_setup` 已并入此类)reason=`missing_config`;② **测试失败**(route 真探挂)reason=`endpoint_unreachable` / `model_failed`。**红、不挡进可用**(failed route 仍列出、仍可拖,换 role 配置 / 重试可能就好,真正永久不可用在运行期 admission 拦)。当前 `_setup_reason` 已返回 reason code,投影统一产 `failed` + reason(`apps/studio/backend/app/services/llm_state_projection.py:37-39`,`:66-73`)。

  5. `cooling_down`(⚪ 灰+倒计时):存在匹配 route/endpoint/rate_limit_bucket 且 retry_at 未过的 circuit(临时网络/限流/超时);UI 展示 retry_at 和 message,不当永久失败(`apps/studio/backend/app/services/llm_state_projection.py:40-47`,`:76-95`)。

  6. `off`(⚪ 灰+不可选):endpoint 或 route disabled(用户/配置主动关闭),优先级最高(`apps/studio/backend/app/services/llm_state_projection.py:35-36`)。**注**(ux-spec §4.2 单模型 probe 失败两类 `00_settings-ux-spec.md:273`):模型已弃用 / 不再提供(provider 明确返回"无此模型")归 `off`(灰、不可选),**不是** `failed`(不是"连不上",是"没这模型了");弃用可逆——点击仍可复制名 + 单独 re-probe,再次连通 → 从弃用区捞回。

  **6 态投影优先级（route 级,目标语义,ux-spec §4.2 状态分层）**:`off > failed🔴 > cooling_down > ready🟢 > historical_ready蓝🔵 > untested⚪`。其中 `ready / 蓝 / untested` 同属"证据 tier",按证据新鲜度排:刚测通(ready) > 历史通(蓝,来自 Probe Knowledge Catalog) > 无证据(untested)。蓝插在 ready 检查之后、untested 兜底之前。

- **决策 + 动机**：
  - **6 态标准总结 `state_projection` = ③b 公共内核(本轮反转)**:把"配置 + 健康 + 熔断 + 历史证据"总结成标准状态集,是 gateway 从自身机制提炼的最佳方案、任何 app 可复用;**判据**:"换个 app 还原样能用吗?能=③b"。**被反转**:原 baseline `Baseline/Alignment 差异` 与 `决策原因` 隐含"UI state 必须**后端**投影"——把它当 studio 后端职责(隐性 ③a);现按判据,投影**内核** = ③b 公共,**只有把 state 渲染成颜色 = ③a**(`module-disposition-revised.md:50`、ux-spec §6.4 横切表 `00_settings-ux-spec.md:468`)。
  - **取消 `needs_setup`,统一 `failed`(红)+ reason(6 态对齐)**:消除文档自相矛盾(原正文旧 5 态 vs 文末回填段 6 态)+ 对齐 PM 裁定。心智:红=出错要你修、灰=非错误的不可用、绿=好、蓝=以前好;`needs_setup`(配置缺口)本质是 failure → 并入 `failed` + reason=`missing_config`,真测试失败 = reason=`endpoint_unreachable`/`model_failed`;权威 ux-spec §2.1 + §4.2 + 状态分层实现 gap(`00_settings-ux-spec.md:285`)。
  - **新增 `historical_ready`(🔵 蓝=以前联通过)第 6 态**:蓝态归 `Capability` 域的 catalog/probe-history 子源(历史连通),是 `ui_state` 投影层的第 6 态、**不是新源域**;蓝判据从窄(只 route probe verified 历史算蓝)。

- **原话**：
  > **PM #A 6 态体系**(ux-spec §4.2 `00_settings-ux-spec.md:262`)：标签颜色 = 该 **route** 的状态,**三页一致**;canonical 6 态 = `ready` / `historical_ready`(🔵 蓝) / `untested` / `failed`(带 reason) / `cooling_down` / `off`。

  > **PM 取消 needs_setup**(ux-spec §2.1 #10 PM 裁定 `00_settings-ux-spec.md:114`)：原话 PM 问"现在有一个状态叫做needs_setup, 这是一个什么状态? 要setup什么呢??";裁定"取消原 `needs_setup` 灰态——它本质是 `failed` 的一个 reason(配置缺口),并入 failed 显红"——理由:①「配置缺口」本质是 failure、和 failed 同族;②灰色会和 untested(没测、中性)混淆、弱化"这是致命错误";③现码 `_setup_reason` 把真测试失败也揉进 needs_setup 显灰、双重混淆。

  > **PM 蓝↔绿 = endpoint 验证 vs model 保证**(ux-spec §4.3 + §4.2 状态分层)：API key 页验 endpoint + catalog 历史回填 → 模型显 🔵 蓝;role 页对模型真 probe → 升 🟢 绿。即"endpoint 验证(蓝)→ model 保证(绿)"。

- **status**：已落地:后端 `ProviderUiState` Literal 是六态,旧 `needs_setup` 已取消并由 `failed` + reason 替代,`historical_ready` 由 credentials route.metadata.evidence_refs 驱动；前端类型、Available Models provider tag、ProviderStateBadge、ProviderCard route tag 已同步六态。

- **测试点**：
  - **6 态投影**:① 双 verified → `ready🟢`;② endpoint verified + credentials route.metadata.evidence_refs 有历史连通证据引用 + 无 live verified → `historical_ready🔵`;③ 无任何证据 → `untested⚪`;④ 缺 key/base_url/protocol/model id → `failed🔴` reason=`missing_config`;⑤ route 真探挂 → `failed🔴` reason=`endpoint_unreachable`/`model_failed`;⑥ active circuit 未过期 → `cooling_down`(带 retry_at);⑦ disabled / 模型弃用 → `off`。
  - **取消 needs_setup(回归)**:任何旧产 `needs_setup` 的输入(配置缺口)现产 `failed` + reason;`ProviderUiState` Literal 不再含 `needs_setup`。
  - **蓝↔绿升级**:`historical_ready🔵` 的 route 真 route-probe 通 → 升 `ready🟢`(蓝是历史态,不替代 ready)。
  - **蓝判据从窄**:只 credentials route.metadata.evidence_refs 引用的 `route_probe/probe_verified` 历史(真连通过)算蓝;provider-list-observed / doc-discovered / catalog-only 未晋升证据 / 没连过的 → 仍 `untested`(不冒充蓝)。
  - **投影优先级**:同时满足多态时按 `off > failed > cooling_down > ready > 蓝 > untested` 取最高优先。

- **归属**：**③b** = 6 态投影内核(`services/llm_state_projection.py`,待下沉);**③a** = 前端把 state 渲染成颜色/文案。

### F3 Probe Knowledge Catalog（探测知识库）

- **机制 / 数据流（目标边界）**：

  1. **证据输入**:endpoint test、model list、route probe、role/copilot test、provider docs ingestion 都写入 `EvidenceRecord`。证据必须 append-only,包含 `evidence_type`、`trust_state`、`provider_id`、`endpoint_fingerprint`、`provider_model_id`、`route_key`、`capability_profile`、`observed_at`、`share_policy`。成功和失败都写入;失败是 probe priority 的降权输入,不是垃圾数据。

  2. **Provider 分区**:catalog 逻辑上按 `provider_id` 分区。每个 provider 下维护 `endpoints`、`models`、`routes` 三类画像: endpoint 画像表示 base_url/protocol/request mapper/auth 形态; model 画像表示 provider-scoped model id 和 capability 事实; route 画像表示 endpoint + model + method/profile 的连通关系。

  3. **匹配键**:endpoint 级事实用 `endpoint_fingerprint = hash(provider_id | normalized_base_url | protocol | request_mapper_id | auth_scheme | optional region/vendor hints)` 匹配;route 级事实用 `route_key = endpoint_fingerprint + provider_model_id + method_id/request_mapper_id` 匹配。只匹配 model id 不足以证明 route 连通过。

  4. **模型列表兜底**:`GET /models` 失败或返回空时,从 catalog 以 `provider_id + endpoint_fingerprint` 精确查候选;没有精确命中时降级到 `provider_id + protocol`。兜底生成的 route 只能是 `unverified_manual / untested`,不能直接 verified。

  5. **能力回填**:当前 probe/list-models 拿不到 capability 时,可从 catalog 回填 `capabilities`。每个 capability value 必须带 provenance(`catalog_probe_verified` / `api_list` / `provider_doc` / `community_reported`)和 `evidence_ref`;它能辅助 role fit / UI 展示 / probe 参数选择,但不能单独把 route 变绿。

  6. **Probe 优先级**:当 endpoint 可连但不知道测哪个 model 时,按 catalog 的历史连通数据排序:最近成功、成功次数多、capability 匹配当前用途、没有 deprecated/off 证据、失败率低的模型优先;历史失败或弃用模型降权。目标是少盲测,不是跳过本地验证。

  7. **蓝/绿红线**:catalog 中 `route_probe/probe_verified` 必须先晋升为 credentials route.metadata.evidence_refs;当前 endpoint verified + 当前 route 未 live verified + credentials 有 evidence_refs → `historical_ready` 蓝;当前用户当前 key 真 route probe 成功 → `ready` 绿。远端/公共 catalog evidence 永远不能直接写 active `route.status="verified"`，也不能绕过 credentials 直接点蓝。

  8. **上传/共享**:本地 probe 成功先写 local catalog evidence 并让 credentials 引用 local evidence;分享时生成 sanitized evidence bundle,用户显式确认后上传远端 catalog。上传前必须删除 API key、credential_ref、本地路径、私有 base_url(除非用户明确标记 public/shareable)、原始请求/响应中的账号信息、prompt/input/output。可上传 public normalized base_url 或 base_url fingerprint、protocol、request_mapper_id、provider_model_id、capability summary、success/failure category、latency bucket、observed_at、client/library version、evidence hash/signature。

  9. **存储规模**:MVP 小规模可用单文件 `llm_probe_catalog.json`;中规模改为 `index.json` + `providers/{provider_id}.json`;大规模使用 provider summary + append-only JSONL evidence log: `evidence/{provider_id}/YYYY-MM.jsonl`。summary/index 可重建,append-only evidence 是真源。

- **目标 schema（逻辑形态）**：

  ```json
  {
    "schema_version": 1,
    "kind": "llm_probe_knowledge_catalog",
    "providers": {
      "openai": {
        "provider_id": "openai",
        "endpoints": {
          "fp_...": {
            "endpoint_fingerprint": "fp_...",
            "normalized_base_url": "https://api.openai.com/v1",
            "protocol": "openai_compatible",
            "request_mapper_id": "openai_chat_completions",
            "connectivity_summary": {}
          }
        },
        "models": {
          "gpt-4.1": {
            "provider_model_id": "gpt-4.1",
            "canonical_model_id": "openai:gpt-4.1",
            "capability_summary": {}
          }
        },
        "routes": {
          "fp_...:gpt-4.1:chat_minimal": {
            "route_key": "fp_...:gpt-4.1:chat_minimal",
            "endpoint_fingerprint": "fp_...",
            "provider_model_id": "gpt-4.1",
            "connectivity_summary": {},
            "capability_summary": {},
            "evidence_refs": []
          }
        }
      }
    },
    "evidence_records": {},
    "indexes": {
      "by_endpoint_fingerprint": {},
      "by_provider_model": {},
      "by_capability": {},
      "probe_priority": {}
    }
  }
  ```

- **credentials 写入规则**：

  1. `llm_credentials.json` 是当前用户配置和当前验证状态,不是公共 catalog。它保存 `provider_endpoints`、`provider_routes`、roles/profiles 引用等 active runtime 真相。
  2. endpoint 建议补强字段:`provider_id`、`endpoint_fingerprint`、`normalized_base_url`、`protocol`、`request_mapper_id`。
  3. route 建议补强字段:`provider_model_id`、`canonical_id`、`capabilities`(带 provenance)、`verified_profiles`、`evidence_refs`。
  4. catalog seeded 的 route 可写入 credentials 作为候选:`status="unverified_manual"`、`ui_state="untested"`、`metadata.catalog_seeded=true`、`metadata.catalog_evidence_refs=[...]`。
  5. catalog capability 可写入 route capabilities,但 source 必须标成 catalog/provenance;它不改变 `route.status`。
  6. 只有当前用户当前 key 真 probe 成功,才能把 route 写成 `status="verified"` 并挂本地 `route_probe/probe_verified` evidence ref。

- **决策 + 动机**：
  - **Probe Knowledge Catalog 替代 draft 命名**:功能目标是"收集终端探测到的 endpoint/model/route/capability evidence,全网共享,后来者少盲测",不是"待导入草稿"。`draft` 在 MVP1 中只保留为 legacy 命名,不再是设计概念。
  - **provider 分区 + 扁平 evidence**:provider 是天然分片键,endpoint/model/route 是 provider-scoped 画像;append-only evidence 不深嵌,避免重复、冲突和大文件局部更新困难。summary 可重建,evidence log 是真源。
  - **catalog advisory, credentials authoritative**:catalog 可以推荐、补列表、补 capability、让 route 蓝;不能绕过当前 credentials 的本地 probe,不能直接让 route 绿。

- **原话**：
  > **PM 探测知识库目标(2026-06-23 本轮收敛)**:把终端探测到的模型数据收集到一起、全网同步,让后来者共享这些数据。数据包括 endpoint 的连通数据(provider 的 base_url + protocol/request mapper),route 的连通数据(endpoint + model + capability)。新用户 get models 没有模型列表时从知识库获得;probe models 没有 capability 时从知识库获得;测试 endpoint 不知道哪个 model 更可能连通时,从历史连通过的模型中挑选,不用盲测。

- **status**：设计目标已收敛；canonical 代码入口已是 `graph_agent_gateway.probe_catalog` / `app.services.llm_probe_catalog` / `llm_probe_catalog.json`。底层 schema 仍以 legacy `ProviderImportDraft` 容器承载部分 evidence library 能力，后续需要迁移为正式 `ProbeKnowledgeCatalog` schema。

- **测试点**：
  - **列表兜底**:`GET /models` 空/失败 + catalog 有 provider/endpoint 候选 → credentials 生成 untested 候选,不 verified。
  - **能力回填**:probe/list 未给 capability + catalog 有 evidence → route capabilities 带 catalog provenance/evidence_ref,`route.status` 不变。
  - **probe priority**:候选模型排序优先历史成功、能力匹配、近期成功;历史失败/弃用降权。
  - **蓝态**:只有已写入 credentials route.metadata.evidence_refs 的 `route_probe/probe_verified` 历史出 `historical_ready`;`model_list_observation/provider-list-observed` 和 catalog-only 证据不出蓝。
  - **上传脱敏**:share/export bundle 不含 secret/private local data;上传需要用户显式确认。

- **归属**：**③b** = Probe Knowledge Catalog schema、evidence merge/dedupe、provider 分区、endpoint/route/capability 匹配、probe priority、credentials evidence_refs 投影内核;**③a** = 远端源配置、存储介质路径、上传审批和脱敏 UI、HTTP/job 包装;**active credentials** = 当前用户 verified 真相。

### F4 后端 SSOT 回写规则（四类结果）

- **机制 / 数据流**：**SSOT 写回路径(四类结果,当前语义)**:① endpoint models-list 成功 → 写 `endpoint.status` + last_test 字段,并追加模型列表观察 evidence;② model/profile/role/copilot probe 成功 → 写 active route/profile(适用时) + **写成功 probe evidence**;③ 临时失败(网络/限流/超时/配额)→ 写 health store circuit(`cooling_down`),**不**把 route 永久 failed,并写失败 evidence;④ 确定失败 → 写 `route.status=failed` 或 probe result error/reason,并写失败 evidence(适用路径)。投影再把 ④ 变成 `failed🔴`(带 reason,旧 `needs_setup` 已被替代)。逐条回写规则:

  1. 成功的 endpoint models-list 测试回写 endpoint.status 与 last_test 字段;若发现官方 endpoint 的模型列表,可 upsert route,但 route 仍需按 probe 语义决定 verified;同时追加模型列表观察 evidence(`apps/studio/backend/app/routers/llm.py:561-600`,`:2748-2765`)。

  2. 成功的 model/profile probe 回写 route.status、capabilities、verified_profiles 和 probe metadata,并写成功 probe evidence;`_force_probe_route` 的 success path 会写 route verified + clear circuit(`apps/studio/backend/app/routers/llm.py:669-708`,`:748-807`,`:2017-2056`,`:2605-2745`)。

  3. 临时失败回写 health store,不写 route failed;当前 `_force_probe_route` / role test 等路径对 timeout/rate_limited/quota/network_error 打开 circuit,这是 cooling_down SSOT。

  4. 确定失败回写 route.status failed 和 metadata reason,或写入 probe evidence reason;projection 再把它变成 `failed🔴`(带 reason),旧 `needs_setup` 已被替代。

- **决策 + 动机**：**cooling_down 不应写成 failed**:临时网络/限流问题会过期,health store 的 retry_at 能表达"暂时不要用",而 route.status failed 会表达"配置或模型不可用"(`apps/studio/backend/app/routers/llm.py:960-965`,`:2057-2063`;`apps/studio/backend/app/services/llm_health_store.py:70-101`)。**probe evidence 成功+失败都要保留**(PM #2.4):成功证据喂蓝态历史 + 下次免重探,失败证据让下次批量探测可跳过历史失败。evidence 何时能晋升/覆盖 active credentials 仍需规则化。

- **原话**：见 F3 PM #2.4 原话(失败也写证据)+ F2 PM 取消 needs_setup 原话(④ 确定失败投影成 `failed` 而非 `needs_setup`)。

- **status**：endpoint test、endpoint model test、role/copilot test、route force probe 已分别具备 active status / evidence / circuit 的写回基础;`failed` 六态投影已落地。剩余是把 Probe Knowledge Catalog 到 active credentials 的候选/能力/蓝态/绿态晋升规则按 F3 落到实现。

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

- **机制 / 数据流**：版本-stale(见 [[04-orch-registry-schema]] 回填)的"曾 verified"route 在 resolver 侧**不再算 live ready**:registry resolver 会把版本不一致的 `verified_profiles/capabilities` 从 live evidence 中剥离,并把当前 `snapshot.snapshot_version` 传给 `ResolvedRoute`。投影层可以把 Probe Knowledge Catalog 的历史证据合成为 `historical_ready🔵`;版本-stale 若要稳定进入蓝态,需要 loader/materializer/host 填充 `snapshot_version` 并把旧 verified 事实保留/转写为可消费的 catalog evidence。

- **决策 + 动机**：版本-stale 与 catalog 历史是两条独立来源(D1 版本失效 / catalog probe history),但 UI 语义都指向"以前 verified、现未重验"。resolver 先保证旧 live evidence 不误当 ready;投影层用 `historical_ready` 表达历史建议态,真重验通才升绿(与 F2 蓝判据一致)。

- **原话**：（两轴合成为投影层内部一致性收敛,无独立 PM 原话;依据 ux-spec §4.2 状态分层 + [[04-orch-registry-schema]] 版本-stale 回填。）

- **status**：registry schema/resolver 的版本-stale 降级已落地;`project_provider_model_state` 的历史证据蓝态已落地。仍需明确的是 `snapshot_version` 由 loader/materializer/host 填充,以及版本-stale 的旧 verified 事实如何进入 Probe Knowledge Catalog。

- **测试点**：registry resolver:当前 snapshot 有版本而 route evidence 版本不同 → 旧 ready verified profile 不再被选成 live ready(`packages/graph-agent-gateway/tests/test_registry_resolver.py:119-184`)。UI projection:有历史证据且当前无 live verified 的 route → `historical_ready🔵`;真重验通 → 升 `ready🟢`(复用 F2 蓝↔绿升级测试点)。

- **归属**：**③b**(两轴合成投影内核,与 6 态投影同处);版本-stale 字段权威源归 [[04-orch-registry-schema]],catalog 历史归 F3 Probe Knowledge Catalog;本模块只链接不复制。

---

## gaps / 待设计

- ⚠️ **Finding C + C-2（2026-06-04 实查代码，状态真实性，强化本模块"后端 SSOT / 前端不持第二份真相"论点）**：
  - **C（probe ≠ runtime）**：Studio endpoint test 走 raw HTTP（探测段经 `_join_base_url_and_endpoint` 会 dedup `/v1`），但 SDK runtime 不 dedup → 同一 base_url，probe 通过、runtime 404（实证见 [[03-orch-credentials-endpoints]] F3 + [chatx-provider-patterns.md](../references/chatx-provider-patterns.md)）。**后果：route 可能 probe 显 verified/绿、runtime 实际挂 = false-positive verified。**
  - **C-2（API Keys 页 Connected 仍需独立收口）**：实查——third-party/custom 的 `Connected` 文案仍由 API Keys 前端 `testStatus` 自算（`ProviderCard.tsx:783-813`，取持久化 `available_models`/`last_test_status`），不等同于 LLM Roles/provider model 的六态投影。Get Models 失败路径目前 catch 只 toast、不会改写持久化状态(`apps/studio/frontend/src/components/studio/settings/SettingsPage.tsx:698-700`);`upsertProviderModelsListResponse` 仍会保留旧 ok/provider models(`apps/studio/frontend/src/components/studio/settings/SettingsPage.tsx:247-275`)。
  - **设计结论（要求）**：① 可用性状态（含 API Keys 页 Connected）由**后端 6 态投影**驱动，前端只读、不自持第二份；② **探测 / Get Models 失败必须回写状态**（降级，而非保留旧 ok）；③ probe 尽量贴 runtime 路径，或显式区分 `HTTP-reachable` / `SDK-runtime-verified` 两态。
- **代码下沉/改名**:6 态投影内核与 Probe Knowledge Catalog canonical API 已进入 gateway 包；颜色渲染 / 存储介质 / 远端源配置 / 上传审批留 ③a。剩余兼容债是把底层 `llm_import_drafts.py` / `ProviderImportDraft` 容器迁移为正式 `ProbeKnowledgeCatalog` schema。
- **待办(catalog → credentials 晋升规则)**:按 F3 固定:catalog 可 seed route / 回填 capability / 排 probe priority / 出蓝;仅当前用户当前 key 本地 probe 成功可写 active `route.status="verified"`。远端 evidence 只能作为建议。
- **待办(snapshot_version 填充边界)**:`ProviderRoute`/`RegistrySnapshot`/`ResolvedRoute` schema 与 resolver 降级已支持 `snapshot_version`,但 Studio `RolesData.to_registry_snapshot` 当前不填该字段;填充仍由 loader/materializer/host 侧负责(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:207-221`,`:404-442`;`apps/studio/backend/app/models/llm_config.py:279-296`)。
- **待办(远端源配置边界)**:`sync_remote_probe_catalog` 当前有默认 GitHub URL,并支持 `url` 参数或 `STUDIO_CATALOG_URL` 覆盖;下沉 ③b 时远端源选择仍应由 ③a 注入,不要把默认源固化成公共内核事实。
- **疑点(circuit 排序)**:`_select_active_circuit`(active circuit 选择 helper)当前用 `-retry_at.timestamp()` 排序、倾向选更晚 retry_at 的 circuit;如果 UI 想展示"最具体 scope 优先"或"最快可重试",需要调整排序规则(`apps/studio/backend/app/services/llm_state_projection.py:76-95`)。

## 交叉引用（双向，回写）

- [[02-orch-role-resolution]]:materialize 消费 6 态投影排 fallback_chain（已取消 needs_setup,跳过 `failed`/`off`）
- [[05-orch-capabilities-and-models]]:`capability_state` 第二轴 + identity/notable/model_groups 同属 Probe Knowledge Catalog 下沉知识库
- [[07-orch-fallback-circuit-probe]]:probe 产证据 + 熔断写 health store（`SqliteLlmHealthStore` 同源反转 ③b）
- [[04-orch-registry-schema]]:`ProbeKnowledgeCatalog`/`EvidenceRecord`/`ProviderRoute`/`ProviderEndpoint` 字段权威源（现码仍有 legacy `ProviderImportDraft`,本模块只链接）
- [[03-orch-credentials-endpoints]]:endpoint test 回写 active credentials + base_url 归一化
- studio `llm-copilot-http-api`（`docs/studio/mvp1/04_platform/llm-copilot-http-api/`）:HTTP `/api/llm/*` 探测端点 = ③a 薄壳
- [Community Probe Knowledge Catalog Service Design](../../../development/COMMUNITY_PROBE_CATALOG_SERVICE_DESIGN.md):阶段二托管社区目录服务设计，覆盖 ingestion、脱敏校验、反滥用、聚合索引和只读 artifact 发布；作为 MVP1 local-first Probe Knowledge Catalog 的后续扩展，不改变本模块的 advisory-only / 不写绿约束。
- ux-spec §4.1(Probe Knowledge Catalog)/§4.2(6 态体系)/§4.3(测试落点)/§6.0(判据)/§6.4(横切四层) · 归属表 `module-disposition-revised.md`（08 行重新定位 + 远端源可配置）· gateway 包 `README.md` §3 B/D

---

## 附录 A — 涉及 region / platform（模块级 ③a/③b/② 总表）

> 各功能段已带各自 归属;此处保留跨功能完整 ③a/③b/② 清单作模块级总览。

- **③b** `packages/graph-agent-gateway`:6 态投影内核(`state_projection.py`)、Probe Knowledge Catalog canonical API(`probe_catalog.py`)、熔断持久化内核(现 `services/llm_health_store.py`,与 07 同,待下沉)、`ProbeKnowledgeCatalog`/`EvidenceRecord`/`ProbeResult` 数据结构(目标归 04,现码仍有 legacy `ProviderImportDraft` 容器)、list-models 解析 + 批量探测编排内核(现 `routers/llm.py` 探测段)。
- **③a** `apps/studio/backend` + 前端:状态颜色/文案渲染、远端源选择/配置(当前默认 GitHub URL 可被 `url` 参数 / `STUDIO_CATALOG_URL` 覆盖)、上传审批/脱敏、存储介质(catalog/credentials/健康库存哪个文件 / SQLite 路径)、HTTP `/api/llm/*` 探测端点薄壳(归 14)、批量探测进度 UI。Import/apply 工作流不是 MVP1 功能。
- **② Rust**:N/A(凭证/角色/证据/健康数据永不 Rust)。

## 附录 B — 已实现 / 与 baseline 差异

1. 已实现:后端已有 `project_provider_model_state`,并且 router 与 materializer 都在调用它,说明 UI 与编排已经共享同一投影口径(`apps/studio/backend/app/services/llm_state_projection.py:26-52`;`apps/studio/backend/app/routers/llm.py:1862-1907`;`apps/studio/backend/app/services/llm_role_materializer.py:142-170`)。**归属:投影内核 = ③b(待下沉)。**
2. 已实现:route force probe 对 success、temporary failure、hard failure 三类结果有不同持久化路径,这是 SSOT 回写的基础(`apps/studio/backend/app/routers/llm.py:2017-2076`)。
3. 已实现:runtime circuit 是 SQLite 持久化,不是前端内存态(`apps/studio/backend/app/services/llm_health_store.py:26-101`)。**归属:熔断持久化内核 = ③b(待下沉,与 07 同);SQLite 路径 = ③a 注入。**
4. 已实现:旧 `needs_setup` 已取消并由 `failed` + reason 取代,`ProviderUiState` 当前为六态,`historical_ready🔵` 已由 credentials route.metadata.evidence_refs 驱动(`packages/graph-agent-gateway/src/graph_agent_gateway/state_projection.py`)。
5. 已实现:compact model status 旧事实已被替代,当前 DTO status 是六态加 `testing`,并通过 `_provider_model_projection(...).ui_state` 复用同一投影(`apps/studio/backend/app/routers/llm.py:196-209`,`:4353-4401`)。
6. 现码事实:legacy `probe_import_draft` worker / 公开 Import Draft HTTP 主线已移除；可复用逻辑已收敛进 Probe Knowledge Catalog/route probe 写证据链路。
7. 已实现:前端 `ProviderUiState` / `ModelGroupStatusSummary` / ProviderCard route tag / LLM Roles provider badge 已同步六态(`apps/studio/frontend/src/api/llm.ts:12-13`,`:109-116`;`apps/studio/frontend/src/components/studio/api-keys/ProviderCard.tsx:348-378`;`apps/studio/frontend/src/components/studio/settings/llm-roles/provider-state-badge.tsx:15-59`)。
8. 差异(**判据反转 + 重新定位**):baseline 的实现仍散在 Studio 后端且命名为 draft;MVP1 归属要求投影内核 + Probe Knowledge Catalog 内核 = ③b 公共(待下沉),仅 UI 颜色 / 远端源 / 存储介质 / 上传审批留 ③a。
9. 差异:baseline `apply_draft` 属 Import Draft 工作流;MVP1 不做该功能。若后续恢复 Import Draft,也必须保持保守默认:`apply` 后 route 只能是 `unverified_manual`,不能直接 verified。
10. 差异:`snapshot_version` schema/resolver 已支持,但填充仍属于 loader/materializer/host 侧责任,不是 08 投影内核自动生成(`packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:207-221`,`:404-442`;`apps/studio/backend/app/models/llm_config.py:279-296`)。

## 附录 C — 决策原因（保留 baseline 原文,补反转 + 6 态对齐）

1. UI state 投影内核必须存在,原因是 ready/failed/cooling_down 需要同时看 endpoint、route、secret、runtime circuit(+ 历史证据);这些数据前端不应自己拼(`apps/studio/backend/app/services/llm_state_projection.py:26-73`)。**反转补:此"投影"的内核 = ③b 公共(可下沉 gateway),原 baseline 隐含的"必须 studio 后端"只是相对前端的 SSOT 表述,不与下沉冲突;前端只渲染颜色。**
2. runtime circuit 单独持久化,原因是限流/网络冷却不等于 route 永久 failed;`_force_probe_route` 对 timeout/rate_limited/network_error 打开 circuit,但返回原 route,就是这个语义(`apps/studio/backend/app/routers/llm.py:2057-2063`)。**反转补:熔断持久化内核 = ③b(与 07 同),SQLite 路径 ③a 注入。**
3. Import Draft 不进入 MVP1,原因是当前产品目标不是"非可信候选导入再 apply",而是"探测知识沉淀与共享"。旧 `apply_draft` 可作为后续功能参考,但不能继续污染探测知识库命名。
4. Probe Knowledge Catalog 适合作为建议材料,原因是它是 append-only 并可远端同步,但不应替代 active credentials 的可执行状态。**反转补:append-only 知识库内核 + 远端合并去重 = ③b 公共;远端源选择/配置 + 上传审批/脱敏 = ③a。当前代码有默认 GitHub URL,也支持 `url` 参数 / `STUDIO_CATALOG_URL` 覆盖。**

**判据反转 + 6 态对齐 + 重新命名(2026-06 第四轮后追加收敛)**:6 态标准总结 `state_projection` + Probe Knowledge Catalog 从"隐性 ③a 后端 SSOT/投影 + draft 命名"收敛为"③b 公共能力内核(待下沉)";`needs_setup` 取消并入 `failed`+reason、新增蓝态 `historical_ready`,正文从旧 5 态对齐到 canonical 6 态;`draft` 命名退役为 legacy,不再代表 MVP1 功能。

## 附录 D — 代码索引 clues

- `apps/studio/backend/app/services/llm_state_projection.py:15`:`ProviderUiState` Literal 已是六态;旧 `needs_setup` 已被 `failed`+reason 替代。
- `packages/graph-agent-gateway/src/graph_agent_gateway/state_projection.py`:6 态投影流程——**= ③b 公共内核**;canonical 入参为 `credential_evidence_refs`，不再提供 catalog evidence 直读投影入口。
- `apps/studio/backend/app/services/llm_state_projection.py:55-73`:`has_historical_probe_verified` / `_setup_reason`。
- `apps/studio/backend/app/services/llm_state_projection.py:76-116`:circuit 匹配/scope priority。
- `apps/studio/backend/app/routers/llm.py:488-600`:endpoint test 回写 active credentials 并追加模型列表观察 evidence(③a 壳 + ③b 写回内核)。
- `apps/studio/backend/app/routers/llm.py:609-807`:endpoint model test 写 route/profile probe evidence。
- `apps/studio/backend/app/routers/llm.py:810-846`:route probe 回写 verified/capabilities。
- `apps/studio/backend/app/routers/llm.py`:公开 Import Draft HTTP 家族已移除；route/endpoint/role probe 写 evidence 的可复用逻辑归 Probe Knowledge Catalog 链路。
- `apps/studio/backend/app/routers/llm.py:2017-2095`:force route probe 回写 missing_key/success/circuit/failed。
- `apps/studio/backend/app/routers/llm.py:196-209`,`:4353-4401`:compact model status 六态(+`testing`)收口。
- `apps/studio/backend/app/services/llm_health_store.py:34-101`:runtime circuit 写入和读取——**熔断持久化内核 = ③b(待下沉);SQLite 路径 ③a 注入**。
- `apps/studio/backend/app/services/llm_role_materializer.py:48-90`:projection 影响 fallback_chain 物化(跳过 `failed`/`off`、`cooling_down` warning)——旧 `needs_setup` 已并入 `failed`。
- `packages/graph-agent-gateway/src/graph_agent_gateway/probe_catalog.py`:Probe Knowledge Catalog canonical API；当前复用 legacy store 类型以兼容历史 catalog。
- `apps/studio/backend/app/services/llm_probe_catalog.py`:Studio canonical service facade；`llm_import_drafts.py` 仅是历史存储实现。
- `apps/studio/backend/app/services/llm_import_drafts.py`:legacy draft/evidence store + remote merge 实现；Import Draft 非 MVP1，apply 路径不作为公开产品功能。
- `apps/studio/frontend/src/api/llm.ts:12-13`,`:109-116`:前端 ProviderUiState / status summary 六态。
- `apps/studio/frontend/src/components/studio/api-keys/ProviderCard.tsx:348-378`:ProviderCard 以 `historical_ready` 状态渲染蓝色 Tag variant,不输出旧状态值。
- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:150-183`,`:258-264`:snapshot_version 透传与 stale live evidence 降级。

## 附录 E — 覆盖率

本 alignment 覆盖 08 brief 的全部要求:`state_projection.py:project_route_state`(6 态投影)+ `probe_catalog.py` / `llm_probe_catalog.py`(Probe Knowledge Catalog canonical 入口)两个核心对象已落到真实代码,并完成设计重新定位:6 态投影内核 = ③b、Probe Knowledge Catalog 内核 = ③b、Import Draft 非 MVP1 主线、`draft` 命名退役为 legacy。为说明"探测→持久化→投影→复用",额外引用 router、health store、role materializer 作为证据线索,均标注 ③a/③b 归属。
