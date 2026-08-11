---
module: graph-agent-gateway-mvp1
doc: audit-report
status: drafted
workflow_axis: N/A（gateway MVP1 是库/公共能力模块,无独立用户旅程 workflow 文档）
binds_design: ./README.md · ./DESIGN_UNITS_INDEX.md
binds_code: packages/graph-agent-gateway/src/graph_agent_gateway · apps/studio/backend/app/services
units: []
aligns_with: ../../development/design-doc-standards/02-audit-standard.md · ./README.md · ./DESIGN_UNITS_INDEX.md
---

# Graph Agent Gateway MVP1 审计报告

> 日期:2026-06-06。范围:`docs/graph-agent-gateway/mvp1`。本报告记录本轮深审与修复后的状态;它不是 FROZEN 盖章。

## 结论

当前文档已完成本轮 drafted 深审与修复:README scope/non-goals、Workflow=N/A 说明、新建 MVP1 `DESIGN_UNITS_INDEX.md`、frontmatter 追踪字段、R6 临时引用、Markdown/wiki 链接、`binds_code` 符号、带完整路径的行号引用、INDEX 单元登记和当前代码 baseline 口径均已复核通过。

仍不得标 `FROZEN`:gateway 专属锁入口已经建立,但所有设计单元仍是 `owned-lock=drafted`、`integration-lock=unverified`,hash 表仍为空,且尚未由 owner 盖章。10/11 是目标新增模块,`RouteChatModelFactory` / `ProviderProfile` 等目标符号还没有生产实现,文档已按 target 标注。

## 审计原则

1. baseline 只按当前代码写,不得拿旧 spec、mvp0 或目标设计冒充现状。
2. alignment 只写 MVP1 目标与最新决策,目标未实现必须显式标 target / 待办。
3. gateway MVP1 是库/公共能力模块,workflow 轴为 N/A;审计覆盖靠 README 决策主落点、`DESIGN_UNITS_INDEX.md`、`module-disposition-revised.md` 和各模块就近 PM 原话,不伪造用户旅程。
4. 只做文档审计和文档修复;发现代码债写回 baseline/alignment 的差异或风险,不在审计中顺手改生产代码。

## 动作流水

