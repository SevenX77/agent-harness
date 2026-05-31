---
status: Draft
created: 2026-05-27
owner: Engine + Studio
related_requirements: .kiro/specs/studio-gateway-runtime-schema-boundary/requirements.md
---

# Gateway Runtime Schema Boundary Tasks

## Phase 0: Contract Lock

- [x] Confirm Gateway runtime schema must not contain `display_name`.
- [x] Confirm no compatibility fallback is allowed.
- [x] Confirm Studio Backend is the source of user-facing display names.
- [x] Confirm Gateway still uses `provider_model_id` for provider calls.

## Phase 1: Gateway Schema Cleanup

- [x] Remove `display_name` from `CanonicalModel`.
- [x] Remove `_display_name()` from `graph_agent_gateway.registry.canonical`.
- [x] Update `canonicalize_model()` to return only `canonical_id` and `confidence`.
- [x] Remove `display_name` from `ProviderEndpoint`.
- [x] Remove `display_name` from `ProviderRoute`.
- [x] Remove `display_name` from `ModelProfile` or remove `ModelProfile` from runtime path if it is no longer runtime-owned.
- [x] Keep Pydantic models `extra="forbid"` so old payloads fail loudly.
- [x] Update gateway tests and fixtures to remove runtime `display_name`.
- [x] Run `uv run pytest packages/graph-agent-gateway/tests -q`.

## Phase 2: Studio-Owned LLM DTOs

- [x] Split Studio-owned endpoint/route persistence models from Gateway runtime schema where display labels are needed.
- [x] Keep Studio provider display label on Studio-owned endpoint/config DTO.
- [x] Keep Studio model group display name on Studio-owned `/api/llm/registry` response DTO.
- [x] Keep provider row label on Studio-owned provider model option DTO.
- [x] Ensure generated Gateway `RegistrySnapshot` strips Studio display fields before resolver/runtime use.
- [x] Add tests that Studio-owned DTO can expose display fields while Gateway runtime snapshot rejects them.

## Phase 3: Studio Display Projection

- [x] Create Studio Backend model identity projection helper.
- [x] Input fields: `provider_model_id`, `canonical_id`, endpoint/provider metadata, curated provider/model rules.
- [x] Output fields: model group display name, model family/section label, confidence, optional diagnostic unknown tokens.
- [x] Preserve exact `route_id`, `provider_model_id`, and `canonical_id`.
- [x] Handle examples:
  - `claude-opus-4-7` -> `Claude Opus 4.7`
  - `claude-opus-4-1-20250805` -> `Claude Opus 4.1 20250805`
  - `deepseek/deepseek-v3.1-terminus-thinking` -> `DeepSeek V3.1 Terminus Thinking`
  - `gpt-5.5` -> `GPT 5.5`
  - `antigravity-preview-05-2026` -> `Antigravity Preview 05 2026`
- [x] Add Studio backend tests for display projection and section grouping.

## Phase 4: Studio API Serializer Cutover

- [x] Update `/api/llm/registry` model group serializer to call Studio display projection.
- [x] Stop reading `route.display_name`.
- [x] Update route create/probe paths so new routes do not require Gateway display names.
- [x] Update imports/migrations that previously wrote route display names.
- [x] Run `uv run pytest apps/studio/backend/tests/routers/test_llm_registry_api.py -q`.
- [x] Run relevant Studio backend LLM tests.

## Phase 5: Frontend Cleanup After Backend Projection

- [x] Update frontend `AvailableModelsSidebar` to use backend `model_groups[].display_name` directly.
- [x] Remove or demote frontend `model-identity-normalizer` to a test-only/dev fallback if backend projection is complete.
- [x] Ensure frontend tests fail if backend sends `Claude Opus 4 7` as authoritative display name.
- [x] Verify real UI screenshot for `opus` shows `Claude Opus 4.7`.
- [x] Run frontend LLM Roles tests/typecheck/lint.

## Phase 6: Audit Checklist Update

- [x] Add field ownership checklist to this spec or the parent LLM Roles spec.
- [x] Note in implementation PR that previous audits missed `display_name` because they validated wiring consistency, not layer ownership.
- [x] Add a regression test or static assertion preventing Gateway runtime models from gaining `display_name` again.
