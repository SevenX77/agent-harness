# Design: LLM Provider Intelligence V2 (Deterministic Resolver Architecture)

This spec supersedes `.kiro/specs/studio-api-keys-redesign/*` and deprecated LLM config specs under `.kiro/specs/_archive/`. Implementation must follow this document for the hard cutover.

## 1. Architecture Overview

The design introduces a shared LLM registry core that is used by Graph Agent Engine and Studio Backend. Studio Frontend consumes backend DTOs and does not own canonicalization or route resolution logic.

```text
<studio_config_dir>/llm/llm_credentials.json
  provider_endpoints
  provider_routes
  runtime_policy

<studio_config_dir>/llm/llm_import_drafts.json or backend job store
  provider_import_drafts

<studio_config_dir>/llm/llm_roles.yaml
  model_profiles[*].fallback_chain[*].route_id
  roles[*].fallback_chain[*].route_id
  roles[*].lint_requirements

graph_agent_gateway package defaults
  built-in canonical rules
  protocol runtime-setting defaults

graph_agent_gateway.registry
  schema
  storage
  canonical mapper
  deterministic resolver
  linter
  error classifier

engine runtime
  ModelResolverProtocol -> graph_agent_gateway.ModelResolver
  -> GatewayChatModel -> gateway-owned LLMClientManager

studio backend
  API routes -> graph_agent_gateway.registry -> atomic storage writes

studio frontend
  API DTOs -> route grouped UI -> role fallback chain editor
```

The central invariant is that role execution always starts from a declared `route_id` and ends at one exact `provider_model_id`.

Active user state lives in the Studio user config directory resolved by `apps/studio/backend/app/core/paths.app_settings_dir` (`STUDIO_CONFIG_DIR` override, then platform default). Repository-root `config/` files are not an active runtime configuration location in V2; they may be retained only as checked-in examples, seeds, or package-default fixtures. Studio Backend resolves active credentials from `STUDIO_LLM_CREDENTIALS_PATH` or defaults to `<studio_config_dir>/llm/llm_credentials.json`; active roles resolve from `STUDIO_LLM_ROLES_PATH` or `<studio_config_dir>/llm/llm_roles.yaml`.

## 2. Shared Module Boundary

Create a cohesive registry module inside the standalone gateway package:

```text
packages/graph-agent-gateway/src/graph_agent_gateway/registry/
  __init__.py
  schema.py
  storage.py
  canonical.py
  resolver.py
  lint.py
  error_classification.py
  probe_contracts.py
```

Responsibilities:

- `schema.py`: shared dataclasses/Pydantic models for endpoint, route, capability, runtime policy, resolved role, role chain, lint result, and import draft.
- `storage.py`: load and validate `llm_credentials.json` and `llm_roles.yaml`; join them into a registry snapshot.
- `canonical.py`: route-safe canonical mapping with explicit transport normalization and curated aliases.
- `resolver.py`: resolve role names and route IDs into ordered physical route chains.
- `lint.py`: evaluate role lint requirements against route capabilities.
- `error_classification.py`: classify provider/runtime exceptions into fallback-allowed or fail-fast decisions.
- `probe_contracts.py`: shared probe request/result structures used by backend probes and engine diagnostics.

Non-responsibilities:

- It must not expose FastAPI route handlers.
- It must not import Studio backend modules.
- It must not render UI.
- It must not instantiate LangChain or SDK clients.
- It must not import Graph Agent execution internals.

`graph_agent_gateway.resolver.ModelResolver` remains the runtime adapter that calls `graph_agent_gateway.registry.resolver` and builds `GatewayChatModel`. Graph Agent Engine continues to depend only on `ModelResolverProtocol`; it does not own registry storage or provider SDK construction.

### 2.1 Gateway Shared Primitive Cutover

The standalone gateway package must not import Graph Agent execution internals. Current shared objects that cross the package boundary must be moved or narrowed:

- Move gateway fallback event payloads into `graph_agent_gateway.events`; Graph Agent tracing adapters may import gateway event DTOs and translate them into engine trace events.
- Move gateway base exceptions into `graph_agent_gateway.exceptions`; they must not inherit from `graph_agent.core.exceptions.ExecutionError`.
- Keep Predict-mode support outside the runtime import path. `PredictGatewayChatModel` must live in `graph_agent_gateway.predict_interception` or be injected as a test/runtime strategy without importing `graph_agent.core._predict_internal`.
- Move `LLMClientManager` into `graph_agent_gateway.client_manager` and remove `packages/graph-agent/src/graph_agent/models/llm_client_manager.py` from production imports.
- Remove `graph_agent_gateway.factory` from the public runtime API. If a lightweight factory is still useful for tests, keep it under a test-only helper path and do not re-export it from `graph_agent_gateway.__init__`.

## 2.2 Hard Cutover Rules

This prototype uses a clean schema cutover.

- Runtime code must not read the old `models/providers/roles` short-code schema.
- Runtime code must not provide compatibility DTOs for old Studio API clients.
- Engine must not keep a production import path for the old Engine-owned client manager.
- Old config files must fail validation with an actionable schema-version error.

## 3. Storage Schemas

### 3.1 Credentials File

