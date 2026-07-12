import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it, vi } from "vitest"
import type { RegistryResponse, RolesData } from "../../../api/llm"
import { rolesDataFromBackend, rolesDataToBackend } from "../../../api/llm"
import { normalizeRolesDraft } from "./role-utils"
import { RoleCard } from "./llm-roles/RoleCard"

// A registry that has been fully loaded but simply does NOT know the vocabulary
// referenced by the role below (the model group's canonical id / route id are
// absent). This is the exact steady-state the data-loss bug fires in: a real,
// hydrated registry that no longer recognizes a persisted model group (route
// deleted, credential expired, model retired, canonical id renamed).
const registryWithoutVocab: RegistryResponse = {
  provider_endpoints: {},
  provider_routes: {},
  runtime_policy: {
    provider_down_ttl_seconds: 0,
    probe_timeout_seconds: 0,
    token_escalation_rounds: 0,
  },
  model_profiles: {},
  model_groups: [],
  roles: {},
  canonical_groups: [],
  lint_results: [],
  setup_required: false,
}

// The backend `roles_data` projection: schema_version + roles with model_groups,
// and crucially NO top-level `models`/`providers` maps (so it is not treated as a
// legacy role-map payload). The `analyst` role references a model group whose
// canonical id + route id are unknown to `registryWithoutVocab`.
const ORIGINAL_MODEL_GROUP = {
  canonical_id: "anthropic.claude-opus-4.8",
  display_name: "Claude Opus 4.8",
  provider_models: [{ route_id: "anthropic-official:claude-opus-4-8" }],
}

function backendRolesReferencingUnknownVocab(): RolesData {
  return {
    schema_version: 3,
    model_profiles: {},
    model_bundles: {},
    roles: {
      analyst: {
        role_kind: "graph_agent",
        system_prompt_prefix: "",
        model_fallback_enabled: true,
        intent: {
          provider_preference: "manual_order",
          thinking: false,
          max_output_tokens: null,
          temperature: 1.4,
        },
        model_groups: [structuredClone(ORIGINAL_MODEL_GROUP)],
        fallback_chain: [],
        lint_requirements: {},
      },
    },
  } as unknown as RolesData
}

describe("settings role autosave data-loss (unknown-vocabulary model groups)", () => {
  it("命门: a role referencing unknown-vocabulary survives a lossless load→project→normalize→serialize round-trip", () => {
    const backend = backendRolesReferencingUnknownVocab()

    // load → project (synthesize placeholder) → normalize (autosave path) →
    // serialize back to the backend payload.
    const projected = rolesDataFromBackend(backend, registryWithoutVocab)
    const normalized = normalizeRolesDraft(projected)
    const writeback = rolesDataToBackend(normalized)

    // The written-back model group must be BYTE-FOR-BYTE the original input:
    // canonical_id / display_name / route_id all unchanged.
    expect(writeback.roles.analyst.model_groups).toEqual([ORIGINAL_MODEL_GROUP])

    // The placeholder is for the UI only: none of its display-only decorations
    // (`unknown_id`, "(未注册)"/"(unregistered)", "(offline)") may leak into the
    // data that gets persisted to truth.
    const serialized = JSON.stringify(writeback)
    expect(serialized).not.toContain("unknown_id")
    expect(serialized).not.toContain("未注册")
    expect(serialized).not.toContain("unregistered")
    expect(serialized).not.toContain("offline")
    expect(writeback.roles.analyst.model_groups[0].display_name).toBe("Claude Opus 4.8")
  })

  it("synthesizes an is_unresolved placeholder (clean display name) for the unknown model + route", () => {
    const projected = rolesDataFromBackend(backendRolesReferencingUnknownVocab(), registryWithoutVocab)

    const placeholder = projected.models["anthropic.claude-opus-4.8"]
    expect(placeholder?.is_unresolved).toBe(true)
    // The placeholder keeps the ORIGINAL display name so the serializer writes it
    // back verbatim — the "(未注册)" decoration lives in the UI, not the data.
    expect(placeholder?.name).toBe("Claude Opus 4.8")

    const providerPlaceholder = projected.providers["anthropic-official:claude-opus-4-8"]
    expect(providerPlaceholder?.is_unresolved).toBe(true)

    // The role still carries the real route id (its authoring intent), not a
    // pruned-empty group.
    expect(projected.roles.analyst.models["anthropic.claude-opus-4.8"].providers).toEqual([
      "anthropic-official:claude-opus-4-8",
    ])
  })

  it("normalizeRolesDraft does not prune the placeholder-backed unknown group (no silent trim)", () => {
    const projected = rolesDataFromBackend(backendRolesReferencingUnknownVocab(), registryWithoutVocab)

    const normalized = normalizeRolesDraft(projected)

    // The unknown group is retained and active_model is NOT wiped to "".
    expect(normalized.roles.analyst.models["anthropic.claude-opus-4.8"]).toBeTruthy()
    expect(normalized.roles.analyst.active_model).toBe("anthropic.claude-opus-4.8")
  })

  it("renders an explicit broken-state on the role card for an unresolved model group", () => {
    const projected = rolesDataFromBackend(backendRolesReferencingUnknownVocab(), registryWithoutVocab)

    const html = renderToStaticMarkup(
      <RoleCard
        data={projected}
        category="graph-agent"
        credentialsByCode={{}}
        modelDisplayNamesByCode={new Map()}
        ownedProviderCodesByModel={new Map()}
        roleName="analyst"
        onRunTestChain={vi.fn()}
        getActiveAvailableModelDragId={() => null}
        getAvailableModelGroup={() => null}
        onChange={vi.fn()}
        onDeleteRole={vi.fn()}
      />,
    )

    expect(html).toContain('data-model-unresolved="true"')
  })
})
