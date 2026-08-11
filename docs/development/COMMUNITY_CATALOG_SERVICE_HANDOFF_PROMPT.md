# Handoff Prompt: Community Probe Knowledge Catalog Service Design

你接手的是第二阶段设计任务：为 Probe Knowledge Catalog 设计一个可承载大量用户贡献与同步的社区目录服务。不要实现代码，不要改当前 MVP1 本地目录行为；先产出设计文档和待确认问题。

## 背景

当前 MVP1 已把 `draft` 语义收敛掉：Import Draft（非可信候选配置 -> apply 到 active credentials）不是 MVP1 功能，不要恢复它。`draft` 只允许作为旧代码/旧文里的 legacy 词。

MVP1 的 Probe Knowledge Catalog 是 local-first：

- 本机 endpoint/model/capability 探测结果写入本地 append-only catalog。
- 远端 catalog 在 MVP1 只是 read-only suggestion source，用于清单兜底、能力回填、probe 优先级和 historical_ready 蓝态。
- `/api/llm/catalog/share` 只做 local_export_only 的本地脱敏导出/摘要，不自动上传社区证据。

第二阶段要设计的是新的 Community Catalog Service：负责多用户 evidence ingestion、脱敏校验、反滥用、聚合、索引、发布远端只读 artifact，让后来的用户可以共享“哪些 endpoint / protocol / model / capability 组合曾经连通过或失败过”的经验。

## 必读

按顺序读：

1. `/Users/sevenx/Documents/coding/agent-harness/AGENTS.md`
2. `/Users/sevenx/Documents/coding/agent-harness/docs/development/LLM_MODEL_CONFIGURATION_FLOW.md`
3. `/Users/sevenx/Documents/coding/agent-harness/docs/studio/mvp1/01_workflows/00_settings-ux-spec.md`，尤其 §4.1、§4.2、§7.2
4. `/Users/sevenx/Documents/coding/agent-harness/docs/studio/mvp1/04_platform/llm-copilot-http-api/mvp1-alignment.md`
5. `/Users/sevenx/Documents/coding/agent-harness/docs/graph-agent-gateway/mvp1/03-orch-credentials-endpoints/mvp1-alignment.md`
6. `/Users/sevenx/Documents/coding/agent-harness/docs/graph-agent-gateway/mvp1/04-orch-registry-schema/mvp1-alignment.md`
7. `/Users/sevenx/Documents/coding/agent-harness/docs/graph-agent-gateway/mvp1/05-orch-capabilities-and-models/mvp1-alignment.md`
8. `/Users/sevenx/Documents/coding/agent-harness/docs/graph-agent-gateway/mvp1/07-orch-fallback-circuit-probe/mvp1-alignment.md`
9. `/Users/sevenx/Documents/coding/agent-harness/docs/graph-agent-gateway/mvp1/08-orch-test-status-ssot/mvp1-alignment.md`
10. 当前实现参考：`/Users/sevenx/Documents/coding/agent-harness/apps/studio/backend/app/services/llm_probe_catalog.py`、`/Users/sevenx/Documents/coding/agent-harness/packages/graph-agent-gateway/src/graph_agent_gateway/registry/catalog.py`、`/Users/sevenx/Documents/coding/agent-harness/apps/studio/backend/app/routers/llm.py` 中 catalog sync/share 端点。

## 设计目标

回答一个问题：当有大量用户、provider、endpoint、model、capability evidence 时，如何保证新用户拿到的是“正确、可解释、可验证、不会污染本地 credentials”的候选信息？

设计至少覆盖：

- Community Catalog Service 的边界：desktop app、Studio backend、gateway SDK、托管服务、artifact CDN/GitHub mirror 各做什么。
- Evidence ingestion API：上传哪些字段、哪些字段禁止上传、是否需要登录/匿名 token、幂等 key、批量格式、失败重试。
- 隐私与脱敏：API key、credential_ref、私有 base_url、本地路径、prompt/input/output、账号/组织信息的硬红线；如何识别内网/private endpoint。
- Schema：provider、endpoint、route/model、capability、protocol、evidence、source、time window、trust score、deprecation、failure class、artifact metadata 怎么建模。
- 大体量索引：provider_id、endpoint_fingerprint、protocol、model_id/canonical_model_id、capability、region/source cohort 的索引策略；嵌套 JSON vs 扁平表/列存/搜索索引的取舍。
- 正确匹配：新用户的 provider/base_url/protocol/model 如何查到最相关 evidence；精确匹配、规范化、降级匹配、冲突处理和“不确定就不写绿”的规则。
- Aggregation：多条 evidence 如何变成候选 model list、capability hints、probe priority；成功/失败的时间衰减、provider 版本变化、模型下线、异常用户噪声如何处理。
- Trust model：probe-verified、probe-failed、provider-list-observed 的差异；什么能出蓝 historical_ready，什么只能灰；公共 catalog 永远不能直接把 active route 写成 ready。
- Client flow：本地探测成功/失败后如何排队、脱敏、预览、用户 opt-in 上传；上传成功后本地怎么记录 ack；离线/失败如何处理。
- Artifact publishing：服务如何生成远端 read-only catalog shards；客户端启动 sync 如何按 provider/etag/incremental 下载；如何避免每次全量拉取。
- Abuse / ops：限流、垃圾 evidence、恶意污染、签名、审计、撤回、版本迁移、监控和回滚。
- Migration：如何从 MVP1 local-only export 过渡到托管 ingestion；现有 `llm_probe_catalog.json` / legacy `ProviderImportDraft` 命名如何迁移而不破坏用户数据。
- Tests：服务端 schema/ingestion/aggregation 测试、客户端上传队列测试、脱敏红线测试、artifact 兼容测试。

## 明确不要做

- 不要把 Import Draft 作为功能重新设计回来。
- 不要设计“远端 evidence 自动 apply 到 credentials”的路径。
- 不要让桌面客户端持有能写公共 catalog 仓库的 maintainer token。
- 不要上传 API key、credential_ref、本地路径、raw prompt/input/output、用户账号/组织信息或可识别私有 endpoint 的原文。
- 不要把 `provider-list-observed` 当成连通证据；只有真实 probe 成功证据才可能参与 historical_ready。

## 产出

新增或更新一份设计文档，建议路径：

`/Users/sevenx/Documents/coding/agent-harness/docs/development/COMMUNITY_PROBE_CATALOG_SERVICE_DESIGN.md`

文档结构建议：

1. Problem Statement
2. Non-Goals
3. Current MVP1 Contract
4. Proposed Architecture
5. Data Model and Indexes
6. Ingestion API
7. Aggregation and Trust
8. Client Sync and Upload Flow
9. Privacy and Abuse Controls
10. Migration Plan
11. Test Plan
12. Open Questions

完成后只提交设计，不实现后端服务。