`<studio_config_dir>/llm/llm_credentials.json` becomes schema version 4.

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
  "runtime_policy": {
    "provider_down_ttl_seconds": 60,
    "probe_timeout_seconds": 5,
    "token_escalation_rounds": 2
  }
}
```

Secrets:

- `api_key` is stored only in the local credentials file.
- Registry read APIs must redact `api_key` unless an explicit internal-only runtime path needs the value.
- Endpoint mutation APIs may omit `api_key` to keep the current secret.
- Endpoint mutation APIs treat `api_key: ""` as an explicit clear only when the Settings UI is saving an intentionally empty API key value. Frontend must not send a redacted placeholder such as `"**********"` as a real secret.

Runtime policy:

- `runtime_policy` is a top-level optional block of `<studio_config_dir>/llm/llm_credentials.json` because it controls gateway-owned endpoint health and probe behavior.
- The in-memory `RegistrySnapshot` mirrors this block. If absent, `graph_agent_gateway.registry.schema.RuntimePolicy` supplies documented defaults.
- Legacy role fields such as `circuit_breaker`, `peer_model_groups`, and `single_model_roles` must not be parsed as policy during V2 runtime construction.

| Field | Default | Range | Runtime use |
|---|---:|---:|---|
| `provider_down_ttl_seconds` | `60` | `0..3600` | How long the gateway health cache treats a route/endpoint as temporarily down after a fallback-classified failure. |
| `probe_timeout_seconds` | `5` | `1..120` | Timeout for endpoint tests and route capability probes. |
| `token_escalation_rounds` | `2` | `0..10` | Number of bounded retries the gateway client manager may use for max-output-token probing. |

`RegistrySnapshot` contains `runtime_policy: RuntimePolicy`. `ModelResolver` returns a `ResolvedRole` that carries this policy to `GatewayChatModel` and the gateway-owned `LLMClientManager`.

`runtime_policy` only controls TTL, timeout, and bounded retry-round integer policies. Retryable provider status code sets and truncated finish-reason sets remain client-manager/error-classifier constants unless a later spec explicitly promotes them into policy.

### 3.2 Import Draft Store

Import drafts are untrusted transient data and are stored outside active credentials. The backend may use `<studio_config_dir>/llm/llm_import_drafts.json` or a backend job store with the same DTO shape.

```json
{
  "schema_version": 1,
  "provider_import_drafts": {
    "draft_20260524_openrouter": {
      "draft_id": "draft_20260524_openrouter",
      "source": {
        "kind": "url",
        "url": "https://openrouter.ai/docs/models"
      },
      "status": "needs_probe",
      "created_at": "2026-05-24T00:00:00Z",
      "updated_at": "2026-05-24T00:00:00Z",
      "expires_at": "2026-05-31T00:00:00Z",
      "endpoint_candidates": {
        "openrouter-prod": {
          "endpoint_id": "openrouter-prod",
          "display_name": "OpenRouter",
          "protocol": "openai_compatible",
          "base_url": "https://openrouter.ai/api/v1",
          "metadata": {
            "provider_brand": "openrouter"
          },
          "field_sources": {
            "base_url": {
              "source": "agent_draft",
              "message": "Found in provider docs",
              "observed_at": "2026-05-24T00:00:00Z"
            },
            "protocol": {
              "source": "agent_draft",
              "message": "Inferred from OpenAI-compatible examples"
            }
          }
        }
      },
      "route_candidates": {
        "openrouter-prod:anthropic.claude-opus-4.7": {
          "endpoint_id": "openrouter-prod",
          "provider_model_id": "anthropic/claude-opus-4.7",
          "route_slug": "anthropic.claude-opus-4.7",
          "canonical_id": "claude-opus-4.7",
          "display_name": "Claude Opus 4.7 via OpenRouter",
          "capabilities": {
            "max_input_tokens": {
              "value": 200000,
              "source": "agent_draft"
            }
          }
        }
      },
      "probe_results": {
        "openrouter-prod": {
          "target_type": "endpoint",
          "status": "not_run"
        },
        "openrouter-prod:anthropic.claude-opus-4.7": {
          "target_type": "route",
          "status": "not_run"
        }
      },
      "agent_notes": [
        {
          "message": "Model list extracted from docs table",
          "source_url": "https://openrouter.ai/docs/models"
        }
      ],
      "diff": {
        "endpoint_conflicts": [],
        "new_routes": [
          "openrouter-prod:anthropic.claude-opus-4.7"
        ],
        "updated_routes": []
      }
    }
  }
}
```

Draft promotion identity:

- `status` enum: `pending`, `needs_probe`, `probing`, `probed`, `applying`, `applied`, `expired`, `conflicted`, `failed`.
- `endpoint_candidates` is keyed by proposed `endpoint_id`. A single draft may contain multiple endpoint candidates when one documentation source exposes multiple protocols or base URLs.
- `route_candidates` is keyed by proposed `route_id`. Each route candidate must include the `endpoint_id` it belongs to.
- `probe_results` is keyed by `endpoint_id` for endpoint tests and by `route_id` for route probes. Values include `target_type`, `status`, optional normalized capabilities, optional redacted error, and `observed_at`.
- `field_sources` may annotate any candidate field using dot paths such as `base_url`, `protocol`, `metadata.provider_brand`, or `capabilities.max_output_tokens`. Each source record contains `source`, optional `message`, and optional `observed_at`.
- A draft may auto-promote an endpoint only when no active endpoint has the same `endpoint_id`.
- If `endpoint_id` differs but `protocol + normalized base_url` matches an active endpoint, backend must return a conflict diff and require user confirmation.
- If `endpoint_id` matches an active endpoint, the draft cannot auto-promote endpoint fields. UI must show the diff and require an explicit user choice: discard draft fields, merge selected fields into the active endpoint, or delete the active endpoint first.
- Draft routes are promoted by generated `route_id`; collisions use the stable route-slug hash rule.
- Drafts expire and must be re-probed before apply if `expires_at` has passed.

### 3.3 Roles File

`<studio_config_dir>/llm/llm_roles.yaml` is the active roles file and uses explicit route chains. `STUDIO_LLM_ROLES_PATH` may override this path for tests or isolated runs. Checked-in role files under `docs/development/examples/` are seeds only and must not be hard-coded as active runtime state.

```yaml
schema_version: 2

model_profiles:
  CLO47T:
    display_name: Claude Opus 4.7 Thinking
    canonical_id: claude-opus-4.7
    tags:
      - thinking
      - premium
    lint_requirements:
      thinking: "error"
      tool_calling: "warn"
    fallback_chain:
      - route_id: anthropic-official:claude-opus-4.7
        runtime_settings:
          temperature: null
          max_output_tokens: 8192
          reasoning:
            enabled: true
            budget_tokens: 4096
      - route_id: openrouter-prod:anthropic.claude-opus-4.7
        runtime_settings:
          temperature: null
          max_output_tokens: 8192
          reasoning:
            enabled: true

