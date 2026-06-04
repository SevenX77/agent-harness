# gateway Baseline

Status: gateway package and Studio HTTP glue are both live; canonical state projection and copilot probe parity need alignment.

Source workflow: `01_workflows/00_settings-ux-spec.md`.

## Current Code Index

| Surface | Current behavior | Evidence |
|---|---|---|
| Registry schema | Gateway schema defines provider/route status, capabilities, runtime policy, snapshots, resolved route/role. | `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:19`, `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py:403` |
| Role resolver | Gateway resolver filters executable routes and returns resolved role/fallback chains. | `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:26`, `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py:33` |
| Model resolver | graph-agent gateway adapter resolves role into chat model runtime. | `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:73`, `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py:92` |
| Chat fallback | GatewayChatModel iterates fallback candidates, probes/classifies, and emits fallback behavior. | `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:96`, `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py:111` |
| Capability descriptors | Gateway builds runtime setting descriptors for capabilities. | `packages/graph-agent-gateway/src/graph_agent_gateway/registry/capabilities.py:205` |
| State projection | Studio backend state projection still uses five states with `needs_setup`. | `apps/studio/backend/app/services/llm_state_projection.py:12`, `apps/studio/backend/app/services/llm_state_projection.py:23` |
| Role materializer | Studio backend materializes roles from model groups, skipping unusable states and building fallback chains. | `apps/studio/backend/app/services/llm_role_materializer.py:27`, `apps/studio/backend/app/services/llm_role_materializer.py:85` |
| Health store | Studio backend stores runtime circuits in sqlite. | `apps/studio/backend/app/services/llm_health_store.py:14`, `apps/studio/backend/app/services/llm_health_store.py:26` |
| HTTP glue | LLM router exposes registry/roles/tests/model groups; detailed HTTP contract is in `llm-copilot-http-api/`. | `apps/studio/backend/app/routers/llm.py:312`, `docs/studio/mvp1/04_platform/llm-copilot-http-api/baseline.md:1` |

## Current Coverage

- live: registry schema, resolver, model adapter, chat fallback, role materializer, health/circuit store, HTTP routes.
- stale/target gap: canonical six-state projection, copilot SDK test path parity, clearer split between HTTP glue and gateway library.

## Known Drift

- Settings spec asks for canonical six-state model; current backend projection still emits `needs_setup` (`apps/studio/backend/app/services/llm_state_projection.py:12`).
- Copilot role tests have a distinct probe path from real Copilot chat runtime (`apps/studio/backend/app/routers/llm.py:2150`, `apps/studio/backend/app/services/copilot.py:201`).
