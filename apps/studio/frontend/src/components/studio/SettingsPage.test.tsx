import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"
import type { RegistryResponse, RolesData } from "../../api/llm"
import { mergeEndpointTestResult } from "./settings/SettingsPage"
import { SettingsPageContent } from "./settings/SettingsPageContent"
import type { SettingsPageContentProps } from "./settings/types"

const registry: RegistryResponse = {
  provider_endpoints: {},
  provider_routes: {},
  runtime_policy: {
    provider_down_ttl_seconds: 300,
    probe_timeout_seconds: 30,
    token_escalation_rounds: 2,
  },
  model_profiles: {},
  roles: {},
  canonical_groups: [],
  lint_results: [],
}

const rolesData: RolesData = {
  schema_version: 2,
  model_profiles: {},
  roles: {},
}

function props(overrides: Partial<SettingsPageContentProps> = {}): SettingsPageContentProps {
  return {
    activeTab: "endpoints",
    registry,
    registryLoading: false,
    registryError: null,
    endpointSaveStatus: "idle",
    importDrafts: [],
    rolesData,
    rolesSaveStatus: "idle",
    rolesError: null,
    appSettings: {
      userId: "user",
      giteaHost: "http://localhost:3000",
      defaultSkillsDirectory: "/tmp/skills",
      isLoading: false,
      saveStatus: "idle",
      setUserId: () => undefined,
      setGiteaHost: () => undefined,
      setDefaultSkillsDirectory: () => undefined,
    },
    onClose: () => undefined,
    onTabChange: () => undefined,
    onAddEndpoint: () => undefined,
    onEndpointChange: () => undefined,
    onDeleteEndpoint: () => undefined,
    onTestEndpoint: () => undefined,
    onProbeRoute: () => undefined,
    onApplyDraft: () => undefined,
    onRolesDataChange: () => undefined,
    onProbeRole: () => undefined,
    onApplyProfile: () => undefined,
    ...overrides,
  }
}

describe("SettingsPageContent", () => {
  it("uses Endpoints navigation copy instead of API Keys", () => {
    const html = renderToStaticMarkup(<SettingsPageContent {...props()} />)

    expect(html).toContain("Endpoints")
    expect(html).not.toContain("API Keys")
  })

  it("renders the LLM Roles route/profile view", () => {
    const html = renderToStaticMarkup(<SettingsPageContent {...props({ activeTab: "llm_roles" })} />)

    expect(html).toContain("LLM Roles")
    expect(html).toContain("Available Routes")
    expect(html).toContain("Model Profiles")
  })
})

describe("mergeEndpointTestResult", () => {
  it("keeps local endpoint edits while applying backend-owned test fields", () => {
    const local = {
      endpoint_id: "openai-direct",
      display_name: "OpenAI Direct Manual",
      protocol: "openai_compatible" as const,
      base_url: "https://proxy.local/v1",
      api_key: "",
      status: "unverified_manual" as const,
      timeout_seconds: 60,
      trust_env: false,
      proxy_env: null,
      metadata: {},
    }
    const response = {
      ...local,
      display_name: "OpenAI Direct",
      base_url: "https://api.openai.com/v1",
      status: "failed" as const,
      last_test_at: "2026-05-25T00:00:00Z",
      last_test_message: "API key is empty.",
    }

    expect(mergeEndpointTestResult(local, response)).toMatchObject({
      display_name: "OpenAI Direct Manual",
      base_url: "https://proxy.local/v1",
      status: "failed",
      last_test_at: "2026-05-25T00:00:00Z",
      last_test_message: "API key is empty.",
    })
  })
})
