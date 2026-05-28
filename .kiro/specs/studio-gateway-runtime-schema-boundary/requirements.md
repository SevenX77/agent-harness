---
status: Draft
created: 2026-05-27
owner: Engine + Studio
related_specs:
  - .kiro/specs/studio-llm-roles-model-groups/
  - .kiro/specs/llm-provider-intelligence-v2/
  - .kiro/specs/engine-mvp0-rebuild-v030/round-9-PR-alpha-gateway-llm-roles/
related_code_paths:
  - packages/graph-agent-gateway/src/graph_agent_gateway/registry/schema.py
  - packages/graph-agent-gateway/src/graph_agent_gateway/registry/canonical.py
  - packages/graph-agent-gateway/src/graph_agent_gateway/registry/resolver.py
  - apps/studio/backend/app/models/llm_config.py
  - apps/studio/backend/app/services/llm_credentials.py
  - apps/studio/backend/app/routers/llm.py
---

# Gateway Runtime Schema Boundary Requirements

## Context

Gateway is the engine LLM execution layer. It resolves concrete route candidates, enforces admission/lint, calls provider clients, records runtime health, and falls back to later candidates. It is not a Studio UI or authoring schema.

The current gateway registry schema contains `display_name` on runtime models such as `ProviderEndpoint`, `ProviderRoute`, `ModelProfile`, and `CanonicalModel`. This leaks UI/admin vocabulary into the execution contract and caused Studio to receive model group display names such as `Claude Opus 4 7`.

This spec removes UI display fields from Gateway runtime schema without compatibility fallback. If any caller still depends on these fields, tests should fail until the caller is moved to a Studio-owned DTO or an explicit non-runtime admin DTO.

## Requirement 1: Gateway Runtime Schema Has No UI Display Fields

**Goal:** Gateway runtime data must contain only execution facts.

Acceptance criteria:

1. `ProviderEndpoint` in gateway runtime schema must not define `display_name`.
2. `ProviderRoute` in gateway runtime schema must not define `display_name`.
3. `CanonicalModel` in gateway canonicalization must not define `display_name`.
4. `ModelProfile` and any remaining gateway runtime authoring types must not define `display_name`.
5. Import-draft or Studio admin DTOs may have labels only outside gateway runtime schema.
6. Tests must fail if a gateway runtime payload includes unknown `display_name` fields.

## Requirement 2: Gateway Calls Providers With Real Provider Model IDs

**Goal:** Gateway execution must use exact provider model identifiers, not display or normalized labels.

Acceptance criteria:

1. Provider clients receive `ProviderRoute.provider_model_id` as the model name.
2. `canonical_id` is allowed only as grouping/fallback metadata and must not replace `provider_model_id` for provider calls.
3. `route_id` remains the concrete route selection identity.
4. `endpoint_id` remains the endpoint lookup identity.
5. Removing `display_name` must not change provider request payload model values.

## Requirement 3: Studio Owns Display Projection

**Goal:** Studio Backend must compute user-facing display names and sections before sending data to frontend.

Acceptance criteria:

1. Studio Backend exposes `model_groups[].display_name`.
2. Studio Backend exposes model group section/family metadata needed by the frontend list.
3. Studio Backend exposes provider labels for user-facing provider rows.
4. Studio display projection may use `provider_model_id`, `canonical_id`, provider kind, provider family, and curated Studio model identity rules.
5. Studio display projection must preserve exact `route_id` and `provider_model_id` unchanged for execution.
6. Frontend displays Studio Backend projection directly.
7. Frontend must not import or emulate gateway canonical display logic.

## Requirement 4: No Compatibility Fallback

**Goal:** Boundary violations must be caught immediately.

Acceptance criteria:

1. Gateway Pydantic runtime models remain `extra="forbid"`.
2. `display_name` is removed from tests and fixtures, not silently ignored.
3. Studio code that still tries to read gateway `route.display_name` must fail tests.
4. API serializers must explicitly map Studio-owned display fields rather than forwarding gateway runtime models.
5. Migration code must write Studio display fields only into Studio-owned storage/DTOs.

## Requirement 5: Audit Gap Is Documented

**Goal:** Future audits must check layer ownership, not only whether fields are wired consistently.

Acceptance criteria:

1. This spec records why prior audits missed the boundary issue.
2. Future LLM registry audits must include a field ownership checklist:
   - runtime execution field
   - Studio authoring field
   - Studio UI projection field
   - import/admin-only field
3. Any field used by frontend visible UI must be traced to a Studio-owned DTO.
4. Any field in gateway runtime schema must be justified by execution, admission, lint, or runtime health.

