# Design: LLM Provider Intelligence V2 (Deterministic Resolver Architecture)

## 1. Architecture Overview

The design introduces a shared LLM registry core that is used by Graph Agent Engine and Studio Backend. Studio Frontend consumes backend DTOs and does not own canonicalization or route resolution logic.

```text
llm_credentials.json
  provider_endpoints
  provider_routes
  provider_import_drafts

llm_roles.yaml
  roles[*].fallback_chain[*].route_id
  roles[*].lint_requirements

graph_agent.llm_registry
  schema
  storage
  canonical mapper
  deterministic resolver
  linter

engine runtime
  ModelResolver -> GatewayChatModel -> LLMClientManager

studio backend
  API routes -> llm_registry -> atomic storage writes

studio frontend
  API DTOs -> route grouped UI -> role fallback chain editor
```

The central invariant is that role execution always starts from a declared `route_id` and ends at one exact `provider_model_id`.

## 2. Shared Module Boundary

Create a cohesive module:

```text
packages/graph-agent/src/graph_agent/llm_registry/
  __init__.py
  schema.py
  storage.py
  canonical.py
  resolver.py
  lint.py
  probe_contracts.py
```

Responsibilities:

- `schema.py`: shared dataclasses/Pydantic models for endpoint, route, capability, role chain, lint result, and import draft.
- `storage.py`: load and validate `llm_credentials.json` and `llm_roles.yaml`; join them into a registry snapshot.
- `canonical.py`: route-safe canonical mapping with explicit transport normalization and curated aliases.
- `resolver.py`: resolve role names and route IDs into ordered physical route chains.
- `lint.py`: evaluate role lint requirements against route capabilities.
- `probe_contracts.py`: shared probe request/result structures used by backend probes and engine diagnostics.

Non-responsibilities:

- It must not expose FastAPI route handlers.
- It must not import Studio backend modules.
- It must not render UI.
- It must not instantiate LangChain or SDK clients.

`packages/graph-agent/src/graph_agent/models/resolver.py` remains a runtime adapter that calls `llm_registry.resolver` and builds `GatewayChatModel`.

## 3. Storage Schemas

### 3.1 Credentials File

`~/.studio/llm_credentials.json` becomes schema version 4.

```json
{
  "schema_version": 4,
  "provider_endpoints": {
    "anthropic-official": {
      "endpoint_id": "anthropic-official",
      "display_name": "Anthropic Official",
      "protocol": "anthropic_compatible",
      "base_url": "https://api.anthropic.com",
      "api_key": "<stored-anthropic-secret>",
      "status": "verified",
      "last_test_at": "2026-05-24T00:00:00Z",
      "last_test_message": "Connected",
      "metadata": {
        "provider_brand": "anthropic"
      }
    },
    "openrouter-prod": {
      "endpoint_id": "openrouter-prod",
      "display_name": "OpenRouter",
      "protocol": "openai_compatible",
      "base_url": "https://openrouter.ai/api/v1",
      "api_key": "<stored-openrouter-secret>",
      "status": "verified",
      "last_test_at": "2026-05-24T00:00:00Z",
      "last_test_message": "Connected",
      "metadata": {
        "provider_brand": "openrouter"
      }
    }
  },
  "provider_routes": {
    "anthropic-official:claude-sonnet-4.6": {
      "route_id": "anthropic-official:claude-sonnet-4.6",
      "endpoint_id": "anthropic-official",
      "route_slug": "claude-sonnet-4.6",
      "provider_model_id": "claude-sonnet-4-6",
      "canonical_id": "claude-sonnet-4.6",
      "display_name": "Claude Sonnet 4.6",
      "status": "verified",
      "capabilities": {
        "max_input_tokens": {
          "value": 200000,
          "source": "provider_doc"
        },
        "max_output_tokens": {
          "value": 8192,
          "source": "probed_verified",
          "observed_at": "2026-05-24T00:00:00Z",
          "message": "Accepted max_tokens=8192 probe"
        },
        "thinking_protocol": {
          "value": "anthropic_v1",
          "source": "probed_verified",
          "observed_at": "2026-05-24T00:00:00Z"
        },
        "tool_protocol": {
          "value": "anthropic_tools",
          "source": "provider_doc"
        }
      }
    },
    "openrouter-prod:anthropic.claude-sonnet-4.6": {
      "route_id": "openrouter-prod:anthropic.claude-sonnet-4.6",
      "endpoint_id": "openrouter-prod",
      "route_slug": "anthropic.claude-sonnet-4.6",
      "provider_model_id": "anthropic/claude-sonnet-4.6",
      "canonical_id": "claude-sonnet-4.6",
      "display_name": "Claude Sonnet 4.6 via OpenRouter",
      "status": "verified",
      "capabilities": {
        "max_input_tokens": {
          "value": 200000,
          "source": "api_list"
        },
        "tool_protocol": {
          "value": "openai_tools",
          "source": "probed_verified",
          "observed_at": "2026-05-24T00:00:00Z"
        }
      }
    }
  },
  "provider_import_drafts": {}
}
```