| 编号 | 动作 | 文件 / 证据 | 结果 |
|---|---|---|---|
| A01 | 读取 `design-doc-standards` 三份规范,确认三轴、R0-R8、Q1-Q5、M1-M8 审计方法。 | `docs/development/design-doc-standards/00-three-axes.md`; `01-writing-standard.md`; `02-audit-standard.md` | 明确 gateway 本轮按轴②模块 + 轴③ INDEX 审,workflow 轴写 N/A。 |
| A02 | 回扫 MVP1 目录结构和已有模块,确认 01/02/03/04/05/06/07/08/09/10/11/13/predict 是本轮主体。 | `docs/graph-agent-gateway/mvp1` | 原 12 copilot SDK 调用和 14 HTTP 壳按归属判据移交 Studio,不再作为 gateway owner 模块。 |
| A03 | 补 README scope / non-goals / 归属判据。 | `README.md` | 明确 gateway 做公共能力内核;不做 UI、产品策略、copilot SDK 调用、HTTP job/DTO 壳、engine predict 业务逻辑。 |
| A04 | 补 README Workflow=N/A 说明。 | `README.md` | 不伪造轴① workflow;覆盖依据改为 README 决策主落点 + INDEX + disposition + 各 alignment PM 原话。 |
| A05 | 新建 MVP1 设计单元 INDEX,不用 mvp0 INDEX。 | `DESIGN_UNITS_INDEX.md` | 登记 14 个设计单元,包含 owner/spans/binds_code/owned-lock/external-binding/integration-lock。 |
| A06 | 审锁机制和脚本冲突风险。 | `DESIGN_UNITS_INDEX.md`; `AUDIT_REPORT.md` | 结论:不能复用 Studio 或 graph-agent 锁;gateway 需要独立锁测试、快照和 exemption。 |
| A07 | 一波修复 frontmatter。 | 30 个 `.md` 文件 | 补 `status`、`binds_design`、`binds_code`、`units`、`aligns_with`;所有文档仍为 `drafted`,不冒用 `FROZEN`。 |
| A08 | 清理 R6 临时引用和旧参考路径。 | 各模块 alignment / baseline | 临时 spike / 工作日志类证据不再作为正式 SSOT;可复用模式归档到 `references/chatx-provider-patterns.md`。 |
| A09 | 建立 ChatX/provider 参考归档。 | `references/chatx-provider-patterns.md` | 将外部范本结论固定为参考,供 10/11/09/03 消费,不当作当前代码事实。 |
| A10 | 回扫 mvp0 泄漏。 | `README.md`; 01/05 等模块 | 旧版材料不再作为证据来源;剩余 mvp0 字样只保留“仅迁移背景 / 不作 SSOT / 不复用 INDEX”的边界声明。 |
| A11 | 逐模块核 01 handoff。 | `01-handoff-interface/*`; `registry/schema.py`; `protocol.py`; `copilot.py` | 修正为当前 `ResolvedRoute/ResolvedRole.routes` 契约;删除旧 `call_chain/ResolvedProvider` 证据;Copilot WS 契约归 Studio,本模块只链接。 |
| A12 | 逐模块核 02 role resolution。 | `02-orch-role-resolution/*`; `registry/resolver.py`; `resolver.py`; `llm_role_materializer.py` | 标清当前 `resolve_role` 行为、`ModelResolver.resolve` 返回 `BaseChatModel`、materialize 当前仍散 Studio;skip diagnostics 后续已落地并回写。 |
| A13 | 逐模块核 03 credentials/endpoints。 | `03-orch-credentials-endpoints/*`; `llm_credentials.py`; `registry/credentials.py`; `registry/storage.py` | 修正 base_url 当前只是 strip/rstrip,没有统一 protocol canonicalize;`_stable_endpoint_id` 是 v3→v4 migration helper,不是当前统一 canonical id 生成器。 |
| A14 | 逐模块核 04 registry schema。 | `04-orch-registry-schema/*`; `registry/schema.py`; `registry/canonical.py`; `llm_config.py` | 补 schema / canonical / Studio DTO 衔接 binds;字段事实按当前 schema。 |
| A15 | 逐模块核 05 capabilities/models。 | `05-orch-capabilities-and-models/*`; `capabilities.py`; `lint.py`; `profile_selector.py`; Studio model services | 修正 capability/lint/profile 边界:只 warn/block/fail-fast,不做动态替代 route 搜索;model knowledge 现仍散 Studio,目标下沉 gateway。 |
| A16 | 逐模块核 06 error classification。 | `06-orch-error-classification/*`; `registry/error_classification.py`; `call/clients.py` | 修正当前函数签名、字段、fallback/fail-fast 映射;401/402/403/404 与 capability 类错误按当前语义记录。 |
| A17 | 逐模块核 07 fallback/circuit/probe。 | `07-orch-fallback-circuit-probe/*`; `call/chat_model.py`; `call/clients.py`; `llm_health_store.py`; `copilot_test.py` | 拆清 `_generate` 编排段、probe、down-cache、usage/event;保留 ChatX 瞬时 retry 是目标,当前 OpenAI/Anthropic client 仍 `max_retries=0`。 |
| A18 | 逐模块核 08 test status SSOT。 | `08-orch-test-status-ssot/*`; `llm_state_projection.py`; `llm_import_drafts.py` | 修正当前 projection 是 5 态且有 `needs_setup`;MVP1 目标才是取消 `needs_setup` 后 6 态;remote evidence catalog 当前有默认 URL,也支持参数/env 配置。 |
| A19 | 逐模块核 09 invocation runtime。 | `09-inv-invocation-runtime/*`; `call/chat_model.py`; `call/clients.py`; `models.py` | 标清当前自研 `_call_*`/dict response/`_coerce_text` 仍存在;目标是原生 ChatX invoke、保留 content blocks、usage/metadata bridge。 |
| A20 | 逐模块核 10 route chat model factory。 | `10-inv-route-chat-model-factory/*`; `models.py`; `resolver.py`; `call/clients.py` | 修正当前没有 `RouteChatModelFactory` 源码;职责暂由 resolver + client_manager 承担;Ark 当前仍走官方 SDK,目标才是 OpenAI-compatible ChatX。 |
| A21 | 逐模块核 11 provider profiles。 | `11-inv-provider-profiles/*`; `profile_selector.py`; `VerifiedProfile`; `call/clients.py` | 修正当前没有 `ProviderProfile` 调用层注册表;当前存在的是 `VerifiedProfile` / `select_verified_profile` 和 scattered provider kwargs;`ProviderProfile` 是 MVP1 target。 |
| A22 | 逐模块核 13 tracing/events/exceptions。 | `13-x-tracing-events-exceptions/*`; `events.py`; `exceptions.py`; `tracing.py`; `call/chat_model.py` | 标清当前 fallback event / exception / tracing helper 字段和触发点;事件 code 当前仍复用 all-providers-failed 系列,target 才拆专用语义。 |
| A23 | 核 predict migration 单独文档。 | `predict-migration-to-engine.md`; `call/predict.py`; `protocol.py`; `resolver.py`; `predictor.py` | 修正当前 gateway 仍有 `PredictGatewayChatModel`、`PredictContext`、resolver predict 特判;目标才是 mock/path diff 业务移交 engine。 |
| A24 | 修正 module disposition 绑定。 | `module-disposition-revised.md` | 补 frontmatter 和 scope links;保持 12/14 移交 Studio、health/status/model knowledge 等待下沉的归属判据。 |
| A25 | 对全部文档做 frontmatter / 符号 / 链接 / 行号 / INDEX 单元机械复核。 | 见“复核命令” | 机械可判项全部 0 issues。 |
| A26 | 对 gateway package 跑测试。 | `uv run pytest packages/graph-agent-gateway/tests -q` | `97 passed, 1 xfailed`。 |
| A27 | 回写审计报告。 | `AUDIT_REPORT.md` | 本报告从摘要扩展为动作流水、模块台账、命令台账和残余风险。 |
| A28 | 拆 INDEX 非原子 spans。 | `DESIGN_UNITS_INDEX.md` | 将多模块 span 和 facet 内部箭头拆成机器可解析的 `facet→module(role)` 原子项。 |
| A29 | 按 TDD 写 gateway 锁测试 RED。 | `packages/graph-agent-gateway/tests/test_gateway_doc_locks.py` | 首次运行 `2 failed, 3 passed`,失败点正是缺 `_audited-ready-hashes.json` 和 `_design-unit-lock-snapshot.json`。 |
| A30 | 补 gateway 专属锁表、快照和 exemption 空表。 | `_audited-ready-hashes.json`; `_design-unit-lock-snapshot.json`; `gateway-doc-exemptions.json` | 重新运行锁测试 `5 passed`;锁入口独立于 Studio / graph-agent。 |
| A31 | 锁入口落地后跑 gateway 全量测试。 | `uv run pytest packages/graph-agent-gateway/tests -q` | `102 passed, 1 xfailed`。 |

