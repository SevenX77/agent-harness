import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it, vi } from "vitest"
import { CopilotTab, copilotBackendReadyCount } from "./CopilotTab"
import { agentStatusForRoute } from "./CopilotModelGroupCard"
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
