import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it, vi } from "vitest"
import {
  CopilotTab,
  copilotBackendReadyCount,
  copilotGroupComboboxFilter,
  copilotGroupSearchValue,
} from "./CopilotTab"
import { agentStatusForRoute } from "./CopilotModelGroupCard"
import type { CopilotRolePreview, CopilotRoutePreview } from "./copilot-role-derivation"
import type { CredentialsState, ModelGroup, RolesData } from "@/api/llm"

vi.mock("react-i18next", () => ({
  initReactI18next: {
    type: "3rdParty",
    init: () => undefined,
  },
  useTranslation: () => ({ t: (key: string) => key }),
}))

vi.mock("@/api/client", () => ({
  getRoleTestResults: vi.fn(async () => ({ results: {} })),
}))

function registryModelGroups(): ModelGroup[] {
  return [
    {
      canonical_id: "claude-opus-4.7",
      display_name: "Claude Opus 4.7",
      provider_models: [
        {
          route_id: "anthropic-official:claude-opus-4-7",
          endpoint_id: "anthropic-official",
          provider_label: "Anthropic Official",
          provider_kind: "official",
          provider_model_id: "claude-opus-4-7",
          ui_state: "ready",
          ui_detail: null,
          retry_at: null,
          reason_code: null,
          capability_state: "known",
          capabilities: {},
        },
        {
          route_id: "qiniu-anthropic:claude-opus-4-7",
          endpoint_id: "qiniu-anthropic",
          provider_label: "Qiniu Anthropic",
          provider_kind: "third_party",
          provider_model_id: "claude-opus-4-7",
          ui_state: "untested",
          ui_detail: null,
          retry_at: null,
          reason_code: null,
          capability_state: "known",
          capabilities: {},
        },
      ],
      status_summary: {
        ready: 1,
        untested: 1,
        cooling_down: 0,
        historical_ready: 0,
        failed: 0,
        off: 0,
      },
      capability_summary: {
        capability_known_count: 2,
        thinking: "unknown",
        tools: "unknown",
        structured_output: "unknown",
        max_context_tokens: null,
        max_output_tokens: null,
      },
    },
  ]
}

function credentials(): CredentialsState {
  return {
    providers: [
      {
        id: "anthropic-official",
        name: "Anthropic Official",
        provider_type: "anthropic_compatible",
        api_key: "**********",
      },
      {
        id: "qiniu-anthropic",
        name: "Qiniu Anthropic",
        provider_type: "anthropic_compatible",
        api_key: "**********",
      },
    ],
  }
}

function roles(): RolesData {
  return {
    schema_version: 3,
    models: {},
    providers: {},
    model_profiles: {},
    model_bundles: {},
    roles: {
      copilot_opus: {
        role_kind: "copilot",
        system_prompt_prefix: "",
        model_fallback_enabled: true,
        intent: { provider_preference: "manual_order" },
        model_groups: [],
        active_model: "claude-opus-4.7",
        models: {
          "claude-opus-4.7": {
            providers: [
              "anthropic-official:claude-opus-4-7",
              "qiniu-anthropic:claude-opus-4-7",
            ],
          },
        },
        fallback_chain: [
          { route_id: "anthropic-official:claude-opus-4-7", runtime_settings: {} },
          { route_id: "qiniu-anthropic:claude-opus-4-7", runtime_settings: {} },
        ],
        lint_requirements: {},
      },
    },
  }
}

describe("CopilotTab route status projection", () => {
  it("computes ready count from backend agentStatus rather than route test overrides", () => {
    const routes = [
      { id: "ready:route", agentStatus: "ready" },
      { id: "untested:route", agentStatus: "untested" },
    ]

    expect(copilotBackendReadyCount(routes, { "untested:route": "ready" })).toBe(1)
  })

  it("only lets live testing override backend route status", () => {
    expect(agentStatusForRoute("untested", "route-a", { "route-a": "ready" })).toBe("untested")
    expect(agentStatusForRoute("ready", "route-a", { "route-a": "unsupported" })).toBe("ready")
    expect(agentStatusForRoute("untested", "route-a", { "route-a": "testing" })).toBe("testing")
  })

  it("renders SDK ready count from backend DTO facts rather than route test overrides", () => {
    const html = renderToStaticMarkup(
      <CopilotTab data={roles()} credentials={credentials()} modelGroups={registryModelGroups()} />,
    )

    expect(html).toContain("1/2 SDK Ready")
  })
})

