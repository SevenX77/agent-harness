import { describe, expect, it } from "vitest"
import {
  applyCopilotModelGroupSelection,
  buildCopilotRoleEntry,
  deriveCopilotCandidateGroups,
  pickDefaultCopilotGroupIds,
} from "./copilot-role-derivation"
import type { CredentialsState, ModelGroup, RolesData } from "@/api/llm"

function route(endpointId: string, modelId: string, uiState: string) {
  return {
    route_id: `${endpointId}:${modelId}`,
    endpoint_id: endpointId,
    provider_label: endpointId,
    provider_kind: endpointId.includes("official") ? "official" : "third_party",
    provider_model_id: modelId,
    ui_state: uiState,
    ui_detail: null,
    retry_at: null,
    reason_code: null,
    capability_state: "known",
    capabilities: {},
  }
}

function group(canonicalId: string, displayName: string, uiState = "ready"): ModelGroup {
  return {
    canonical_id: canonicalId,
    display_name: displayName,
    provider_models: [route("anthropic-official", canonicalId, uiState)],
    status_summary: { ready: 1, untested: 0, cooling_down: 0, historical_ready: 0, failed: 0, off: 0 },
    capability_summary: {
      capability_known_count: 1,
      thinking: "unknown",
      tools: "unknown",
      structured_output: "unknown",
      max_context_tokens: null,
      max_output_tokens: null,
    },
  } as ModelGroup
}

const anthropicCredentials: CredentialsState = {
  providers: [{ id: "anthropic-official", name: "Anthropic Official", provider_type: "anthropic_compatible", api_key: "**********" }],
}

describe("pickDefaultCopilotGroupIds — family preference ladder", () => {
  it("prefers opus-4.8 over 4.7 when both are present", () => {
    const candidates = deriveCopilotCandidateGroups(
      [group("claude-opus-4.8", "Claude Opus 4.8"), group("claude-opus-4.7", "Claude Opus 4.7")],
      anthropicCredentials,
    )
    expect(pickDefaultCopilotGroupIds(candidates)).toEqual(["claude-opus-4.8"])
  })

  it("falls back to opus-4.7 when 4.8 is absent", () => {
    const candidates = deriveCopilotCandidateGroups([group("claude-opus-4.7", "Claude Opus 4.7")], anthropicCredentials)
    expect(pickDefaultCopilotGroupIds(candidates)).toEqual(["claude-opus-4.7"])
  })

  it("floats one per family — Claude best + DeepSeek best", () => {
    const candidates = deriveCopilotCandidateGroups(
      [
        group("claude-opus-4.8", "Claude Opus 4.8"),
        group("deepseek-v4-pro", "DeepSeek V4 Pro"),
        group("deepseek-v3.2-pro", "DeepSeek V3.2 Pro"),
      ],
      anthropicCredentials,
    )
    expect(pickDefaultCopilotGroupIds(candidates)).toEqual(["claude-opus-4.8", "deepseek-v4-pro"])
  })

  it("floats nothing when neither family has a ladder model", () => {
    const candidates = deriveCopilotCandidateGroups([group("some-other-model", "Some Other Model")], anthropicCredentials)
    expect(pickDefaultCopilotGroupIds(candidates)).toEqual([])
  })
})

describe("deriveCopilotCandidateGroups — Built-in detection (floated-set, single source of truth)", () => {
  it("marks the floated default as built_in and a non-floated ladder peer as third_party", () => {
    const candidates = deriveCopilotCandidateGroups(
      [group("claude-opus-4.8", "Claude Opus 4.8"), group("claude-opus-4.7", "Claude Opus 4.7")],
      anthropicCredentials,
    )
    const byId = Object.fromEntries(candidates.map((c) => [c.id, c]))
    // 4.8 is floated → built_in; 4.7 is a canonical model but NOT the floated default → third_party
    expect(byId["claude-opus-4.8"].source).toBe("built_in")
    expect(byId["claude-opus-4.7"].source).toBe("third_party")
  })

  it("marks a user-built (non-ladder) group as third_party", () => {
    const candidates = deriveCopilotCandidateGroups([group("my-private-claude", "My Private Claude")], anthropicCredentials)
    expect(candidates[0].source).toBe("third_party")
  })

  it("derives description from the normalized display_name, not a Claude/DeepSeek family template", () => {
    const candidates = deriveCopilotCandidateGroups([group("claude-opus-4.8", "Claude Opus 4.8")], anthropicCredentials)
    expect(candidates[0].description).not.toBe("Anthropic Claude reasoning agent")
    expect(candidates[0].description).toBe("Claude Opus 4.8")
  })

  it("only lists groups that have at least one Anthropic-compatible route", () => {
    const candidates = deriveCopilotCandidateGroups(
      [group("claude-opus-4.8", "Claude Opus 4.8")],
      { providers: [{ id: "openai-key", name: "OpenAI", provider_type: "openai_compatible", api_key: "x" }] },
    )
    expect(candidates).toEqual([])
  })
})