## 模块修复台账

| 模块 | baseline 当前代码口径 | alignment 目标口径 | 本轮关键修正 |
|---|---|---|---|
| 01 handoff | 当前是 `ResolvedRoute/ResolvedRole.routes`;public resolver 仍 model-first。 | 新增 route 级 handoff API,route 是编排/调用唯一交接物。 | 去掉 mvp0 证据;Copilot WS owner 改为 Studio;runtime metadata 证据改挂当前 `GatewayChatModel`。 |
| 02 role resolution | `resolve_role` 展开 role→routes;普通坏 route 会进入 skipped diagnostics 并继续,override 坏 route fail-fast。 | skip 普通坏 route + skipped diagnostics;override 坏 route fail-fast。 | 现状已回写为 skipped diagnostics 落地,不再保留旧口径。 |
| 03 credentials/endpoints | base_url 当前未统一 canonicalize;凭证按 `credential_ref` 取明文,key 不落 route。 | 保存时 protocol canonicalize + 调用时 no-op 双保险。 | `_stable_endpoint_id` 改成 migration helper 事实,不是统一 canonical id。 |
| 04 registry schema | schema 当前权威在 `registry/schema.py` 和 Studio DTO bridge。 | route/schema 字段继续作为 handoff/编排/调用共同契约。 | 补 binds 和 unit 登记,按当前字段写 baseline。 |
| 05 capabilities/models | capability/lint/profile selector 只做能力归一、warn/block/fail-fast。 | model knowledge 下沉 gateway,但不驱动动态替代 route 搜索。 | 删除把旧材料当权威的说法;补 Studio services 现状归属。 |
| 06 error classification | 当前 `classify_exception` 输出 legacy decision + v1.1 action/scope。 | 语义基本不变,供 ChatX/probe/fallback 继续消费。 | 修正签名、字段名和 401/402/403/404 fallback 语义。 |
| 07 fallback/circuit/probe | `GatewayChatModel._generate` 承担 fallback/probe/mark_down/event/usage。 | 保留编排外壳,只替换 route 调用步骤;ChatX retry 不禁用。 | 将 `_generate` 符号写法和编排/调用边界修正;health_store 标待下沉。 |
| 08 test status SSOT | 当前 `project_provider_model_state` 仍有 `needs_setup`;draft/evidence 在 Studio service。 | 后端 SSOT 回写,取消 `needs_setup`,形成 6 态。 | 修正 remote catalog 当前可配置事实;修正 README 行号和 UX/spec 链接。 |
| 09 invocation runtime | 当前自研消息 dict、`_call_*`、dict response、`_coerce_text` 仍存在。 | 原生 ChatX invoke,保留 content blocks,从 `usage_metadata` 取 usage。 | WaveSpeed 当前 `_call_wavespeed_any_llm` 与目标 ChatX 边界拆开。 |
| 10 route factory | 当前无 `RouteChatModelFactory` 源文件;client_manager/ resolver 暂代管。 | 新建 route→ChatX 工厂和 generic adapter。 | Ark 当前仍官方 SDK;目标才改 ChatOpenAI-compatible。 |
| 11 provider profiles | 当前无 `ProviderProfile`;只有 `VerifiedProfile`/profile selector/provider branches。 | 新建 provider/model init-kwargs profile registry。 | 不再把 `ProviderProfile` 写成当前实现;与 `VerifiedProfile` 明确分层。 |
| 13 tracing/events/exceptions | 当前 event/exception/tracing helper 已存在,触发在 `_generate`。 | 保留结构化事件/异常,目标拆更准确事件 code。 | 补触发点和 current code 字段;当前 code 复用事实写清。 |
| predict migration | 当前 gateway 仍有 predict interception 和 resolver 特判。 | predict mock/path diff 业务移交 engine,gateway 只留 role→route。 | 不把目标迁移写成已完成;补当前 `PredictGatewayChatModel` 事实。 |

