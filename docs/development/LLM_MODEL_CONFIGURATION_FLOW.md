---
status: Living
target_goal: "Studio LLM configuration uses deterministic endpoint/route registry execution"
linked_code_paths:
  - apps/studio/frontend/src/components/studio/settings/endpoints/EndpointsTab.tsx
  - apps/studio/frontend/src/components/studio/settings/LlmRolesTab.tsx
  - apps/studio/frontend/src/api/llm.ts
  - apps/studio/backend/app/routers/llm.py
  - apps/studio/backend/app/services/llm_credentials.py
  - apps/studio/backend/app/services/llm_roles.py
  - apps/studio/backend/app/services/llm_import_drafts.py
  - packages/graph-agent-gateway/src/graph_agent_gateway/registry/
---

# LLM Endpoint/Route Configuration Flow

LLM Provider Intelligence V2 is a hard cut from provider cards, `available_models`, and short-code roles to an explicit endpoint/route registry. Runtime execution always uses exact `route_id` values from role fallback chains.

## 1. Concepts

- **Provider brand**: human/vendor label such as Anthropic, OpenAI, Qiniu, or OneChats. It is display metadata only.
- **ProviderEndpoint**: callable credential and transport root. It owns `endpoint_id`, protocol, base URL, API key, and endpoint test status.
- **ProviderRoute**: one physical model route under one endpoint. It owns `route_id`, `endpoint_id`, provider model ID, canonical display grouping, capabilities, and probe status.
- **ModelProfile**: authoring-time bundle such as `CLO47T = Claude Opus 4.7 Thinking`. A profile stores a fallback chain of exact route IDs.
- **RoleEntry**: runtime role config. It stores the actual fallback chain executed by the engine, plus optional source-profile trace metadata.
- **ProviderImportDraft**: non-trusted Agent import output. Drafts never write active endpoints or routes until the backend probe/diff/apply workflow accepts them.

## 2. Endpoints

Endpoints live in `~/.studio/llm_credentials.json` under `provider_endpoints`.

One provider brand can produce multiple endpoints when protocols or base URLs differ. Qiniu, for example, should be represented as two endpoints if both protocol URLs are used:

| endpoint_id | Protocol | Base URL |
|---|---|---|
| `qiniu-openai` | `openai_compatible` | `https://api.qnaigc.com/v1` |
| `qiniu-anthropic` | `anthropic_compatible` | `https://anthropic.qnaigc.com` |

Endpoint identity is immutable after creation. Editing display name, API key, status, timeout, or metadata does not change `endpoint_id`.

The endpoint test action only verifies the credential/base URL boundary. UI test responses must merge backend-owned diagnostic fields, such as `status`, `last_test_at`, and `last_test_message`, without overwriting local form edits that are still pending autosave.

## 3. Routes

Routes live in `~/.studio/llm_credentials.json` under `provider_routes`.

`route_id` is always:

```text
<endpoint_id>:<route_slug>
```

Examples:

| route_id | provider_model_id |
|---|---|
| `anthropic-official:claude-opus-4-7-thinking` | `claude-opus-4.7-thinking` |
| `onechats-anthropic:claude-sonnet-4-6` | `anthropic/claude-sonnet-4.6` |
| `qiniu-openai:deepseek-r1` | `deepseek-r1` |

Route identity fields are immutable: `route_id`, `endpoint_id`, and `provider_model_id` cannot be changed by metadata update APIs. Editable route fields are display name, canonical ID, status, capabilities, and diagnostic metadata.

Route probe replaces the old manual model probing flow. It records verified capability evidence on the route. Probe and lint results may block or warn, but they never select a replacement model.

## 4. Canonical Grouping

Canonical IDs are UI grouping keys supplied by backend DTOs. Frontend code must not canonicalize raw provider model strings, infer provider ownership, or prune stale providers locally.

`config/llm_canonical_rules.yaml` is the explicit source for curated aliases. Moving aliases such as OpenRouter `~...latest` are intentionally not canonical aliases unless they are pinned by a deliberate rule and test.

## 5. Import Drafts

Agent onboarding output enters a draft store, not active credentials.

Drafts can include multiple endpoint candidates and multiple route candidates. If a draft endpoint ID matches an active endpoint, apply must require an explicit merge/discard/delete-active-first decision. There is no auto-promote path from Agent output into runtime configuration.

## 6. Model Profiles and Roles

Model Profiles are reusable editing bundles. Applying a profile copies its fallback chain into a role. Runtime never resolves by profile ID.

Rules:

- Role fallback order is deterministic and user-controlled.
- Updating a profile does not implicitly mutate roles that previously used it.
- Deleting a profile does not delete role fallback chains; roles keep the route chain and receive deleted-profile trace metadata for UI display.
- `model_override` means one exact `route_id`, not a model code or capability intent.

## 7. Runtime Resolution

Studio Backend joins active credentials and roles into a `RegistrySnapshot`. The Gateway `ModelResolver` resolves a role by walking its fallback chain in order and joining each route to its endpoint.

The resolver may lint, warn, block invalid configuration, or fail fast. It must not search by capability, provider, price, latency, or availability to choose a different route.

Runtime credentials come from the resolved endpoint and route. `.env` provider keys, old provider cards, and old short-code schemas are not runtime inputs.

## 8. Provider Notes Archive

The provider notes archive lives in `docs/development/llm_provider_notes/`.

Those files are human and Agent-import reference material only. They are not loaded by Studio runtime code. Active endpoint/route state is stored in V4 credentials and V2 roles, with canonical alias rules limited to `config/llm_canonical_rules.yaml`.
