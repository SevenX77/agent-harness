---
milestone: MVP1
decision_record: ../../../.kiro/specs/studio-llm-gateway-redesign/client-layer-decision-record.md
coverage: 42 后端文件 100% 映射(Explore 清点);14 个模块 baseline/mvp1-alignment 已起草
status: 14 个模块文档已补齐,待实现阶段按待办推进
---

# MVP1 — 模块 manifest + 写作 brief

> 每个模块一个子文件夹,内含 `baseline.md`(现状)+ `mvp1-alignment.md`(目标)。
> 全部必须满足底部**写作 bar**——核心:**把每个类/函数解释清楚,不靠名字猜**。

## 架构:编排 → [route] → 调用

- **编排(准备期)**:role → 解析出该用哪条 `route`(含 fallback 顺序、熔断/probe 决策),**不调模型**。
- **交接**:`route`(`ResolvedRoute`/`ResolvedRole`)= 编排↔调用唯一接口。
- **调用(实际执行)**:拿 `route` 真正调。两个消费方:graph-agent(原生 ChatX)/ copilot(交回 studio claude_agent_sdk)。
- 决策与理由(A'、编排/调用分离、base_url 归一化、retry、错误分类):见 [决策记录](../../../.kiro/specs/studio-llm-gateway-redesign/client-layer-decision-record.md)。

## 模块清单(覆盖代码来自 Explore 清点,100%)

> ⚠️ 标「共享」的文件:`gateway_chat_model.py` / `client_manager.py` 的**编排步骤**写进 07、**调用步骤**写进 09;两篇各写各的那部分,交叉引用。

### 编排层
| 文件夹 | 覆盖代码 | 职责 / 必须解释 |
|---|---|---|
| `02-orch-role-resolution` | `registry/resolver.py:resolve_role`、`resolver.py:ModelResolver`、`services/gateway_resolver.py`、`services/llm_role_materializer.py` | role→route 全流程;fallback 链排序;未配置跳过(WARNING);空链报错;`model_override`;materialize 投影。baseline 含 5-25 回归;mvp1 跳过语义 + 暴露「role→route」一等 API |
| `03-orch-credentials-endpoints` | `registry/contracts.py`、`registry/credentials.py`、`registry/storage.py:compute_credential_fingerprint`、`services/llm_credentials.py`、`services/llm_roles.py`、`services/llm_paths.py` | `credential_ref` 取密钥(不落明文);endpoint;**base_url 归一化(保存时,每 protocol 固定规则)**;凭证指纹;storage seam。baseline:base_url 原样透传(头号根因);mvp1:保存时归一化 + 调用幂等双保险 |
| `04-orch-registry-schema` | `registry/schema.py`、`registry/__init__.py`、`registry/canonical.py:canonicalize_model`、`models/llm_config.py`、`models.py`(gateway,占位) | 每个数据结构字段含义;canonical 分组;snapshot v4/v2 加载校验;studio↔gateway schema 衔接 |
| `05-orch-capabilities-and-models` | `registry/capabilities.py`、`registry/profile_selector.py:select_verified_profile`、`registry/lint.py:lint_role_routes`、`services/llm_model_identity.py`、`services/llm_notable_models.py`、`services/llm_route_capabilities.py`、`services/llm_model_groups.py` | capability 规范化/探测;**lint 只 warn/block、不驱动选型**(决策);profile 选择;模型身份/分组/notable 投影 |
| `06-orch-error-classification` | `registry/error_classification.py:classify_exception/classify_error_context` | 真实语义表(401/402/403/404 与 400-capability → **fallback**,非 fail-fast);decision 映射。mvp1 **不变**;纠正多处文档错误简写 |
| `07-orch-fallback-circuit-probe` | `gateway_chat_model.py:_generate`(编排步骤,共享)、`client_manager.py:probe_provider/is_provider_marked_down/mark_provider_down`(共享)、`registry/probe_contracts.py`、`services/copilot_test.py`、`services/llm_health_store.py` | fallback 循环逐步;熔断 TTL;probe 1-token 真请求;**retry 保留 ChatX 瞬时重试(不设 0)**;截断升级重试搬到本层 |
| `08-orch-test-status-ssot` | `services/llm_state_projection.py:project_provider_model_state`、`services/llm_import_drafts.py` | 探测→持久化→投影→复用(**用户核心目标**);UI state(ready/untested/cooling_down/needs_setup);draft + evidence library。baseline 前端易失态;mvp1 后端 SSOT 回写 |

### 调用层
| 文件夹 | 覆盖代码 | 职责 / 必须解释 |
|---|---|---|
| `09-inv-invocation-runtime` | `gateway_chat_model.py:_build_chat_result`(调用步骤,共享)、`client_manager.py:_call_*/_call_with_token_escalation`(共享)、`models.py` | invoke 流程;**retry(ChatX 瞬时重试);截断升级;thinking 不拍平;从 `usage_metadata` 取 usage + 注入 route metadata**。baseline 自研 `_call_*`;mvp1 原生 ChatX |
| `10-inv-route-chat-model-factory` | **MVP1 新建**(现状逻辑散在 `client_manager`SDK 工厂 + `resolver` 实例化) | `ResolvedRoute`→原生 ChatX;base_url 双保险;init-kwargs;范本 `temp/deerflow/.../factory.py`、`temp/deepagents/.../_models.py`。baseline=无此模块/职责现由谁承担;mvp1 新建(A' 核心) |
| `11-inv-provider-profiles` | **MVP1 新建**(现状散在 `profile_selector`+`capabilities`+`client_manager` thinking) | provider 差异 = init-kwargs 表;何时子类覆盖单方法(deerflow `PatchedChatDeepSeek`);**绝不重写整套消息转换**。baseline=无;mvp1 新建(deepagents `ProviderProfile` 模式) |
| `12-inv-copilot-invocation` | `services/copilot.py:stream_query/_resolve_route_runtime/_deepseek_anthropic_base_url/_ark_anthropic_base_url` | copilot 拿 route 自己用 claude_agent_sdk 调(独立运行时);base_url→`ANTHROPIC_BASE_URL` env;spawn claude CLI;**假测试问题**(测试 SDK≠运行 SDK)。mvp1 统一从交接接口拿(已归一化)route |

### 交接 / 横切 / API
| 文件夹 | 覆盖代码 | 职责 / 必须解释 |
|---|---|---|
| `01-handoff-interface` | `protocol.py:ModelResolverProtocol`、`__init__.py`、`apps/studio/backend/app/models/copilot.py`(ws 事件)+ 引用 `registry/schema.py:ResolvedRoute/ResolvedRole` | `route` 契约每字段;resolve API 契约;两个消费方各取什么。baseline:route 未作一等输出;mvp1:route 成唯一交接物 |
| `13-x-tracing-events-exceptions` | `events.py:LLMFallbackEvent`、`exceptions.py`、`tracing.py:emit_llm_fallback_event` | fallback 事件 payload(含 from/to route 诊断);各异常类型语义与触发点 |
| `14-api-router` | `routers/llm.py`、`routers/copilot.py` | 每个 HTTP 端点干啥 + delegate 到哪个功能模块;save/test 端点;5000 行巨型 router(后续拆分计划) |

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
8. 素材源:`../mvp0/{logic-explained.md, baseline.md, mvp0-alignment.md}`(核对后引用,勿照抄过时内容)。
