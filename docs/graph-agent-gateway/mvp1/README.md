---
milestone: MVP1
decision_record: 已分散留底进各模块文档(每模块 §4 用户原话 / §5 决策+动机);client 层 A' 重设计决策不再单独引用外部文件
coverage: 后端文件映射(Explore 清点);12 个 gateway ③b 模块 baseline/mvp1-alignment 已起草(原 copilot、HTTP 适配壳 2 模块 2026-06-03 判 ③a，移交 studio)
status: implemented（Gateway MVP1 优化已落地;剩余跨应用下沉项按 deferred 另行排期）
design_units_index: ./DESIGN_UNITS_INDEX.md
workflow_axis: N/A（gateway MVP1 是库/公共能力模块,无独立用户旅程 workflow 文档;覆盖以决策来源清单 + DESIGN_UNITS_INDEX + 各 alignment PM 原话核验）
module: graph-agent-gateway-mvp1
doc: manifest
binds_design: ./DESIGN_UNITS_INDEX.md
binds_code: packages/graph-agent-gateway/README.md
units: []
aligns_with: ../../development/design-doc-standards/00-three-axes.md · ../../development/design-doc-standards/01-writing-standard.md · ../../development/design-doc-standards/02-audit-standard.md
---

# MVP1 — 模块 manifest + 写作 brief

> 每个模块一个子文件夹,内含 `baseline.md`(现状)+ `mvp1-alignment.md`(目标)。
> 设计单元索引(轴③ · R8 枢纽)= [`DESIGN_UNITS_INDEX.md`](./DESIGN_UNITS_INDEX.md)。本索引为 MVP1 新建,不复用 mvp0 `INDEX.md`。
> 全部必须满足底部**写作 bar**——核心:**把每个类/函数解释清楚,不靠名字猜**。

## Scope / Non-goals（审计边界）

**MVP1 做什么**：把 `graph-agent-gateway` 定义成领域无关、可复用的大模型网关公共能力内核(③b)。本轮文档覆盖:role→route 编排与 route 交接契约、凭证/端点 schema 与 base_url 归一化、registry schema、capability/profile/model 知识、错误分类、fallback/circuit/probe、测试状态 SSOT 与证据库、原生 ChatX 调用运行时、route→ChatX 工厂、provider profile、fallback tracing/events/exceptions,以及 predict mock 移交 engine 后 gateway 只留 role→route 的边界。

**MVP1 不做什么**：不定义前端 UI / 颜色 / 拖拽 / 卡片录入;不定义产品策略(默认推荐、动态浮出、弃用区、family 折叠展示);不承载 copilot 的实际 SDK 调用、session、WS 事件翻译或 SDK 测试;不承载 HTTP job/progress/DTO 包装;不绑定凭证、证据库、health store 存储介质;不承载 engine 的 predict mock / path diff 业务逻辑;不在本轮文档审计里顺手改代码。

**归属判据**：凡是对模型数据/机制的标准化、组织、编排、状态总结、知识沉淀,且不依赖 UI 交互 / 产品策略 / 实际调用方式 / 存储介质,归 gateway ③b 公共能力;绑死四件应用加工之一的内容归 ③a Studio 或其它调用方。现代码中散在 `apps/studio/backend` 但按判据属 ③b 的能力,本轮文档写成"待下沉 gateway";代码迁移另立工程任务。

**权威来源**：归属判据以 `packages/graph-agent-gateway/README.md` §2、`docs/studio/mvp1/01_workflows/00_settings-ux-spec.md` §6.0、[`module-disposition-revised.md`](./module-disposition-revised.md) 为准;横切单元 / owner / lock 以 [`DESIGN_UNITS_INDEX.md`](./DESIGN_UNITS_INDEX.md) 为准。

**Workflow 轴说明**：gateway MVP1 是库/公共能力模块,不是用户旅程型产品模块,本目录没有独立轴① workflow 文档。审计覆盖不伪造 atom action,改按本 README 的决策主落点、[`module-disposition-revised.md`](./module-disposition-revised.md) 的归属反转、[`DESIGN_UNITS_INDEX.md`](./DESIGN_UNITS_INDEX.md) 的设计单元映射,以及各 `mvp1-alignment.md` 就近 PM 原话逐项核验。

## 架构:编排 → [route] → 调用