describe("buildCopilotRoleEntry — materialize a floated/selected group into a persistable copilot role", () => {
  it("builds a copilot role from the group's ready routes", () => {
    const [candidate] = deriveCopilotCandidateGroups([group("claude-opus-4.8", "Claude Opus 4.8")], anthropicCredentials)
    const entry = buildCopilotRoleEntry(candidate)
    expect(entry.role_kind).toBe("copilot")
    expect(entry.active_model).toBe("claude-opus-4.8")
    expect(entry.models["claude-opus-4.8"].providers).toEqual(["anthropic-official:claude-opus-4.8"])
    expect(entry.fallback_chain).toEqual([
      { route_id: "anthropic-official:claude-opus-4.8", runtime_settings: {} },
    ])
  })

  it("excludes non-ready routes from the default fallback chain", () => {
    const [candidate] = deriveCopilotCandidateGroups(
      [group("claude-opus-4.8", "Claude Opus 4.8", "untested")],
      anthropicCredentials,
    )
    const entry = buildCopilotRoleEntry(candidate)
    expect(entry.fallback_chain).toEqual([])
  })

  it("keeps only the ready routes when a group mixes ready and non-ready", () => {
    const mixedGroup = {
      canonical_id: "claude-opus-4.8",
      display_name: "Claude Opus 4.8",
      provider_models: [
        route("anthropic-official", "claude-opus-4.8", "ready"),
        route("qiniu-anthropic", "claude-opus-4.8", "untested"),
      ],
      status_summary: { ready: 1, untested: 1, cooling_down: 0, historical_ready: 0, failed: 0, off: 0 },
      capability_summary: {
        capability_known_count: 2,
        thinking: "unknown",
        tools: "unknown",
        structured_output: "unknown",
        max_context_tokens: null,
        max_output_tokens: null,
      },
    } as ModelGroup
    const twoKeyCredentials: CredentialsState = {
      providers: [
        { id: "anthropic-official", name: "Anthropic Official", provider_type: "anthropic_compatible", api_key: "x" },
        { id: "qiniu-anthropic", name: "Qiniu Anthropic", provider_type: "anthropic_compatible", api_key: "x" },
      ],
    }
    const [candidate] = deriveCopilotCandidateGroups([mixedGroup], twoKeyCredentials)
    const entry = buildCopilotRoleEntry(candidate)
    expect(entry.fallback_chain).toEqual([
      { route_id: "anthropic-official:claude-opus-4.8", runtime_settings: {} },
    ])
    expect(entry.models["claude-opus-4.8"].providers).toEqual(["anthropic-official:claude-opus-4.8"])
  })
})

describe("applyCopilotModelGroupSelection — selecting a group keeps the copilot role identity", () => {
  function emptyDraftRoles(): RolesData {
    return {
      schema_version: 3,
      models: {},
      providers: {},
      model_profiles: {},
      model_bundles: {},
      roles: {
        copilot_custom_1: {
          role_kind: "copilot",
          model_fallback_enabled: true,
          intent: { provider_preference: "manual_order" },
          model_groups: [],
          active_model: "",
          models: {},
          fallback_chain: [],
        },
      },
    }
  }

  it("preserves the copilot_ role key and role_kind, and writes the chosen group (no graph-agent misfile)", () => {
    const [candidate] = deriveCopilotCandidateGroups([group("claude-opus-4.8", "Claude Opus 4.8")], anthropicCredentials)
    const next = applyCopilotModelGroupSelection(emptyDraftRoles(), "copilot_custom_1", candidate.id, candidate.availableRoutes)

    // Role key is NOT renamed to the model-group id (the old prefix bug).
    expect(Object.keys(next.roles)).toEqual(["copilot_custom_1"])
    const role = next.roles.copilot_custom_1
    expect(role.role_kind).toBe("copilot")
    expect(role.active_model).toBe("claude-opus-4.8")
    expect(role.models["claude-opus-4.8"].providers).toEqual(["anthropic-official:claude-opus-4.8"])
  })
})