function opusGroup(canonicalId: string, displayName: string): ModelGroup {
  return {
    canonical_id: canonicalId,
    display_name: displayName,
    provider_models: [
      {
        route_id: `anthropic-official:${canonicalId}`,
        endpoint_id: "anthropic-official",
        provider_label: "Anthropic Official",
        provider_kind: "official",
        provider_model_id: canonicalId,
        ui_state: "ready",
        ui_detail: null,
        retry_at: null,
        reason_code: null,
        capability_state: "known",
        capabilities: {},
      },
    ],
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

function emptyRoles(): RolesData {
  return { schema_version: 3, models: {}, providers: {}, model_profiles: {}, model_bundles: {}, roles: {} }
}

function rolesWithDraft(): RolesData {
  return {
    ...emptyRoles(),
    roles: {
      copilot_custom_1: {
        role_kind: "copilot",
        system_prompt_prefix: "",
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

describe("CopilotTab #56 dynamic float of built-in defaults", () => {
  it("floats the family-ladder built-in default when no copilot role exists", () => {
    const html = renderToStaticMarkup(
      <CopilotTab data={emptyRoles()} credentials={credentials()} modelGroups={[opusGroup("claude-opus-4.8", "Claude Opus 4.8")]} />,
    )
    expect(html).toContain("Claude Opus 4.8")
    expect(html).toContain('data-copilot-role-source="built_in"')
    expect(html).toContain("Built-in")
  })

  it("prefers opus-4.8 over 4.7 when both are available", () => {
    const html = renderToStaticMarkup(
      <CopilotTab
        data={emptyRoles()}
        credentials={credentials()}
        modelGroups={[opusGroup("claude-opus-4.7", "Claude Opus 4.7"), opusGroup("claude-opus-4.8", "Claude Opus 4.8")]}
      />,
    )
    expect(html).toContain("Claude Opus 4.8")
    // 4.7 is not the floated default, so it is NOT surfaced as a built-in card
    expect(html).not.toContain("Claude Opus 4.7")
  })

  it("floats nothing (and seeds no mock) when no ladder model is available", () => {
    const html = renderToStaticMarkup(
      <CopilotTab data={emptyRoles()} credentials={credentials()} modelGroups={[opusGroup("some-other-model", "Some Other Model")]} />,
    )
    expect(html).not.toContain('data-copilot-role-card="true"')
  })
})

describe("CopilotTab #61 model-group remove control", () => {
  it("renders an enabled group-level Remove button on a configured role", () => {
    const html = renderToStaticMarkup(
      <CopilotTab data={roles()} credentials={credentials()} modelGroups={registryModelGroups()} />,
    )
    const removeButton = html.match(/<button[^>]*data-copilot-model-group-remove="true"[^>]*>/)
    expect(removeButton).not.toBeNull()
    expect(removeButton?.[0]).not.toContain('disabled=""')
  })
})

describe("CopilotTab #63 searchable model-group combobox", () => {
  it("renders a combobox trigger (not a native select) on the empty draft card", () => {
    const html = renderToStaticMarkup(
      <CopilotTab data={rolesWithDraft()} credentials={credentials()} modelGroups={registryModelGroups()} />,
    )
    const trigger = html.match(/<button[^>]*data-copilot-model-group-select="true"[^>]*>/)
    expect(trigger).not.toBeNull()
    expect(trigger?.[0]).toContain('role="combobox"')
  })
})

describe("copilotGroupComboboxFilter — searchable picker matching (atom-63 ②)", () => {
  function previewRoute(providerLabel: string, providerModelId: string): CopilotRoutePreview {
    return {
      id: `${providerLabel}:${providerModelId}`,
      route_id: `${providerLabel}:${providerModelId}`,
      endpointId: providerLabel,
      providerLabel,
      providerKind: "third_party",
      providerModelId,
      uiState: "ready",
      agentStatus: "ready",
      capabilities: {},
      provider: providerLabel,
      modelId: providerModelId,
      methodId: null,
      note: null,
    }
  }
  const preview: CopilotRolePreview = {
    id: "claude-opus-4.8",
    title: "Claude Opus 4.8",
    description: "Claude Opus 4.8",
    source: "built_in",
    modelLabel: "Claude Opus 4.8",
    sdkId: "claude-agent-sdk",
    activeRouteIds: [],
    availableRoutes: [previewRoute("Qiniu Anthropic", "claude-opus-4-8")],
    routes: [],
  }
  const haystack = copilotGroupSearchValue(preview)

  it("requires every token to match (multi-token AND)", () => {
    expect(copilotGroupComboboxFilter(haystack, "claude opus")).toBe(1)
    expect(copilotGroupComboboxFilter(haystack, "claude gpt")).toBe(0)
  })

  it("matches compactly, ignoring separators", () => {
    expect(copilotGroupComboboxFilter(haystack, "opus-4.8")).toBe(1)
    expect(copilotGroupComboboxFilter(haystack, "opus4.8")).toBe(1)
  })

  it("searches canonical id, provider label and provider model id — not just the display name", () => {
    expect(copilotGroupComboboxFilter(haystack, "qiniu")).toBe(1) // provider label
    expect(copilotGroupComboboxFilter(haystack, "claude-opus-4-8")).toBe(1) // provider model id
  })

  it("shows every option for an empty query", () => {
    expect(copilotGroupComboboxFilter(haystack, "")).toBe(1)
  })
})