roles:
  graph_agent:
    system_prompt_prefix: ""
    source_profile_id: CLO47T
    source_profile_snapshot:
      display_name: Claude Opus 4.7 Thinking
      applied_at: "2026-05-24T00:00:00Z"
      deleted_at: null
      deleted_marker: false
    fallback_chain:
      - route_id: anthropic-official:claude-opus-4.7
        runtime_settings:
          temperature: null
          max_output_tokens: 8192
          reasoning:
            enabled: true
            budget_tokens: 4096
      - route_id: openrouter-prod:anthropic.claude-opus-4.7
        runtime_settings:
          temperature: null
          max_output_tokens: 8192
          reasoning:
            enabled: true
    lint_requirements:
      thinking: "error"
      tool_calling: "warn"

  copilot_chat:
    system_prompt_prefix: ""
    fallback_chain:
      - route_id: openrouter-prod:anthropic.claude-sonnet-4.6
        runtime_settings:
          temperature: 0.7
          max_output_tokens: 4096
    lint_requirements:
      thinking: "warn"
      tool_calling: "off"
```

The old `models`, `providers`, `active_model`, `model_fallback`, `peer_model_groups`, and provider short-code maps are removed from the runtime schema. The core resolver accepts only the route-chain schema.

Role `system_prompt_prefix` is a string field with default `""`. Missing values normalize to `""`; `null` is rejected at schema validation so runtime prompt rendering never receives Python `None`.

`lint_requirements` values are string enum values: `"off"`, `"warn"`, and `"error"`. Examples quote these values so YAML 1.1 parsers cannot coerce `off` into boolean `false`.

### 3.4 Model Profiles

`model_profiles` are reusable authoring templates for Studio and backend APIs. They replace the useful part of the old short-code model combinations without reintroducing runtime indirection.

Profile fields:

- `model_profile_id`: YAML key, for example `CLO47T`
- `display_name`
- `canonical_id`
- `tags`
- `fallback_chain`
- `lint_requirements`
- optional profile-level runtime defaults that may be copied into route `runtime_settings` when applying the profile

Rules:

- Profile `fallback_chain` entries are the same route-chain item type used by roles.
- Profile and role route entries store user-authored runtime parameters under `runtime_settings`; they do not store provider-specific request payloads.
- Profile route IDs are validated and linted at save time.
- Applying a profile to a role expands it into the role's `fallback_chain`.
- The role may store `source_profile_id` and `source_profile_snapshot` for UI traceability.
- Runtime resolver ignores `source_profile_id`; it executes only the role's saved `fallback_chain`.
- Updating a profile does not mutate existing roles. Users must explicitly reapply a profile to refresh a role.
- Deleting a profile must not mutate existing role `fallback_chain` values. Backend may clear dangling `source_profile_id` links and preserve `source_profile_snapshot` with a deleted-profile marker for UI traceability.
- Profile IDs are authoring identifiers and must never be sent to provider APIs.

`source_profile_snapshot` fields:

- `display_name`
- `applied_at`
- optional `deleted_at`
- optional `deleted_marker: bool`

When deleting a profile, backend clears dangling `source_profile_id`, sets `source_profile_snapshot.deleted_at`, and sets `source_profile_snapshot.deleted_marker: true`. The saved role fallback chain remains unchanged.

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
3. If a generated slug collides under the same endpoint, append a deterministic suffix derived from a short stable hash of `endpoint_id + provider_model_id`.
4. Never infer `provider_model_id` by reversing the slug.

Endpoint naming convention for seed/import/cutover:

- Prefer lowercase `<brand>-<protocol-or-channel>` names.
- Official first-party APIs use `official` when the brand itself is the route owner.
- Proxies and aggregators use their brand plus the protocol surface they expose.
- Existing uppercase provider short codes such as `OC_CL`, `WS_LLM`, or `GM_OFF` are not migrated into runtime identifiers.

Examples:

| Existing/provider meaning | V2 endpoint_id |
|---|---|
| Anthropic official API | `anthropic-official` |
| OpenAI official API | `openai-official` |
| OneChats OpenAI-compatible endpoint | `onechats-openai` |
| OneChats Anthropic-compatible endpoint | `onechats-anthropic` |
| WaveSpeed Any-LLM endpoint | `wavespeed-anyllm` |
| Qiniu OpenAI-compatible endpoint | `qiniu-openai` |
| Qiniu Anthropic-compatible endpoint | `qiniu-anthropic` |

## 5. Canonicalization Design

Canonicalization is implemented in `graph_agent_gateway.registry.canonical`.

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
- User/project curated rule overrides may live in `<studio_config_dir>/llm/llm_canonical_rules.yaml` or an explicit `STUDIO_LLM_CANONICAL_RULES_PATH` override.
- Checked-in canonical rule files under repo `config/` are seed fixtures only; runtime code must not hard-code repo-root `config/llm_canonical_rules.yaml` as active state.
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

Raw provider capability trees from model-list APIs are not stored directly as executable metadata. Backend normalizers map selected known fields into `CapabilityValue` entries with `source: "api_list"` or `source: "provider_doc"`. Unknown provider-specific capability trees may be retained only under route `metadata.raw_capabilities` for diagnosis; linter and runtime checks must use normalized capability keys only.

Common capability keys:

- `max_input_tokens`
- `max_output_tokens`
- `temperature`
- `top_p`
- `stop_sequences`
- `seed`
- `thinking_protocol`
- `reasoning_budget_tokens`
- `reasoning_effort`
- `tool_protocol`
- `tool_choice`
- `parallel_tool_calls`
- `structured_output_protocol`
- `vision`

The capability object is not a route-selection policy. It is metadata for display, linting, verification, and fail-fast validation.

### 6.2 Lint Requirements

Role lint requirement values:

```yaml
lint_requirements:
  thinking: "error"
  tool_calling: "warn"
  structured_output: "off"
```

Lint key mapping:

| lint key | normalized capability key |
|---|---|
| `thinking` | `thinking_protocol` |
| `tool_calling` | `tool_protocol` |
| `structured_output` | `structured_output_protocol` |
| `vision` | `vision` |
| `max_input_tokens` | `max_input_tokens` |
| `max_output_tokens` | `max_output_tokens` |

Linter evaluation must use this mapping. Unknown lint keys fail schema validation rather than being compared against raw provider metadata.

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
- `error` requirements block save when the route is known incompatible.
- Missing or unverified capability data for an `error` requirement produces a blocking `requires_probe` lint until the route is probed, manually verified, or the user lowers the requirement severity.
- Missing capability data for a `warn` requirement produces a visible warning but does not block save.

Runtime behavior:

- If a role reaches runtime with an `error` requirement that the route cannot satisfy or has not verified, Gateway fails before making the LLM request.
- Runtime must not replace that route with another route based on the capability.

### 6.3 Runtime Settings Schema

Runtime settings are user-authored request parameters. Capabilities describe whether a route supports those settings, what limits/defaults are known, and where that knowledge came from. These two concepts must stay separate.

Use a fixed normalized schema for runtime settings:

```yaml
runtime_settings:
  temperature: null
  top_p: null
  max_output_tokens: 8192
  stop_sequences: []
  seed: null
  tool_choice: auto
  parallel_tool_calls: null
  structured_output:
    mode: none
    json_schema: null
    strict: null
  reasoning:
    enabled: true
    effort: null
    budget_tokens: 4096