Secrets:

- `api_key` is stored only in the local credentials file.
- `GET /api/llm/registry` and `GET /api/llm/credentials` must redact `api_key` unless an explicit internal-only path needs the value.
- PUT/PATCH endpoints may accept empty `api_key` to preserve the existing secret for that endpoint.

### 3.2 Roles File

`config/llm_roles.yaml` moves to explicit route chains.

```yaml
schema_version: 2

roles:
  graph_agent:
    system_prompt_prefix: ""
    fallback_chain:
      - route_id: anthropic-official:claude-sonnet-4.6
        temperature: null
        max_output_tokens: 8192
      - route_id: openrouter-prod:anthropic.claude-sonnet-4.6
        temperature: null
        max_output_tokens: 8192
    lint_requirements:
      thinking: error
      tool_calling: warn

  copilot_chat:
    system_prompt_prefix: ""
    fallback_chain:
      - route_id: openrouter-prod:anthropic.claude-sonnet-4.6
        temperature: 0.7
        max_output_tokens: 4096
    lint_requirements:
      thinking: warn
      tool_calling: off
```

The old `models`, `providers`, `active_model`, `model_fallback`, `peer_model_groups`, and provider short-code maps are replaced for this prototype. If a compatibility reader is useful for local migration, it should live in a one-way migration script rather than in the core resolver.

## 4. Route ID Rules

`route_id` is a durable internal identity and must not contain raw provider model syntax.

Rules:

- `endpoint_id`: lowercase slug matching `[a-z0-9][a-z0-9._-]*`
- `route_slug`: lowercase slug matching `[a-z0-9][a-z0-9._-]*`
- `route_id`: `<endpoint_id>:<route_slug>`
- `provider_model_id`: exact API model string, stored separately
- `canonical_id`: grouping label, stored separately

Route slug generation:

1. Prefer a sanitized canonical ID when the provider model maps clearly to one route.
2. Preserve provider/vendor disambiguation in the slug when one endpoint exposes multiple vendors, for example `anthropic.claude-sonnet-4.6`.
3. If a generated slug collides under the same endpoint, append a deterministic suffix based on discovery order or a short stable hash.
4. Never infer `provider_model_id` by reversing the slug.

## 5. Canonicalization Design

Canonicalization is implemented in `llm_registry/canonical.py`.

Inputs:

- `endpoint_id`
- provider brand metadata when known
- protocol
- raw `provider_model_id`
- optional provider API metadata
- curated alias rules

Outputs:

- `canonical_id`
- `display_name`
- mapping explanation
- mapping confidence class: `transport_normalized`, `explicit_alias`, or `orphan`

Allowed mappings:

- **Transport normalization**: strip known proxy routing prefixes where the endpoint is known to expose raw vendor model IDs, for example OpenRouter `anthropic/claude-sonnet-4.6` -> `claude-sonnet-4.6`.
- **Explicit alias**: curated KV rule with tests, for example `qiniu-claude-sonnet-v1` -> `claude-sonnet-4.6`.
- **Orphan**: no safe mapping; canonical ID is derived from the route's own sanitized model ID and is not grouped with others.

Forbidden by default:

- Merging `latest` into a dated release.
- Merging `fast` into a base model.
- Merging `thinking` variants into non-thinking variants.
- Merging dated snapshots based only on shared family names.
- Merging across vendors based on fuzzy string similarity.

Rule storage:

- Default safe rules live in the shared module.
- Project-specific curated rules may live in `config/llm_canonical_rules.yaml`.
- Rules require positive and negative tests before they are used by default.

## 6. Capability Model and Linter

### 6.1 Capability Values

Capability values are intentionally shallow and inspectable.

```python
CapabilityValue = {
    "value": Any,
    "source": Literal[
        "api_list",
        "provider_doc",
        "agent_draft",
        "manual",
        "probed_verified",
    ],
    "observed_at": str | None,
    "message": str | None,
}
```

Common capability keys:

- `max_input_tokens`
- `max_output_tokens`
- `thinking_protocol`
- `tool_protocol`
- `structured_output_protocol`
- `vision`

The capability object is not a route-selection policy. It is metadata for display, linting, verification, and fail-fast validation.

### 6.2 Lint Requirements

Role lint requirement values:

```yaml
lint_requirements:
  thinking: error
  tool_calling: warn
  structured_output: off
```

Linter outputs:

```json
{
  "role_name": "graph_agent",
  "route_id": "openrouter-prod:anthropic.claude-sonnet-4.6",
  "severity": "warn",
  "capability": "thinking",
  "message": "Route has no probed thinking_protocol capability",
  "source": "missing"
}
```