## R0-R8

| 规则 | 结果 | 证据 / 说明 |
|---|---|---|
| R0 scope | PASS | `README.md` 已补 scope / non-goals;明确 gateway 做公共能力内核,不做 UI、产品策略、copilot SDK 调用、HTTP 壳、engine predict 业务逻辑。 |
| R1 当前 SSOT | PASS | 旧版材料不得作为 MVP1 SSOT;剩余 mvp0 字样只保留在 README/INDEX/AUDIT 的“不得复用 / 仅迁移背景”边界说明中。MVP1 当前权威落在 README、DESIGN_UNITS_INDEX、各 alignment 与源码。 |
| R2 baseline↔代码 | PASS | 30 个文档 frontmatter 合规,367 个 `binds_code` 符号均能在当前代码中解析;高风险 current-code 口径已按源码修正,包括 Ark 现状、remote catalog 配置、5 态/6 态差异、predict 当前仍在 gateway、`RouteChatModelFactory`/`ProviderProfile` 仍是 target。 |
| R3 alignment 最新决策 | PASS | D1/D2/D3/F1/F2/M5/M4 主落点已在 README 和各 alignment 就近登记;workflow 轴为 N/A,不伪造 atom action。 |
| R4 覆盖 | PASS | 12 个模块 baseline/alignment + predict + boundary 单元均登记;12/14 原模块中 12 copilot 与 14 HTTP 壳已移交 studio。 |
| R5 引用拓扑 | PASS | 所有 baseline/alignment 已补 `binds_design`、`binds_code`、`units`、`aligns_with`;Markdown 本地链接和 wiki 解析为 0 缺失。 |
| R6 引用纪律 | PASS | 正式文档不再引用临时目录路径;外部范本和 spike 结论已归档到 `references/chatx-provider-patterns.md`。 |
| R7 锁状态 | PASS(drafted) | 30 个文档状态均符合四态;未冒用文件级 `FROZEN`;INDEX 14 行均为 drafted / unverified。 |
| R8 INDEX | PASS | `DESIGN_UNITS_INDEX.md` 新建 MVP1 设计单元索引,14 个横切单元登记 owner/spans/binds_code/三态锁;不复用 mvp0 INDEX。 |

