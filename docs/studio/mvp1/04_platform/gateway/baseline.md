---
module: 04_platform/gateway
doc: baseline
status: FROZEN（现状对齐 pinned 代码 0d9fbaf；Gateway ③b 包已有 schema/resolver/fallback 代码；Studio 侧仍有 5 态投影、materializer、health/draft 等内核散在后端 ⚠️。）
binds_alignment: ./mvp1-alignment.md
binds_code: apps/studio/backend/app/services/llm_state_projection.py:ProviderUiState · apps/studio/backend/app/services/llm_role_materializer.py:materialize_role · apps/studio/backend/app/services/llm_health_store.py:SqliteLlmHealthStore · apps/studio/backend/app/routers/llm.py:router
units: [settings-six-state-provider-health, model-group-role-materialization, copilot-sdk-test-parity]
---

# gateway — Baseline（当下代码实现逻辑）

> **Scope**: Studio 对 graph-agent-gateway ③b 公共内核的消费边界：6 态投影、materialize/role resolution、endpoint 标准化、fallback/probe 与 copilot route 解析。
> **现状一句话**: Gateway ③b 包已有 schema/resolver/fallback 代码；Studio 侧仍有 5 态投影、materializer、health/draft 等内核散在后端 ⚠️。

## UI/UX
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Registry schema | Gateway schema defines provider/route status, capabilities, runtime policy, snapshots, resolved route/role. | `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:schema（L19）`, `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:RegistrySnapshot（L403）` |
| Role resolver | Gateway resolver filters executable routes and returns resolved role/fallback chains. | `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:resolver（L26）`, `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:resolve_role（L33）` |
| Model resolver | graph-agent gateway adapter resolves role into chat model runtime. | `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:resolve（L73）`, `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:resolve（L92）` |
| Chat fallback | GatewayChatModel iterates fallback candidates, probes/classifies, and emits fallback behavior. | `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:_generate（L96）`, `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:_generate（L111）` |
| Capability descriptors | Gateway builds runtime setting descriptors for capabilities. | `packages/graph-agent-gateway/src/graph_agent_gateway/registry/capabilities.py:build_runtime_setting_descriptors（L205）` |
| State projection | Studio backend state projection still uses five states with `needs_setup`. | `apps/studio/backend/app/services/llm_state_projection.py:llm_state_projection（L12）`, `apps/studio/backend/app/services/llm_state_projection.py:project_provider_model_state（L23）` |
| Role materializer | Studio backend materializes roles from model groups, skipping unusable states and building fallback chains. | `apps/studio/backend/app/services/llm_role_materializer.py:materialize_role（L27）`, `apps/studio/backend/app/services/llm_role_materializer.py:materialize_role（L85）` |
| Health store | Studio backend stores runtime circuits in sqlite. | `apps/studio/backend/app/services/llm_health_store.py:llm_health_store（L14）`, `apps/studio/backend/app/services/llm_health_store.py:SqliteLlmHealthStore（L26）` |
| HTTP glue | LLM router exposes registry/roles/tests/model groups; detailed HTTP contract is in `llm-copilot-http-api/`. | `apps/studio/backend/app/routers/llm.py:EndpointModelTestResponse（L312）`, `docs/studio/mvp1/04_platform/llm-copilot-http-api/baseline.md:baseline（L1）` |

## 前端逻辑
N/A。

## 后端功能
| 面 | 现状 | 证据（文件:符号名） |
|---|---|---|
| Registry schema | Gateway schema defines provider/route status, capabilities, runtime policy, snapshots, resolved route/role. | `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:schema（L19）`, `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:RegistrySnapshot（L403）` |
| Role resolver | Gateway resolver filters executable routes and returns resolved role/fallback chains. | `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:resolver（L26）`, `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:resolve_role（L33）` |
| Model resolver | graph-agent gateway adapter resolves role into chat model runtime. | `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:resolve（L73）`, `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:resolve（L92）` |
| Chat fallback | GatewayChatModel iterates fallback candidates, probes/classifies, and emits fallback behavior. | `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:_generate（L96）`, `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:_generate（L111）` |
| Capability descriptors | Gateway builds runtime setting descriptors for capabilities. | `packages/graph-agent-gateway/src/graph_agent_gateway/registry/capabilities.py:build_runtime_setting_descriptors（L205）` |
| State projection | Studio backend state projection still uses five states with `needs_setup`. | `apps/studio/backend/app/services/llm_state_projection.py:llm_state_projection（L12）`, `apps/studio/backend/app/services/llm_state_projection.py:project_provider_model_state（L23）` |
| Role materializer | Studio backend materializes roles from model groups, skipping unusable states and building fallback chains. | `apps/studio/backend/app/services/llm_role_materializer.py:materialize_role（L27）`, `apps/studio/backend/app/services/llm_role_materializer.py:materialize_role（L85）` |
| Health store | Studio backend stores runtime circuits in sqlite. | `apps/studio/backend/app/services/llm_health_store.py:llm_health_store（L14）`, `apps/studio/backend/app/services/llm_health_store.py:SqliteLlmHealthStore（L26）` |
| HTTP glue | LLM router exposes registry/roles/tests/model groups; detailed HTTP contract is in `llm-copilot-http-api/`. | `apps/studio/backend/app/routers/llm.py:EndpointModelTestResponse（L312）`, `docs/studio/mvp1/04_platform/llm-copilot-http-api/baseline.md:baseline（L1）` |

## 当前边界（gateway 现在不是什么）
- 不复制 graph-agent-gateway ③b 内核实现/决策；只链接 SSOT。
- HTTP endpoint 形状归 `llm-copilot-http-api`，本档只写 gateway 消费边界。

## baseline / alignment 差异（测试锚点）
| 维度 | 现状（baseline） | 目标（alignment） |
|---|---|---|
| 六态归属 | `llm_state_projection.py` 仍旧 5 态且应下沉 ③b ⚠️ | 6 态标准投影由 gateway ③b 内核提供，Studio 只渲染/消费 |
| materialize | Studio materializer/llm.py 仍混 HTTP glue + 内核 ⚠️ | materialize/endpoint 标准化/role resolve 归 ③b，Studio 只传意图/包装 HTTP |
| copilot route | Copilot SDK 调用归 ③a，route 解析归 ③b | gateway 只把 `copilot_chat` 当 role 解析，不感知 SDK session |
> **验"是否按目标改了"**：1. 六态归属；2. materialize；3. copilot route。

## 读代码主路径提示
`apps/studio/backend/app/services/llm_state_projection.py:ProviderUiState` → `apps/studio/backend/app/services/llm_role_materializer.py:materialize_role` → `apps/studio/backend/app/services/llm_health_store.py:SqliteLlmHealthStore` → `apps/studio/backend/app/routers/llm.py:router`。

> 旧 Coverage/Drift 暂存 [`_migrated-coverage-drift.md`](../../_migrated-coverage-drift.md#04-platform-gateway)（迁移期安全网，代码实现验证后删）。

## 交叉引用（链接, 不复制）
[alignment](./mvp1-alignment.md)（目标,双向）· `studio-settings` · `settings` · `llm-copilot-http-api` · `copilot-assist` · `docs/graph-agent-gateway/mvp1/`