```

Schema fields:

| Field | Type | Meaning |
|---|---|---|
| `temperature` | `float | null` | Sampling temperature when the protocol supports it. |
| `top_p` | `float | null` | Nucleus sampling value when supported. |
| `max_output_tokens` | `int | null` | Maximum generated output tokens. Adapter maps to `max_tokens`, `max_output_tokens`, or provider equivalent. |
| `stop_sequences` | `list[str] | null` | Stop sequences. Empty list means explicit none; null means inherit defaults. |
| `seed` | `int | null` | Deterministic seed for providers that support it. |
| `tool_choice` | enum/object/null | `auto`, `none`, `required`, or a specific tool reference when the adapter supports it. |
| `parallel_tool_calls` | `bool | null` | Parallel tool calling preference when supported. |
| `structured_output` | object/null | JSON/schema output request. |
| `reasoning.enabled` | `bool | null` | Whether the user requested reasoning/thinking mode. |
| `reasoning.effort` | enum/null | Provider-neutral effort label such as `low`, `medium`, or `high` for effort-based APIs. |
| `reasoning.budget_tokens` | `int | null` | Budget-token style thinking/reasoning limit for Anthropic/Gemini-like APIs. |

Default resolution order:

1. Explicit route-entry `runtime_settings`.
2. Model profile default copied into the role route entry when the profile is applied.
3. Route capability default, for example a probed or documented minimum/maximum/default.
4. Protocol adapter default.
5. Studio safe default.

The resolver produces `effective_runtime_settings` with per-field source metadata:

```json
{
  "max_output_tokens": {
    "value": 8192,
    "source": "route_setting"
  },
  "reasoning.budget_tokens": {
    "value": 4096,
    "source": "profile_default"
  },
  "parallel_tool_calls": {
    "value": false,
    "source": "protocol_default"
  }
}
```

Validation rules:

- Unknown runtime setting keys fail schema validation.
- Unsupported settings fail save/probe validation when the route capability is known, or fail fast before the provider request if an invalid config reaches runtime.
- Out-of-range values fail validation using the narrowest known bound from route capability, provider documentation, live probe, or adapter default.
- Missing values are resolved to effective defaults or omitted from the provider request deliberately; adapters must not pass ambiguous nulls to provider SDKs.
- Frontend may dynamically show or disable controls from capability metadata, but backend and gateway remain the source of truth for validation.

Capability keys that describe runtime-setting support:

| Capability key | Example value | Purpose |
|---|---|---|
| `temperature` | `{ "supported": true, "min": 0, "max": 2, "default": 1 }` | Validates `runtime_settings.temperature`. |
| `top_p` | `{ "supported": true, "min": 0, "max": 1 }` | Validates `runtime_settings.top_p`. |
| `max_output_tokens` | `{ "max": 8192, "default": 4096 }` | Validates and defaults output length. |
| `stop_sequences` | `{ "supported": true, "max_items": 4 }` | Validates stop sequence support. |
| `seed` | `{ "supported": false }` | Enables/disables seed input. |
| `tool_choice` | `{ "values": ["auto", "none", "required"] }` | Validates tool choice mode. |
| `parallel_tool_calls` | `{ "supported": true }` | Validates parallel tool call setting. |
| `structured_output_protocol` | `"openai_json_schema"` | Selects structured output adapter mapping. |
| `thinking_protocol` | `"anthropic_v1"` | Selects reasoning/thinking adapter mapping. |
| `reasoning_budget_tokens` | `{ "min": 1024, "max": 32000, "default": 4096 }` | Validates `reasoning.budget_tokens`. |
| `reasoning_effort` | `{ "values": ["low", "medium", "high"], "default": "medium" }` | Validates `reasoning.effort`. |

## 7. Deterministic Resolver

`graph_agent_gateway.registry.resolver` loads a registry snapshot from credentials plus roles.

Resolver construction:

- `ModelResolver` must be created from an explicit `RegistrySnapshot` or explicit credentials/roles paths.
- No built-in model defaults are allowed in the V2 runtime path.
- No environment API key fallback is allowed in the V2 runtime path.
- Missing registry files, stale schema versions, or old short-code schemas fail during resolver construction with structured configuration errors.

Resolution flow:

1. Read role by name.
2. Read role `fallback_chain` in declared order.
3. Validate each `route_id` exists.
4. Join route to endpoint by `endpoint_id`.
5. Validate endpoint has protocol, base URL, and credential.
6. Run linter.
7. Return a `ResolvedRole` containing role metadata, runtime policy, and ordered `ResolvedRoute` records.

`ResolvedRole` contains:

- `role_name`
- `system_prompt_prefix: str`, normalized to `""` when omitted in stored config
- `runtime_policy: RuntimePolicy`
- `routes: list[ResolvedRoute]`
- `lint_results`
- optional `source_profile_id` and `source_profile_snapshot` for diagnostics only

`ResolvedRoute` contains:

- `role_name`
- `route_id`
- `endpoint_id`
- `protocol`
- `base_url`
- `api_key: SecretStr`, a short-lived runtime field that is never serialized to API responses, trace payloads, logs, or exceptions
- `credential_fingerprint`
- `timeout_seconds`
- `trust_env`
- `proxy_env`
- `provider_model_id`
- `canonical_id`
- `display_name`
- `capabilities`
- `runtime_settings`, the user-authored normalized settings from the role/profile route entry
- `effective_runtime_settings`, the resolver-produced settings with per-field source metadata

`system_prompt_prefix` is deliberately role-level metadata, not route-level metadata. It is carried by `ResolvedRole` and applied by `GatewayChatModel`; Engine code must not read role files directly to recover it.

Credential fingerprint:

- Computed by `graph_agent_gateway.registry.storage` from `endpoint_id`, `protocol`, normalized `base_url`, secret value, `timeout_seconds`, `trust_env`, and `proxy_env`.
- Used only as a cache invalidation key; it is not displayed as a credential proof and must not allow recovering the secret.
- Gateway is the source of truth for fingerprint computation. `apps/studio/backend/app/services/llm_credentials.provider_test_params_fingerprint` must be replaced by `graph_agent_gateway.registry.storage.compute_credential_fingerprint(endpoint, secret)` so backend provider-test caching and runtime client caching cannot drift.
- Callers may unwrap `ResolvedRoute.api_key.get_secret_value()` only inside gateway client/probe construction scope. Trace events, API DTOs, logs, exceptions, and diagnostics use redacted values only.
- `RuntimePolicy` changes invalidate runtime client cache because relevant policy values are part of the client cache key. They do not invalidate `credential_fingerprint`-keyed provider-test results because policy is not part of the credential fingerprint inputs.

Model profile handling:

- `graph_agent_gateway.registry.resolver` validates profile chains, but does not use profile IDs during role execution.
- Backend profile-apply logic expands a profile into a role fallback-chain snapshot before saving.
- Runtime diagnostics may include `source_profile_id` when present, but fallback behavior is determined only by `route_id` order.

`system_prompt_prefix` is deliberately role-level metadata, not route-level metadata. It is carried by `ResolvedRole` and applied by `GatewayChatModel`; Engine code must not read role files directly to recover it.

Credential fingerprint:

- Computed by `graph_agent_gateway.registry.storage` from `endpoint_id`, `protocol`, normalized `base_url`, secret value, `timeout_seconds`, `trust_env`, and `proxy_env`.
- Used only as a cache invalidation key; it is not displayed as a credential proof and must not allow recovering the secret.
- Gateway is the source of truth for fingerprint computation. `apps/studio/backend/app/services/llm_credentials.provider_test_params_fingerprint` must be replaced by `graph_agent_gateway.registry.storage.compute_credential_fingerprint(endpoint, secret)` so backend provider-test caching and runtime client caching cannot drift.
- Callers may unwrap `ResolvedRoute.api_key.get_secret_value()` only inside gateway client/probe construction scope. Trace events, API DTOs, logs, exceptions, and diagnostics use redacted values only.
- `RuntimePolicy` changes invalidate runtime client cache because relevant policy values are part of the client cache key. They do not invalidate `credential_fingerprint`-keyed provider-test results because policy is not part of the credential fingerprint inputs.

Model profile handling:

- `graph_agent_gateway.registry.resolver` validates profile chains, but does not use profile IDs during role execution.
- Backend profile-apply logic expands a profile into a role fallback-chain snapshot before saving.
- Runtime diagnostics may include `source_profile_id` when present, but fallback behavior is determined only by `route_id` order.

Engine integration:

- `graph_agent_gateway.resolver.ModelResolver` calls shared registry resolution.
- `GatewayChatModel` receives a `ResolvedRole` backed by route records.
- Graph Agent assembly must resolve chat models per executable phase using that phase's
  declared `llm_role`; it must not pre-resolve one workflow-level model with
  `role_name=None` and reuse it across phases.
- The provider client manager is owned by `graph_agent_gateway` and uses endpoint credentials from `ResolvedRoute`, not environment variables.
- Client cache key includes endpoint ID, credential fingerprint, timeout, trust/proxy settings, and relevant `RuntimePolicy` health values.
- `_PROBE_DOWN_TTL`, `_PROBE_TIMEOUT`, and `_TOKEN_ESCALATION_ROUNDS` class constants from the old Engine client manager are replaced by values read from `ResolvedRole.runtime_policy`.

Provider protocol adapters:

- Gateway owns all provider request construction. Engine never branches on provider SDK details.
- Supported protocol identifiers are `openai_compatible`, `anthropic_compatible`, `google_genai`, and `ark_runtime`.
- `ark_runtime` uses Volcengine's official Ark runtime SDK surface, not the OpenAI-compatible client wrapper. It may share endpoint base URLs with an OpenAI-compatible Ark endpoint, but it is a distinct protocol because request/response capabilities may differ.
- Each adapter maps `effective_runtime_settings` into the concrete SDK/API request shape and omits unsupported fields before the request is sent.
- Adapter mapping is deterministic and route-local. If two routes share a `canonical_id` but have different protocols, their supported runtime settings and capabilities remain separate.
- Adapter errors are normalized through `registry.error_classification` before fallback decisions are made.

Runtime fallback:

- The chain order is fixed.
- Fallback is allowed for network/timeouts/retryable 5xx/rate-limit/marked-down cases.
- Invalid model, unsupported capability, bad request, missing credential, or schema validation failures fail fast.

Error classifier:

- Implement in `graph_agent_gateway.registry.error_classification`.
- `httpx.ConnectError`, `httpx.TimeoutException`, retryable 5xx provider responses, classified rate limits, and route health-cache down states are `fallback_allowed`.
- Authentication failures, missing credentials, unknown model IDs, unsupported capability/request-shape errors, schema validation errors, and provider 4xx bad request errors are `fail_fast`.
- Classifier output includes `decision`, `error_class`, `provider_status_code`, `route_id`, and a redacted message.
- Unclassified exceptions default to `fail_fast_with_route_context` unless explicitly marked retryable by an adapter.
- Diagnostics and metrics must tag `unclassified_default: true` when this fallback classification path is used.

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
  "model_profiles": {},
  "roles": {},
  "lint_results": []
}
```