Save behavior:

- `warn` lints do not block save.
- `error` lints block save when the incompatibility is known.
- Missing/unverified information for an `error` requirement should prompt probing. If the user refuses probing, save remains blocked unless they explicitly lower the lint requirement.

Runtime behavior:

- If a role reaches runtime with an `error` requirement that the route cannot satisfy, engine fails before making the LLM request.
- Runtime must not replace that route with another route based on the capability.

## 7. Deterministic Resolver

`llm_registry.resolver` loads a registry snapshot from credentials plus roles.

Resolution flow:

1. Read role by name.
2. Read role `fallback_chain` in declared order.
3. Validate each `route_id` exists.
4. Join route to endpoint by `endpoint_id`.
5. Validate endpoint has protocol, base URL, and credential.
6. Run linter.
7. Return ordered `ResolvedRoute` records.

`ResolvedRoute` contains:

- `role_name`
- `route_id`
- `endpoint_id`
- `protocol`
- `base_url`
- `api_key`
- `provider_model_id`
- `canonical_id`
- `display_name`
- `capabilities`
- per-chain params such as `temperature` and `max_output_tokens`

Engine integration:

- `graph_agent.models.resolver.ModelResolver` calls shared registry resolution.
- `GatewayChatModel` receives a `ResolvedRole` backed by route records.
- `LLMClientManager` uses endpoint credentials from `ResolvedRoute`, not environment variables.
- Client cache key includes endpoint ID and credential fingerprint.

Runtime fallback:

- The chain order is fixed.
- Fallback is allowed for network/timeouts/retryable 5xx/rate-limit/marked-down cases.
- Invalid model, unsupported capability, bad request, missing credential, or schema validation failures fail fast.

## 8. Studio Backend API Design

### 8.1 Registry Read API

`GET /api/llm/registry`

Returns a redacted snapshot:

```json
{
  "provider_endpoints": {},
  "provider_routes": {},
  "canonical_groups": [
    {
      "canonical_id": "claude-sonnet-4.6",
      "display_name": "Claude Sonnet 4.6",
      "routes": [
        "anthropic-official:claude-sonnet-4.6",
        "openrouter-prod:anthropic.claude-sonnet-4.6"
      ]
    }
  ],
  "roles": {},
  "lint_results": []
}
```

### 8.2 Endpoint and Route Mutation APIs

`PUT /api/llm/registry/endpoints`

- Replaces editable endpoint fields.
- Preserves secrets when `api_key` is empty.
- Invalidates client fingerprint/version when secret, protocol, or base URL changes.

`POST /api/llm/endpoints/{endpoint_id}/test`

- Tests authentication and model listing for one endpoint.
- Updates endpoint status and may create route candidates from model list results.

`POST /api/llm/routes/{route_id}/probe`

- Probes one physical route.
- Request names desired capabilities.
- Updates only that route's capability fields and status.

### 8.3 Import Draft APIs

`POST /api/llm/import-drafts`

- Body includes user URL and optional endpoint hint.
- Starts Agent-assisted scrape.
- Returns `draft_id`.

`GET /api/llm/import-drafts/{draft_id}`

- Returns draft status, extracted endpoint candidates, route candidates, probe results, and diff against active config.

`POST /api/llm/import-drafts/{draft_id}/probe`

- Probes draft endpoint/routes.
- Updates draft field statuses.

`POST /api/llm/import-drafts/{draft_id}/apply`

- Applies selected draft changes.
- Verified executable routes become `status: verified`.
- Explicitly confirmed unverified executable routes become `status: unverified_manual`.
- Agent-only metadata remains tagged with `source: agent_draft`.

### 8.4 Role APIs

Existing role read/write endpoints may remain, but their DTOs change to the new role chain schema.

- Backend validates `route_id` references before saving.
- Backend returns lint results with role payloads.
- Backend blocks saves with `error` lints unless the request explicitly changes the requirement severity.

## 9. Agent Import Draft Flow

1. User enters a provider docs URL or pricing/model-list URL.
2. Backend starts an import draft job.
3. Agent extracts:
   - provider brand
   - protocol candidates
   - base URL candidates
   - auth header shape
   - model IDs
   - documented capabilities
   - source snippets/URLs for each claim
4. Backend stores the draft separately from active config.
5. Backend probes the endpoint and selected model candidates.
6. Backend computes a diff against active endpoints/routes.
7. Frontend shows diff:
   - verified additions
   - unverified additions
   - conflicting active fields
   - removed/disabled suggestions
8. User applies selected changes.

Promotion rules:

- A new endpoint may be auto-created only when endpoint probe succeeds and no existing endpoint is overwritten.
- A route may be auto-created as `verified` only when model probe succeeds.
- A route may be created as `unverified_manual` only after explicit user confirmation.
- Active routes are never overwritten by Agent output without a diff confirmation.