## 复核命令

| 命令 / 检查 | 结果 | 说明 |
|---|---|---|
| frontmatter/status 检查 | `frontmatter_files=30`, `issues=0` | 所有文件有 frontmatter,status 符合四态;baseline/alignment 具备绑定字段。 |
| `binds_code` 符号检查 | `checked_symbols=367`, `issues=0` | 绑定的当前代码符号均可解析;目录级 binds 只用于 README/INDEX/AUDIT 这类聚合文档。 |
| Markdown/wiki 链接检查 | `markdown_links=72`, `wiki_links=337`, `issues=0` | 本地 Markdown 链接和模块 wiki 链接均能解析。 |
| 完整路径行号引用检查 | `checked_qualified_line_refs=888`, `issues=0` | 只校验带 `packages/`、`apps/`、`docs/` 前缀的完整路径行号;裸短路径行号作为 clue,不当可解析绝对证据。 |
| INDEX 单元登记检查 | `registered_units=14`, `used_units=13`, `issues=0` | `units:` 使用项都已登记;`studio-boundary-copilot-http` 是边界单元,在 README/INDEX 承载。 |
| gateway doc lock RED | `2 failed, 3 passed` | 失败原因是缺 gateway 专属 hash lock 和 design-unit snapshot,符合 TDD 预期。 |
| gateway doc lock GREEN | `5 passed` | 补最小锁表 / 快照 / exemption 后通过。 |
| `git diff --check -- docs/graph-agent-gateway/mvp1` | clean | 文档 diff 无 whitespace/error marker 问题。 |
| R6 / 旧版泄漏 grep | 仅 README 历史边界说明命中 | mvp0 不作 SSOT;无 `provider-runtime-settings-matrix` / `mvp0-alignment` 证据引用残留。 |
| `uv run pytest packages/graph-agent-gateway/tests -q` | `102 passed, 1 xfailed` | package 现有测试通过;新增 gateway doc lock 测试已纳入。 |

## 残余风险

1. `RouteChatModelFactory`、`GenericRouteChatModel`、`ProviderProfile` 是 MVP1 target,不是当前实现。文档已标 target,实现前不能把 10/11 当已完成能力。
2. `snapshot_version` / snapshot provenance 的写入责任仍未明确;`ResolvedRoute.snapshot_version` 当前未由 resolver 填入。
3. `max_retries=0` 当前仍在 OpenAI/Anthropic client 工厂里;文档已标目标为保留 ChatX 有界瞬时重试,代码未实现。
4. `state_projection`、`import_drafts`、`health_store`、model knowledge 内核仍散在 Studio,文档已标待下沉 gateway。
5. gateway 专属锁入口已创建,但当前 hash 表为空、所有单元仍 drafted;后续 FROZEN/locked 需要 owner approval 后更新 `_audited-ready-hashes.json` / `_design-unit-lock-snapshot.json`。

## 下一步建议

1. 若目标是冻结这些 drafted 文档,下一步应由 owner 逐文件/逐单元盖章,再把对应文件 SHA-256 写入 `_audited-ready-hashes.json`,把对应单元从 `drafted` 升为 `locked` 并更新 `_design-unit-lock-snapshot.json`。
2. 没有 owner approval 前,不要把任何文件或单元标 `FROZEN` / `locked`。
3. 代码实现层面的下一步仍是 MVP1 target 落地,优先级建议从 `resolve_routes` handoff API 和 10/11 ChatX 工厂/profile 开始;这些属于生产代码变更,要另走 TDD。