### 8.2 Endpoint and Route Mutation APIs

`PUT /api/llm/registry/endpoints`

- Upserts editable endpoint fields for submitted endpoint IDs.
- Endpoints absent from the request body are retained.
- Endpoint deletion must use `DELETE /api/llm/registry/endpoints/{endpoint_id}`.
- Keeps the current secret when `api_key` is omitted.
- Clears the current secret when `api_key` is explicitly set to an empty string.
- Invalidates client fingerprint/version when secret, protocol, or base URL changes.

Request:

```json
{
  "provider_endpoints": {
    "anthropic-official": {
      "endpoint_id": "anthropic-official",
      "display_name": "Anthropic Official",
      "protocol": "anthropic_compatible",
      "base_url": "https://api.anthropic.com",
      "api_key": "",
      "status": "unverified_manual",
      "timeout_seconds": 120,
      "trust_env": false
    }
  }
}
```

Response:

```json
{
  "schema_version": 4,
  "provider_endpoints": {
    "anthropic-official": {
      "endpoint_id": "anthropic-official",
      "display_name": "Anthropic Official",
      "protocol": "anthropic_compatible",
      "base_url": "https://api.anthropic.com",
      "api_key": "**********",
      "status": "unverified_manual",
      "timeout_seconds": 120,
      "trust_env": false,
      "proxy_env": null,
      "metadata": {}
    }
  },
  "provider_routes": {},
  "runtime_policy": {
    "provider_down_ttl_seconds": 60,
    "probe_timeout_seconds": 5,
    "token_escalation_rounds": 2
  }
}
```