- **编排(准备期)**:role → 解析出该用哪条 `route`(含 fallback 顺序、熔断/probe 决策),**不调模型**。
- **交接**:`route`(`ResolvedRoute`/`ResolvedRole`)= 编排↔调用唯一接口。
- **调用(实际执行)**:拿 `route` 真正调。两个消费方:graph-agent(原生 ChatX)/ copilot(交回 studio claude_agent_sdk)。
- 决策与理由(client 层 A' 重设计决策)已**分散留底进各模块文档**(每模块 §4 用户原话 + §5 决策+动机),不再单独引用外部文件。各决策主落点:
  - **D1**(否决 A、保留编排外壳)→ [`07-orch-fallback-circuit-probe`](./07-orch-fallback-circuit-probe/mvp1-alignment.md) / [`13-x-tracing-events-exceptions`](./13-x-tracing-events-exceptions/mvp1-alignment.md)
  - **D2**(编排/调用分离)→ [`01-handoff-interface`](./01-handoff-interface/mvp1-alignment.md)(权威，copilot 用例并入此处) / [`predict-migration-to-engine`](./predict-migration-to-engine.md)
  - **D3**(gateway 可复用、前端不归 gateway)→ [`01-handoff-interface`](./01-handoff-interface/mvp1-alignment.md)(权威) / studio `llm-copilot-http-api`(`docs/studio/mvp1/04_platform/llm-copilot-http-api/`，router=③a 适配壳)
  - **F1**(base_url 保存时归一化)→ [`03-orch-credentials-endpoints`](./03-orch-credentials-endpoints/mvp1-alignment.md)(权威)
  - **F2**(retry 保留 ChatX 瞬时重试)→ [`07-orch-fallback-circuit-probe`](./07-orch-fallback-circuit-probe/mvp1-alignment.md) / [`09-inv-invocation-runtime`](./09-inv-invocation-runtime/mvp1-alignment.md)
  - **M5**(错误分类真实语义,401/402/403/404=fallback)→ [`06-orch-error-classification`](./06-orch-error-classification/mvp1-alignment.md)(权威)
  - **M4**(predict mock=业务逻辑→engine)→ [`predict-migration-to-engine`](./predict-migration-to-engine.md)

## 模块清单(覆盖代码来自 Explore 清点,100%)

> ⚠️ 标「共享」的文件:`gateway_chat_model.py` 的 fallback / probe / 熔断 / usage 编排步骤写进 07,单 route ChatX invoke / 结果桥接写进 09;`client_manager.py` 现只覆盖 probe / 熔断 / usage 健康职责,旧 `_call_*` provider 调用已迁到 `ordinary_chat.py` / `route_chat_model_factory.py`。

### 编排层
| 文件夹 | 覆盖代码 | 职责 / 必须解释 |
|---|---|---|
| `02-orch-role-resolution` | `registry/resolver.py:resolve_role`、`resolver.py:ModelResolver`、`services/gateway_resolver.py`、`services/llm_role_materializer.py` | role→route 全流程;fallback 链排序;未配置跳过(WARNING);空链报错;`model_override`;materialize 投影。baseline 含 5-25 回归;mvp1 跳过语义 + 暴露「role→route」一等 API |
| `03-orch-credentials-endpoints` | `registry/contracts.py`、`registry/credentials.py`、`registry/storage.py:compute_credential_fingerprint`、`services/llm_credentials.py`、`services/llm_roles.py`、`services/llm_paths.py` | `credential_ref` 取密钥(不落明文);endpoint;**base_url 归一化(保存时,每 protocol 固定规则)**;凭证指纹;storage seam。baseline:base_url 原样透传(头号根因);mvp1:保存时归一化 + 调用幂等双保险 |
| `04-orch-registry-schema` | `registry/schema.py`、`registry/__init__.py`、`registry/canonical.py:canonicalize_model`、`models/llm_config.py`、`models.py`(gateway,占位) | 每个数据结构字段含义;canonical 分组;snapshot v4/v2 加载校验;studio↔gateway schema 衔接 |
| `05-orch-capabilities-and-models` | `registry/capabilities.py`、`registry/profile_selector.py:select_verified_profile`、`registry/lint.py:lint_role_routes`、`services/llm_model_identity.py`、`services/llm_notable_models.py`、`services/llm_route_capabilities.py`、`services/llm_model_groups.py` | capability 规范化/探测;**lint 只 warn/block、不驱动选型**(决策);profile 选择;模型身份/分组/notable 投影 |
| `06-orch-error-classification` | `registry/error_classification.py:classify_exception/classify_error_context` | 真实语义表(401/402/403/404 与 400-capability → **fallback**,非 fail-fast);decision 映射。mvp1 **不变**;纠正多处文档错误简写 |
| `07-orch-fallback-circuit-probe` | `gateway_chat_model.py:_generate`(编排步骤,共享)、`client_manager.py:probe_provider/is_provider_marked_down/mark_provider_down`(共享)、`registry/probe_contracts.py`、`services/copilot_test.py`、`services/llm_health_store.py` | fallback 循环逐步;熔断 TTL;probe 1-token 真请求;**retry 保留 ChatX 瞬时重试(不设 0)**;截断升级重试搬到本层 |
| `08-orch-test-status-ssot` | `services/llm_state_projection.py:project_provider_model_state`、`services/llm_import_drafts.py`(legacy 名) | 探测→持久化→投影→复用(**用户核心目标**);UI state(6 态:ready/historical_ready/untested/failed/cooling_down/off，已取消 needs_setup);Probe Knowledge Catalog（探测知识库）+ evidence library。baseline 前端易失态;mvp1 后端 SSOT 回写 |

### 调用层
| 文件夹 | 覆盖代码 | 职责 / 必须解释 |
|---|---|---|
| `09-inv-invocation-runtime` | `gateway_chat_model.py:_dispatch/_invoke_with_token_escalation/_build_chat_result/_build_chat_result_from_ai_message`、`ordinary_chat.py:dispatch_ordinary_chat/_call_*`、`models.py:GenericRouteChatModel` | invoke 流程;**retry(ChatX 瞬时重试);截断升级;thinking 不拍平;从 `usage_metadata` 取 usage + 注入 route metadata**。baseline 已记录旧 `client_manager._call_*` 退役;MVP1 主路径为原生 ChatX,generic ordinary path 在 `ordinary_chat.py` |
| `10-inv-route-chat-model-factory` | `route_chat_model_factory.py:RouteChatModelFactory`、`models.py:GenericRouteChatModel`、`provider_profiles.py` | `ResolvedRoute`→原生 ChatX;base_url 双保险;init-kwargs;范本 [chatx-provider-patterns.md](./references/chatx-provider-patterns.md)、[chatx-provider-patterns.md](./references/chatx-provider-patterns.md)。WS-1 后模块源码已存在,剩余为 generic 完整性 deferred |
| `11-inv-provider-profiles` | `provider_profiles.py:ProviderProfile/apply_provider_profile_layers`、`route_chat_model_factory.py:_apply_profiles` | provider 差异 = init-kwargs 表;何时子类覆盖单方法(deerflow `PatchedChatDeepSeek`);**绝不重写整套消息转换**。WS-1 后最小 profile registry 已存在,后续按需收束 provider-specific thinking |

> **copilot SDK 调用（原模块 12）已移交 studio**：按判据它是 ③a 应用（copilot 的实际调用方式，绑 `claude_agent_sdk`），gateway 库不感知 copilot——只把 `copilot_chat` 当普通 role 解析成 route（[`01-handoff-interface`](./01-handoff-interface/mvp1-alignment.md) 的 route 级 API）。SDK 调用 / session / env 注入 / 事件翻译 / 假测试见 `docs/studio/mvp1/02_capabilities/copilot-assist/` + `01_workflows/00_settings-ux-spec.md` §3.8/§3.4；两个 base_url 归一化助手归 [`03-orch-credentials-endpoints`](./03-orch-credentials-endpoints/mvp1-alignment.md)（③b 归一化原语）。

### 交接 / 横切 / API
| 文件夹 | 覆盖代码 | 职责 / 必须解释 |
|---|---|---|
| `01-handoff-interface` | `protocol.py:ModelResolverProtocol.resolve/resolve_routes`、`resolver.py:ModelResolver.resolve_routes`、`__init__.py`、`apps/studio/backend/app/models/copilot.py`(ws 事件)+ 引用 `registry/schema.py:ResolvedRoute/ResolvedRole` | `route` 契约每字段;resolve API 契约;两个消费方各取什么。baseline:route 级 public API 已落地;剩余下游接线与公共门面导出 |
| `13-x-tracing-events-exceptions` | `events.py:LLMFallbackEvent`、`exceptions.py`、`tracing.py:emit_llm_fallback_event` | fallback 事件 payload(含 from/to route 诊断);各异常类型语义与触发点 |

> **HTTP 适配壳（原模块 14）已移交 studio**：`routers/llm.py`、`routers/copilot.py` = ③a Studio HTTP 适配壳（HTTP 端点形状 / job·进度包装 / DTO 投影绑死 studio 调用方式 + 存储介质），不是 ③b gateway 公共内核。它 delegate 的能力内核（base_url 归一化 / capability / probe 策略 / materialize / 6 态 / Probe Knowledge Catalog / endpoint 拆分）才是 ③b 公共。文档见 `docs/studio/mvp1/04_platform/llm-copilot-http-api/`。

### Predict(单独文档,非 baseline+alignment 模块)
[`predict-migration-to-engine.md`](./predict-migration-to-engine.md):`predict_interception.py`、`services/predictor.py`、`services/diagnostic_export.py`、`models/runs.py`、`protocol.py:PredictContext`。决策:mock/模拟移交 engine,gateway 只留「role→route」。

## 写作 bar(逐条强制)
1. 出现任何类/函数 → 紧跟一句话说清它干什么,**禁止只丢名字**。
2. 执行逻辑用编号步骤(输入→中间→输出,关键分支走哪条、为什么)。
3. 讲决策原因(对比被否决做法),不只写「是什么」。
4. 每个论断挂 `file:func` 或 `:行号`(clue/证据)。
5. `baseline.md` 写现状 + 覆盖率;`mvp1-alignment.md` 写目标 + 已实现/差异 + 决策 + 代码索引 + 覆盖率。
6. 单文件 >~400 行 → 在本模块文件夹再拆一级,并在此登记。
7. 只写文档;代码问题记文末「待办/疑点」,不改代码。
8. 历史材料:`../mvp0/{logic-explained.md, baseline.md, mvp0-alignment.md}`只能用于核对迁移背景,不得作为 MVP1 SSOT 或复用 MVP0 INDEX;MVP1 横切映射以 [`DESIGN_UNITS_INDEX.md`](./DESIGN_UNITS_INDEX.md) 为准。
