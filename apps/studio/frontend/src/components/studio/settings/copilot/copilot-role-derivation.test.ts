import { describe, expect, it } from "vitest"
import {
  applyCopilotModelGroupSelection,
  buildCopilotRoleEntry,
  deriveCopilotCandidateGroups,
  copilotKeyForGroupId,
  hostFromBaseUrl,
  pickDefaultCopilotGroupIds,
  routeSupportsCopilotSdk,
  resolveCopilotSendRole,
} from "./copilot-role-derivation"
import type { CredentialsState, ModelGroup, ProviderModelOption, RolesData } from "@/api/llm"

function route(
  endpointId: string,
  modelId: string,
  uiState: ProviderModelOption["ui_state"],
  callMethodId: string | null = "anthropic_messages",
  capabilities: ProviderModelOption["capabilities"] = {},
): ProviderModelOption {
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
    capabilities,
    call_method_id: callMethodId,
  }
}

function group(
  canonicalId: string,
  displayName: string,
  uiState: ProviderModelOption["ui_state"] = "ready",
): ModelGroup {
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

  it("filters a route with an explicit non-Anthropic call method", () => {
    // A verified non-Anthropic method is stronger evidence than endpoint-level
    // protocol metadata, so this route cannot be driven by Claude Agent SDK.
    const openaiOnlyGroup = {
      canonical_id: "claude-opus-4.8",
      display_name: "Claude Opus 4.8",
      provider_models: [route("anthropic-official", "claude-opus-4.8", "ready", "openai_chat_completions")],
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
    const candidates = deriveCopilotCandidateGroups([openaiOnlyGroup], anthropicCredentials)
    expect(candidates).toEqual([])
  })

  it("keeps Anthropic-compatible endpoint routes when the call method is not verified yet", () => {
    const qiniuGroup = {
      canonical_id: "deepseek-v4-pro",
      display_name: "DeepSeek V4 Pro",
      provider_models: [
        route("qiniu-anthropic", "deepseek-v4-pro", "ready", null, {
          tools: { value: true, source: "probed_verified" },
        }),
      ],
      status_summary: { ready: 1, untested: 0, cooling_down: 0, historical_ready: 0, failed: 0, off: 0 },
      capability_summary: {
        capability_known_count: 1,
        thinking: "unknown",
        tools: "supported",
        structured_output: "unknown",
        max_context_tokens: null,
        max_output_tokens: null,
      },
    } as ModelGroup
    const credentials: CredentialsState = {
      providers: [
        {
          id: "qiniu-anthropic",
          name: "Qiniu",
          provider_type: "anthropic_compatible",
          api_key: "x",
          base_url: "https://anthropic.qnaigc.com/anthropic",
        },
      ],
    }

    const candidates = deriveCopilotCandidateGroups([qiniuGroup], credentials)

    expect(candidates).toHaveLength(1)
    expect(candidates[0].availableRoutes.map((route) => route.id)).toEqual([
      "qiniu-anthropic:deepseek-v4-pro",
    ])
    expect(candidates[0].availableRoutes[0].methodId).toBeNull()
    expect(candidates[0].availableRoutes[0].protocol).toBe("anthropic_compatible")
  })

  it("filters routes with no verified call method when the endpoint protocol is not Anthropic-compatible", () => {
    const openaiUnknownMethodGroup = {
      canonical_id: "gpt-5",
      display_name: "GPT-5",
      provider_models: [route("openai-official", "gpt-5", "ready", null)],
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
    const credentials: CredentialsState = {
      providers: [
        { id: "openai-official", name: "OpenAI", provider_type: "openai_compatible", api_key: "x" },
      ],
    }

    expect(deriveCopilotCandidateGroups([openaiUnknownMethodGroup], credentials)).toEqual([])
  })

  it("accepts ark/deepseek/openrouter anthropic-messages variants alongside the official call method", () => {
    // R-F8: the whitelist covers all four anthropic-messages call methods.
    const arkGroup = {
      canonical_id: "claude-opus-4.8",
      display_name: "Claude Opus 4.8",
      provider_models: [route("ark-official", "claude-opus-4.8", "ready", "ark_anthropic_messages")],
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
    const candidates = deriveCopilotCandidateGroups([arkGroup], anthropicCredentials)
    expect(candidates).toHaveLength(1)
    expect(candidates[0].availableRoutes).toHaveLength(1)
  })

  it("filters routes whose explicit capability evidence says the SDK-required tool loop is unsupported", () => {
    const mixedGroup = {
      canonical_id: "claude-opus-4.8",
      display_name: "Claude Opus 4.8",
      provider_models: [
        route("anthropic-official", "claude-opus-4.8", "ready", "anthropic_messages", {
          tools: { value: true, source: "probed_verified" },
        }),
        route("no-tools-endpoint", "claude-opus-4.8", "ready", null, {
          tools: { value: false, source: "probed_verified" },
        }),
      ],
      status_summary: { ready: 2, untested: 0, cooling_down: 0, historical_ready: 0, failed: 0, off: 0 },
      capability_summary: {
        capability_known_count: 2,
        thinking: "unknown",
        tools: "mixed",
        structured_output: "unknown",
        max_context_tokens: null,
        max_output_tokens: null,
      },
    } as ModelGroup
    const twoKeyCredentials: CredentialsState = {
      providers: [
        { id: "anthropic-official", name: "Anthropic Official", provider_type: "anthropic_compatible", api_key: "x" },
        { id: "no-tools-endpoint", name: "No Tools", provider_type: "anthropic_compatible", api_key: "x" },
      ],
    }

    const candidates = deriveCopilotCandidateGroups([mixedGroup], twoKeyCredentials)

    expect(candidates).toHaveLength(1)
    expect(candidates[0].availableRoutes.map((r) => r.id)).toEqual([
      "anthropic-official:claude-opus-4.8",
    ])
  })

  it("keeps unknown tool capability routes visible so the SDK test can collect evidence", () => {
    const untested = route("anthropic-official", "claude-opus-4.8", "untested", "anthropic_messages", {})

    expect(routeSupportsCopilotSdk(untested)).toBe(true)
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

  it("R-F4: keeps untested routes in the default fallback chain so Test can run them", () => {
    // R-F4 / spec §3.2 #3: do NOT pre-filter the chain by uiState. Untested
    // routes must be in the chain so the user can drive Test against them;
    // otherwise no route ever gets to ready.
    const [candidate] = deriveCopilotCandidateGroups(
      [group("claude-opus-4.8", "Claude Opus 4.8", "untested")],
      anthropicCredentials,
    )
    const entry = buildCopilotRoleEntry(candidate)
    expect(entry.fallback_chain).toEqual([
      { route_id: "anthropic-official:claude-opus-4.8", runtime_settings: {} },
    ])
  })

  it("R-F4: keeps both ready and non-ready routes when a group mixes states", () => {
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
      { route_id: "qiniu-anthropic:claude-opus-4.8", runtime_settings: {} },
    ])
    expect(entry.models["claude-opus-4.8"].providers).toEqual([
      "anthropic-official:claude-opus-4.8",
      "qiniu-anthropic:claude-opus-4.8",
    ])
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

// F3 (03_regions/copilot mvp1-alignment): sending a chat message with a
// floated built-in role materializes it through the same path Settings uses.
describe("resolveCopilotSendRole", () => {
  const anthropicCredentials: CredentialsState = {
    providers: [
      { id: "anthropic-official", name: "Anthropic Official", provider_type: "anthropic_compatible", api_key: "***" },
    ],
  }
  const groups = [group("claude-opus-4.8", "Claude Opus 4.8")]

  function rolesData(roles: RolesData["roles"]): RolesData {
    return { models: {}, providers: {}, roles }
  }

  it("passes a persisted role key through untouched", () => {
    const data = rolesData({
      copilot_claude_opus_4_8: {
        role_kind: "copilot",
        system_prompt_prefix: "",
        model_fallback_enabled: true,
        active_model: "claude-opus-4.8",
        models: { "claude-opus-4.8": { providers: ["anthropic-official:claude-opus-4.8"] } },
        fallback_chain: [{ route_id: "anthropic-official:claude-opus-4.8", runtime_settings: {} }],
      },
    })

    expect(resolveCopilotSendRole(
      data,
      { role: "copilot_claude_opus_4_8", persisted: true, modelGroupId: "claude-opus-4.8" },
      groups,
      anthropicCredentials,
    )).toEqual({ roleKey: "copilot_claude_opus_4_8", nextRoles: null })
  })

  it("materializes a floated built-in under copilot_<slug> with the full eligible chain", () => {
    const data = rolesData({})

    const resolution = resolveCopilotSendRole(
      data,
      { role: "claude-opus-4.8", persisted: false, modelGroupId: "claude-opus-4.8" },
      groups,
      anthropicCredentials,
    )

    expect(resolution.roleKey).toBe("copilot_claude_opus_4_8")
    const entry = resolution.nextRoles?.roles.copilot_claude_opus_4_8
    expect(entry?.role_kind).toBe("copilot")
    expect(entry?.active_model).toBe("claude-opus-4.8")
    expect(entry?.fallback_chain).toEqual([
      { route_id: "anthropic-official:claude-opus-4.8", runtime_settings: {} },
    ])
  })

  it("reuses an already-persisted copilot_<slug> entry instead of rewriting it", () => {
    const data = rolesData({
      copilot_claude_opus_4_8: {
        role_kind: "copilot",
        system_prompt_prefix: "",
        model_fallback_enabled: true,
        active_model: "claude-opus-4.8",
        models: { "claude-opus-4.8": { providers: ["anthropic-official:claude-opus-4.8"] } },
        fallback_chain: [{ route_id: "anthropic-official:claude-opus-4.8", runtime_settings: {} }],
      },
    })

    expect(resolveCopilotSendRole(
      data,
      { role: "claude-opus-4.8", persisted: false, modelGroupId: "claude-opus-4.8" },
      groups,
      anthropicCredentials,
    )).toEqual({ roleKey: "copilot_claude_opus_4_8", nextRoles: null })
  })
})

describe("copilotKeyForGroupId", () => {
  it("derives the yaml-safe copilot_ key", () => {
    expect(copilotKeyForGroupId("claude-opus-4.8")).toBe("copilot_claude_opus_4_8")
    expect(copilotKeyForGroupId("DeepSeek V3.2-Pro")).toBe("copilot_deepseek_v3_2_pro")
    expect(copilotKeyForGroupId("a:b/c.d")).toBe("copilot_a_b_c_d")
  })
})

describe("copilot route endpoint disambiguation (谁是谁)", () => {
  it("hostFromBaseUrl extracts the host", () => {
    expect(hostFromBaseUrl("https://api.qnaigc.com/v1")).toBe("api.qnaigc.com")
    expect(hostFromBaseUrl("anthropic.qnaigc.com/anthropic")).toBe("anthropic.qnaigc.com")
    expect(hostFromBaseUrl(null)).toBeNull()
    expect(hostFromBaseUrl("")).toBeNull()
  })

  it("distinguishes same-provider routes by host so 14 'Qiniu' rows are no longer identical", () => {
    // Two Qiniu endpoints, same provider_label but different host/protocol → labels must differ.
    const modelGroup = {
      canonical_id: "deepseek.deepseek-v4-pro",
      display_name: "DeepSeek V4 Pro",
      provider_models: [
        route("anthropic-qnaigc-com-anthropic-38963c9239", "deepseek.deepseek-v4-pro", "ready"),
        route("api-qnaigc-com-anthropic-a3f5205ffe", "deepseek.deepseek-v4-pro", "ready"),
      ],
      status_summary: { ready: 2, untested: 0, cooling_down: 0, historical_ready: 0, failed: 0, off: 0 },
      capability_summary: {
        capability_known_count: 1, thinking: "unknown", tools: "unknown",
        structured_output: "unknown", max_context_tokens: null, max_output_tokens: null,
      },
    } as ModelGroup
    // both endpoints share provider_label "Qiniu" but different base_url host.
    modelGroup.provider_models[0].provider_label = "Qiniu"
    modelGroup.provider_models[1].provider_label = "Qiniu"
    const credentials: CredentialsState = {
      providers: [
        { id: "anthropic-qnaigc-com-anthropic-38963c9239", name: "Qiniu", provider_type: "anthropic_compatible", api_key: "**********", base_url: "https://anthropic.qnaigc.com/anthropic" },
        { id: "api-qnaigc-com-anthropic-a3f5205ffe", name: "Qiniu", provider_type: "anthropic_compatible", api_key: "**********", base_url: "https://api.qnaigc.com/anthropic" },
      ],
    }

    const candidates = deriveCopilotCandidateGroups([modelGroup], credentials)
    const labels = candidates[0].availableRoutes.map((r) => r.endpointLabel)
    expect(labels).toEqual(["Qiniu · anthropic.qnaigc.com", "Qiniu · api.qnaigc.com"])
    // and they carry the host for the tooltip
    expect(candidates[0].availableRoutes[0].baseUrlHost).toBe("anthropic.qnaigc.com")
  })
})