`DELETE /api/llm/registry/endpoints/{endpoint_id}`

- Deletes one endpoint only when no active route, role, or model profile still references it.
- If referenced, returns `409 endpoint_in_use` with references grouped by `routes`, `roles`, and `model_profiles`.
- Does not delete import drafts; drafts remain transient history until expiration or explicit draft cleanup.

Conflict response:

```json
{
  "detail": {
    "code": "endpoint_in_use",
    "endpoint_id": "anthropic-official",
    "routes": ["anthropic-official:claude-sonnet-4.6"],
    "roles": ["graph_agent.fallback_chain[0]"],
    "model_profiles": ["CL46T.fallback_chain[0]"]
  }
}
```

`POST /api/llm/endpoints/{endpoint_id}/test`

- Tests authentication and model listing for one endpoint.
- Updates endpoint status and may create route candidates from model list results.

`POST /api/llm/routes/{route_id}/probe`

- Probes one physical route.
- Request names desired capabilities.
- Updates only that route's capability fields and status.

Request:

```json
{
  "capabilities": ["thinking", "tool_calling", "max_output_tokens"]
}
```

Response:

```json
{
  "route_id": "anthropic-official:claude-sonnet-4.6",
  "status": "verified",
  "capabilities": {
    "tool_protocol": {
      "value": "anthropic_tools",
      "source": "probed_verified",
      "observed_at": "2026-05-24T00:00:00Z"
    }
  }
}
```

`PUT /api/llm/routes/{route_id}`

- Replaces editable metadata for one route.
- Editable fields include `display_name`, `canonical_id`, `status`, `capabilities`, and `metadata`.
- `route_id`, `endpoint_id`, and `provider_model_id` are immutable through this endpoint.
- Changing the route identity requires creating a new route and deleting the old route.
- Backend validates that the route remains internally consistent and still references an existing endpoint.

Request:

```json
{
  "display_name": "Claude Sonnet 4.6",
  "canonical_id": "claude-sonnet-4.6",
  "status": "verified",
  "capabilities": {
    "thinking_protocol": {
      "value": "anthropic_v1",
      "source": "manual"
    }
  },
  "metadata": {
    "provider_brand": "anthropic"
  }
}
```

Response:

```json
{
  "route_id": "anthropic-official:claude-sonnet-4.6",
  "endpoint_id": "anthropic-official",
  "route_slug": "claude-sonnet-4.6",
  "provider_model_id": "claude-sonnet-4-6",
  "canonical_id": "claude-sonnet-4.6",
  "display_name": "Claude Sonnet 4.6",
  "status": "verified",
  "capabilities": {},
  "metadata": {
    "provider_brand": "anthropic"
  }
}
```

`DELETE /api/llm/routes/{route_id}`

- Deletes one route only when no role or model profile references it.
- If referenced, returns `409 route_in_use` with role/profile reference paths.
- Deleting a route never rewrites fallback chains implicitly.

Conflict response:

```json
{
  "detail": {
    "code": "route_in_use",
    "route_id": "anthropic-official:claude-sonnet-4.6",
    "roles": ["graph_agent.fallback_chain[0]"],
    "model_profiles": ["CL46T.fallback_chain[0]"]
  }
}
```

Router implementation must document request/response JSON examples for endpoint upsert, route update, route probe, delete conflicts, and profile-apply conflicts in this section before frontend integration.

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

Role read/write APIs use only the new route-chain schema. Reusing the current URL paths is allowed only as a hard contract replacement, not as backward-compatible behavior.

`GET /api/llm/roles`

`GET /api/llm/roles/{role_name}`

`PUT /api/llm/roles`

- Upserts submitted roles in the roles map.
- Roles absent from the request body are retained.
- Role deletion is out of scope for V2 unless a dedicated delete endpoint is added.

`PUT /api/llm/roles/{role_name}`

- Replaces exactly one role using a full role body.
- Partial role patch semantics are out of scope for V2.
- Frontend autosave should use `PUT /api/llm/roles/{role_name}` for per-role edits and serialize saves per role. Server-side ETag/If-Match concurrency is not required in V2.

- Backend validates `route_id` references before saving.
- Backend returns lint results with role payloads.
- Backend blocks saves with `error` lints unless the request explicitly changes the requirement severity.

### 8.5 Model Profile APIs

`GET /api/llm/model-profiles`

- Returns editable profiles plus lint results for each profile fallback chain.
- Returns only backend-derived route DTOs; no raw model-string synthesis is allowed.

`PUT /api/llm/model-profiles`

- Replaces the model profile set using the new schema.
- Validates every referenced `route_id`.
- Runs the same capability linter used by roles.
- Blocks save on `error` lints for known incompatible routes.

`DELETE /api/llm/model-profiles/{model_profile_id}`

- Deletes one model profile.
- Does not mutate any role `fallback_chain`.
- Clears dangling role `source_profile_id` links and preserves `source_profile_snapshot` with a deleted-profile marker for UI traceability.

`POST /api/llm/roles/{role_name}/apply-profile`

- Body contains `model_profile_id`.
- Expands the profile fallback chain into the role's explicit `fallback_chain`.
- Writes `source_profile_id` and a lightweight `source_profile_snapshot`.
- Does not create a runtime dependency from the role back to the profile.
- If the role has diverged from its stored `source_profile_snapshot`, backend returns `409 profile_apply_conflict` with a diff.
- Conflict resolution is explicit: the caller may retry with `mode: "replace"` to replace the role fallback chain with the current profile, or cancel. No merge mode is provided in V2.

Conflict response:

