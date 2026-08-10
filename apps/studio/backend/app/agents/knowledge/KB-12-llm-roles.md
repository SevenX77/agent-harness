---
related:
  - KB-00-hub
  - KB-04-agent-nodes
  - KB-13-studio-gates-tools
---

> Distilled from: `packages/graph-agent-gateway/src/graph_agent_gateway/registry/` & `packages/graph-agent-gateway/src/graph_agent_gateway/role_materialization.py` & `docs/graph-agent-gateway/mvp1/README.md`

# KB-12: LLM Roles & Gateway Routing

The大模型 Gateway provides a robust, decoupled layer between high-level agent intents and specific model API endpoints. It manages credentials, endpoints, routes, roles, and automated fallbacks.

## 1. The Gateway Concept Chain
To map a user's request to a running 대형 언어 모델 (LLM) instance, the gateway executes the following conceptual chain:

```text
Credential ──> Endpoint ──> Route ──> Role ──> GatewayChatModel (Fallback)
```

1.  **Credential**: Manages references to keys, authorization tokens, or signature configs. The gateway avoids storing raw secrets/passwords, relying on local environment variables or host credential stores.
2.  **Endpoint**: Declares the target API entry point (e.g. `base_url`, `protocol`, headers). Endpoints enforce normalization rules on saving (e.g. trimming trailing slashes, stripping protocol prefixes depending on provider).
3.  **Route**: A concrete pairing of an `Endpoint`, a `Credential`, and a specific model capability profile (e.g. model name, temperature, thinking budget, and token limits).
4.  **Role**: A logical alias (e.g., `analyst`, `coder`, `critic`) mapped to a prioritized list of routes (the route chain). This provides a single-source-of-truth configuration so agent nodes refer to roles, not hardcoded model names.
5.  **GatewayChatModel**: The execution runtime wrapper. It takes a target role, resolves the route list, and attempts invocations. If a route fails or is marked down, it executes automated fallback down the chain.

## 2. Gateway State & Troubleshooting Table
The gateway tracks endpoint health under six discrete states: `ready`, `historical_ready`, `untested`, `failed`, `cooling_down`, and `off`. 

Use this table to diagnose common gateway errors:

| Symptom / Error | Possible Cause | Verification / Checkpoint |
|---|---|---|
| **Role Resolution Failure** (Empty Route List) | The requested role is not registered or has no active routes. | Check the `llm_roles.json` registry file via the gateway service; ensure the node's `llm_role` matches a registered role. |
| **401 Unauthorized** or Credential Errors | The credential reference points to an invalid or empty environment variable. | Verify that the target environment variable is loaded in the terminal/host session. |
| **Connection Timeout / 404 Not Found** | The endpoint `base_url` is invalid, malformed, or missing standard prefixes. | Inspect the endpoint configuration. Check that the normalization rules applied on save matched the required provider format. |
| **Route Cooling Down or Marked Down** | A route failed a health check or token execution and is in a cooldown period. | Wait for the cooldown TTL to expire or trigger a manual role test to force-revalidate. |
| **LLMRouteDecisionEvent Emitted** | The gateway skipped, probed, retried, escalated, fell back from, or ran out of routes. | Read the event's `decision` field in the trace: it names the outcome (`skipped_circuit_open` / `probe_failed` / `retried_same_route` / `dropped_rejected_settings` / `escalated_budget` / `fell_back` / `failed_terminal` / `answered` / `exhausted`) alongside the route, endpoint, provider status code and, for a fall-back, the route taking over. |
| **Answer produced without the role's runtime settings** | The provider refused the request with those settings on it, so the gateway asked the same route again without them (`dropped_rejected_settings`). | Runtime settings are preferences, not commands: the answer stands. The decision's `reason` names which preferences were dropped — check that setting against the route's model before trusting temperature / reasoning to apply here. |

## 3. Configuration Tooling & Write Capabilities
Conversation agents can manage LLM configurations using dedicated write tools, bypassing the need for manual file editing or UI click-throughs.

### Core Write Tools:
*   `create_llm_role(name, fallback_chain, intent?)`: Declares a new role. `fallback_chain` is a **flat `route_id` list** (each item a `route_id` string or `{route_id}` object); the server looks each route up in the registry, derives its `canonical_id`, and auto-groups — the client never assembles `model_groups` or supplies a `canonical_id`.
*   `update_llm_role(role_name, ops)`: Modifies an existing role. `ops.set_fallback_chain` takes the same **flat `route_id` list** (whole-list replace = add/remove/reorder; the exact `fallback_chain` shape `get_llm_roles` returns can be written straight back, extra fields like `runtime_settings` are ignored). `ops.model_fallback_enabled` toggles fallback; `ops.intent` patches thinking / max output tokens / temperature. Unknown `route_id`s are rejected at the boundary with every invalid route listed.

### Safety and Operation Guarantees:
1.  **Service-Layer Execution**: Tools route changes exclusively through the FastAPI service layer (`routers/llm.py`). They never modify registry files (`llm_roles.json`, etc.) directly, ensuring cascade updates and domain events are handled correctly.
2.  **No Raw Credentials**: Conversational write tools are prohibited from reading or writing credentials (raw API keys or secure passwords) to eliminate prompt injection risks. Key entry remains strictly restricted to host UI settings.
3.  **Summary and Revert UX**: Every successful modification returns a before/after configuration state. The Studio UI displays this as a change summary card featuring a one-click **Undo** button. Reverting a change writes the previous snapshot back via the same service-layer endpoint.