## 10. Studio Frontend Design Constraints

The frontend follows `docs/development/FRONTEND_UI_SPEC.md` section 2.

Required UI shape:

- API Keys page evolves into endpoint management.
- Roles page uses an Available Routes sidebar grouped by `canonical_id`.
- A route card shows:
  - canonical display name
  - endpoint label
  - provider model ID
  - verification status
  - capability badges
  - lint state
- Dragging a route into a role appends that exact `route_id` to the role's `fallback_chain`.
- Role fallback rows show route ID or endpoint/model labels, not legacy short codes.
- Probe actions use local `Button`, `Badge`, `Tooltip`, `Dialog`, `Alert`, `ScrollArea`, and `Field` wrappers.
- Long route/model/provider strings use `overflow-wrap:anywhere` and never break card layout.
- Search supports canonical ID, provider model ID, endpoint label, provider brand, and route ID.
- Warnings/errors from linter must be visible without relying only on color.

Frontend must not:

- build route records from raw strings;
- reimplement canonical mapping;
- hide physical `provider_model_id`;
- add dynamic model selection controls that imply intent routing.

## 11. Existing Code Impact

### 11.1 Engine

Primary files affected:

- `packages/graph-agent/src/graph_agent/config/llm_config.py`
- `packages/graph-agent/src/graph_agent/models/resolver.py`
- `packages/graph-agent/src/graph_agent/models/gateway_chat_model.py`
- `packages/graph-agent/src/graph_agent/models/llm_client_manager.py`
- `packages/graph-agent/src/graph_agent/cognitive/prompt.py`

Changes:

- Replace old model/provider short-code schema with route-chain role schema.
- Add credentials loading from the registry snapshot.
- Remove API key lookup as a required environment-variable path.
- Update fallback error classification.
- Include route diagnostics in logs and callback events.
- Update prompt-prefix resolution to read the new role schema.

### 11.2 Studio Backend

Primary files affected:

- `apps/studio/backend/app/models/llm_config.py`
- `apps/studio/backend/app/services/llm_credentials.py`
- `apps/studio/backend/app/services/llm_roles.py`
- `apps/studio/backend/app/services/llm_provider_test.py`
- `apps/studio/backend/app/routers/llm.py`
- `apps/studio/backend/app/services/copilot.py`

Changes:

- Replace `providers: list[ProviderCredential]` with endpoint/route/draft maps.
- Move canonical mapping to the shared registry module.
- Make provider tests create/update endpoint and route records.
- Add route-level probe endpoints.
- Add import draft lifecycle endpoints.
- Save roles as explicit route chains.
- Update Copilot provider resolution to use `route_id`.

### 11.3 Studio Frontend

Primary files affected:

- `apps/studio/frontend/src/api/llm.ts`
- `apps/studio/frontend/src/components/studio/settings/SettingsPage.tsx`
- `apps/studio/frontend/src/components/studio/settings/LlmRolesTab.tsx`
- `apps/studio/frontend/src/components/studio/settings/role-utils.ts`
- `apps/studio/frontend/src/components/studio/settings/llm-roles/*`
- `apps/studio/frontend/src/components/studio/settings/api-keys/*`
- `apps/studio/frontend/src/components/studio/api-keys/*`

Changes:

- Replace model/provider short-code DTOs with endpoint/route/draft DTOs.
- Replace Available Models with Available Routes grouped by canonical ID.
- Make drag/drop payload carry `route_id`.
- Show lint and probe states per route.
- Add import draft diff UI.
- Keep autosave serialized and stale-result safe.

## 12. Verification Plan

Unit tests:

- `llm_registry.schema` validates route IDs and endpoint IDs.
- `llm_registry.canonical` covers transport normalization, explicit aliases, and negative cases.
- `llm_registry.resolver` preserves route order and never dynamically selects by capability.
- `llm_registry.lint` handles `off`, `warn`, `error`, missing capability, and verified incompatibility.
- `LLMClientManager` uses credentials from resolved routes and invalidates cache on credential fingerprint change.

Backend tests:

- Endpoint save/load redacts secrets in responses.
- Endpoint test creates route candidates.
- Route probe updates only route capabilities.
- Import draft create/probe/apply honors verified and unverified rules.
- Role save blocks invalid route IDs and `error` lint failures.

Frontend tests:

- Available Routes groups by backend `canonical_id`.
- Route drag/drop writes `route_id`.
- Lint warning/error badges render with accessible text.
- Probe button triggers route probe flow.
- Import draft diff separates verified and unverified changes.

Manual verification:

- Run Studio frontend or Tauri shell.
- Verify endpoint test, route probe, import draft diff, role route drag/drop, and lint states.
- Check desktop and narrow widths.
- Confirm no horizontal overflow for long provider model IDs and route IDs.