```json
{
  "detail": {
    "code": "profile_apply_conflict",
    "role_name": "graph_agent",
    "model_profile_id": "CL46T",
    "current_route_ids": ["openrouter-prod:anthropic.claude-sonnet-4.6"],
    "profile_route_ids": ["anthropic-official:claude-sonnet-4.6"]
  }
}
```

### 8.6 Deprecated LLM API Paths

Hard cutover removes old provider-oriented LLM endpoints from the production contract:

- `POST /api/llm/providers/test` is replaced by `POST /api/llm/endpoints/{endpoint_id}/test`.
- `POST /api/llm/providers/test-models` is replaced by `POST /api/llm/routes/{route_id}/probe`.
- `GET /api/llm/providers/notable-models` remains only as a suggestion endpoint for manual model-id placeholders. It may parse provider-note §4 entries, but it must not construct endpoints, routes, roles, credentials, canonical aliases, or runtime defaults.
- Existing `GET/PUT /api/llm/roles` paths may be reused only with the new schema.

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
5. Backend probes selected endpoint candidates and route candidates.
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

## 9.5 Provider Protocol Capability Verification

Capability verification is a route/protocol matrix, not a canonical-model-only table. The same marketed model may accept different parameters through first-party SDKs, OpenAI-compatible compatibility layers, and aggregators.

Minimum verification matrix:

| Dimension | Required checks |
|---|---|
| Same official provider family | Probe at least two common models from the same official provider family when credentials are available, for example Anthropic Sonnet/Haiku or OpenAI reasoning/non-reasoning variants, to detect shared defaults and per-model exceptions. |
| Same model through different providers | Compare route capabilities for the same `canonical_id` across at least two `route_id` values when available. Differences stay route-local. |
| SDK vs compatibility layer | For providers with official SDKs plus OpenAI-compatible endpoints, run both paths when credentials and dependencies exist. |
| Positive runtime-setting probe | Send a minimal valid request for selected settings such as tools, structured output, max output tokens, and reasoning/thinking. |
| Negative boundary probe | Send intentionally invalid or too-low settings where safe, classify the provider error, and record the minimum/limit behavior. |

Provider pattern notes:

- Anthropic-style thinking uses a budget-token protocol. Thinking budget lower bounds and max-output interactions must be probed and recorded per route.
- OpenAI-style reasoning may use effort or Responses API fields. Adapters map normalized `reasoning.effort` and output-token fields into the selected API surface.
- Gemini-style generation config may use thinking budget fields that differ from OpenAI and Anthropic names.
- DeepSeek/OpenAI-compatible routes may expose reasoning behavior through OpenAI-shaped requests but provider-specific responses.
- Volcengine Ark must have a first-class `ark_runtime` adapter using the official Ark SDK. The existing OpenAI-compatible Ark endpoint remains a separate route/protocol path for comparison.

Probe results are stored as normalized capabilities with `source: "probed_verified"` plus diagnostic metadata. Raw provider observations may be retained under route metadata for diagnosis, but linter/runtime validation uses normalized capability keys only.

## 10. Studio Frontend Design Constraints

The frontend follows `docs/development/FRONTEND_UI_SPEC.md` section 2.

API Keys UX amendment, added after the API Keys regression review:

- The v4 storage model uses `ProviderEndpoint` and `ProviderRoute`, but the Settings page must not change user-facing UX merely because storage changed.
- The API Keys page remains an API Keys/provider configuration surface. User-visible copy such as "API Keys", "Official Providers", "Third-party Providers", "Provider Name", and "Available Models" is allowed and preferred for the restored page.
- `endpoint` and `route` are internal registry concepts. Use them in DTOs, API paths, tests, and engineering docs; do not force them into user-facing labels unless the product explicitly decides to rename the page.
- The frontend must treat the backend registry as the only persisted truth source. It may keep transient input drafts and loading state, but endpoint status and available models are always projected from the latest registry snapshot.
- API Keys `Available Models` is a view of `provider_routes` filtered by `endpoint_id`; it is not a stored field on the endpoint.

Required UI shape:

- API Keys page manages endpoint-backed provider credentials without changing the restored API Keys/provider UX.
- Provider brand and user-facing provider label are display metadata over endpoint records.
- Roles settings include a Model Profiles area for reusable route bundles such as `CLO47T`.
- Roles page uses an Available Routes sidebar grouped by `canonical_id`.
- Applying a model profile to a role snapshots that profile into the role fallback chain.
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
- Preserve the existing pointer-fallback drag behavior, drag preview, drop shield, and pointerup click suppression needed for Tauri/WebKit. Do not reintroduce native HTML5 drag/drop as the primary path.
- Available Routes grouping, vendor labels, route availability, and canonical IDs come from backend DTOs. Frontend no longer performs model-name canonicalization or provider ownership inference.

Frontend must not:

- build route records from raw strings;
- reimplement canonical mapping;
- hide physical `provider_model_id`;
- add dynamic model selection controls that imply intent routing.

## 11. Existing Code Impact

### 11.1 Gateway Package

Primary files affected:

- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/storage.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/canonical.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/lint.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/error_classification.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/registry/probe_contracts.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/client_manager.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/events.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/llm_config.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/resolver.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/gateway_chat_model.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/tracing.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/exceptions.py`
- `packages/graph-agent-gateway/src/graph_agent_gateway/factory.py`

Changes:

- Replace old model/provider short-code schema with route-chain role schema.
- Add credentials loading from the registry snapshot.
- Move provider client construction into the gateway package and remove the Engine-owned client-manager production path.
- Remove API key lookup as a required environment-variable path.
- Update fallback error classification.
- Include route diagnostics in logs and callback events.
- Remove imports from `graph_agent` execution internals.
- Remove env-reading factory APIs from the public runtime surface.

### 11.2 Graph Agent Engine

Primary files affected:

- `packages/graph-agent/src/graph_agent/core/phase_nodes/base.py`
- `packages/graph-agent/src/graph_agent/core/phase_nodes/llm_phase_node.py`
- `packages/graph-agent/src/graph_agent/core/types.py`
- `packages/graph-agent/src/graph_agent/cognitive/prompt.py`
- `packages/graph-agent/src/graph_agent/config/llm_config.py`
- `packages/graph-agent/src/graph_agent/models/llm_client_manager.py`

Changes:

- Keep Engine dependent on `ModelResolverProtocol`, not concrete registry storage.
- Update `model_override` documentation and validation expectations from model code to explicit `route_id`.
- Remove direct Engine reads of role configuration for `system_prompt_prefix`. Role-specific prompt metadata is owned by Gateway resolution and applied by `GatewayChatModel` or returned through a gateway-owned protocol extension.
- Move `packages/graph-agent/src/graph_agent/models/llm_client_manager.py` into `graph_agent_gateway` and remove the old Engine-owned module from production imports. Do not keep a compatibility import wrapper for the old mode.
- Remove `packages/graph-agent/src/graph_agent/config/llm_config.py` from production imports. Engine must not own an LLM role schema loader.

### 11.3 Studio Backend

Primary files affected:

- `apps/studio/backend/app/models/llm_config.py`
- `apps/studio/backend/app/services/llm_credentials.py`
- `apps/studio/backend/app/services/llm_roles.py`
- `apps/studio/backend/app/services/llm_import_drafts.py`
- `apps/studio/backend/app/services/gateway_resolver.py`
- `apps/studio/backend/app/services/llm_env.py`
- `apps/studio/backend/app/services/migrations.py`
- `apps/studio/backend/app/routers/llm.py`
- `apps/studio/backend/app/services/copilot.py`
- `docs/development/llm_provider_notes/*.md`

Changes:

- Replace `providers: list[ProviderCredential]` with endpoint/route maps and runtime policy in the active credentials file.
- Store import drafts outside active credentials in `llm_import_drafts.json` or a backend job store.
- Move canonical mapping to the shared registry module.
- Replace provider-oriented tests with endpoint test and route probe APIs.
- Add route-level probe endpoints.
- Add import draft lifecycle endpoints.
- Add model profile CRUD and profile-apply endpoints.
- Add endpoint/route/model-profile delete endpoints with `409 *_in_use` reference conflicts.
- Save roles as explicit route chains.
- Replace backend provider-test fingerprint helper with gateway credential fingerprint helper.
- Update Copilot provider resolution to use `route_id`.
- Delete old provider-card probing helpers, env-patching, and old schema migration shims; runtime migration readers are not allowed.
- Archive provider notes under docs only. Runtime construction code must not parse provider note markdown; the only allowed parser is the suggestion-only notable-model endpoint used by manual probing placeholders.

### 11.4 Studio Frontend

Primary files affected:

- `apps/studio/frontend/src/api/llm.ts`
- `apps/studio/frontend/src/hooks/useDebouncedCredentialsSave.ts`
- `apps/studio/frontend/src/hooks/useDebouncedRolesSave.ts`
- `apps/studio/frontend/src/hooks/useRoleTestChainRunner.ts`
- `apps/studio/frontend/src/components/studio/settings/SettingsPage.tsx`
- `apps/studio/frontend/src/components/studio/settings/LlmRolesTab.tsx`
- `apps/studio/frontend/src/components/studio/settings/role-utils.ts`
- `apps/studio/frontend/src/components/studio/settings/provider-utils.ts`
- `apps/studio/frontend/src/components/studio/settings/llm-roles/*`
- `apps/studio/frontend/src/components/studio/settings/api-keys/*`
- `apps/studio/frontend/src/components/studio/settings/endpoints/*`
- `apps/studio/frontend/src/components/studio/api-keys/*`
- `docs/development/FRONTEND_UI_SPEC.md`

Changes:

- Replace model/provider short-code DTOs with endpoint/route/draft DTOs.
- Replace Available Models with Available Routes grouped by canonical ID.
- Remove frontend canonicalization, provider ownership inference, and stale provider pruning from `role-utils.ts`; backend DTOs own those decisions.
- Make drag/drop payload carry `route_id`.
- Show lint and probe states per route.
- Add import draft diff UI.
- Add endpoint/route/model-profile delete UI with reference-conflict display.
- Keep autosave serialized and stale-result safe.

## 12. Verification Plan

Unit tests:

- `graph_agent_gateway.registry.schema` validates route IDs and endpoint IDs.
- `graph_agent_gateway.registry.canonical` covers transport normalization, explicit aliases, and negative cases.
- `graph_agent_gateway.registry.resolver` preserves route order and never dynamically selects by capability.
- `graph_agent_gateway.registry.lint` handles `off`, `warn`, `error`, missing capability, and verified incompatibility.
- `graph_agent_gateway.registry.error_classification` covers retryable network/provider failures and fail-fast credential/model/request failures.
- `graph_agent_gateway.registry.schema.RuntimePolicy` validates defaults and ranges.
- Gateway provider client manager uses credentials from resolved routes and invalidates cache on credential fingerprint change.
- Gateway provider client manager receives runtime policy values from `ResolvedRole`, not hardcoded Engine class constants.
- Gateway import tests prove it does not import `graph_agent` execution internals.

Backend tests:

- Endpoint save/load redacts secrets in responses.
- Endpoint test creates route candidates.
- Route probe updates only route capabilities.
- Import draft create/probe/apply honors verified and unverified rules.
- Import draft schema tests cover status enum, field sources, probe results, and multiple endpoint candidates.
- Import draft expiration and concurrent write tests cover stale draft apply and multi-tab conflicts.
- Role save blocks invalid route IDs and `error` lint failures.
- Model profile save/apply handles conflict, replace, and no-runtime-reference behavior.
- Endpoint, route, and model-profile delete APIs return reference conflicts when in use.
- Deprecated provider-oriented LLM endpoints are removed or return hard-cutover errors.

Frontend tests:

- Available Routes groups by backend `canonical_id`.
- Model Profiles render as reusable backend-defined route bundles.
- Applying a profile writes exact `route_id` fallback-chain entries to the role payload.
- Route drag/drop writes `route_id`.
- Lint warning/error badges render with accessible text.
- Probe button triggers route probe flow.
- Import draft diff separates verified and unverified changes.
- Frontend role utilities no longer canonicalize raw model strings or infer provider ownership.

Manual verification:

- Run Studio frontend or Tauri shell.
- Verify endpoint test, route probe, import draft diff, role route drag/drop, and lint states.
- Check desktop and narrow widths.
- Confirm no horizontal overflow for long provider model IDs and route IDs.
- Remove LLM API keys from `.env` and run a short Graph Agent runtime smoke path using credentials-file-backed routes.
