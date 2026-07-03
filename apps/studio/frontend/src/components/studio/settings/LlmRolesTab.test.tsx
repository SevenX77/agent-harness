import { renderToStaticMarkup } from "react-dom/server"
import { afterEach, describe, expect, it, vi } from "vitest"
import type { CredentialsState, ModelGroup, RolesData } from "../../../api/llm"
import { rolesDataToBackend } from "../../../api/llm"
import { roleChainStatusKey, type RoleChainStatusMap } from "../../../hooks/useRoleTestChainRunner"
import { AvailableModelDragPreview, LlmRolesTab, modelDropFailureMessage, roleIntentFromSettingsDraft, RoleSettingsFields } from "./LlmRolesTab"
import { formatThousands, stripThousands } from "./llm-roles/RoleSettingsDialog"
import {
  AvailableModelsSidebar,
  buildAvailableModelGroups,
  filterAvailableModelGroups,
} from "./llm-roles/AvailableModelsSidebar"
import { AdvancedModelBundlesSection, modelBundleGroupsFromData } from "./llm-roles/AdvancedModelBundlesSection"
import { ModelBundleCard } from "./llm-roles/ModelBundleCard"
import { buildRoleDeleteRequest, RoleCard } from "./llm-roles/RoleCard"
import { roleNameDisplayError, RoleNameDialog, RoleNameFields } from "./llm-roles/RoleNameDialog"
import { roleTestStatusesByRole, __resetRoleTestStoreForTests, __setRoleTestStoreForTests } from "./llm-roles/role-test-store"
import { appendAvailableModelToRole, appendModelGroupToRole, appendModelGroupToRoleWithResult, appendRole, attachBundleReferenceToRole, normalizeRolesDraft, ownedProviderCodesForModel, pruneInvalidRoleProviders, removeModelFromRole, removeProviderFromRole, removeRole, renameRole, reorderModelInRole, reorderProviderInRole, toggleModelFallback, validateRolesDraft } from "./role-utils"
import { credentialsByProviderCode } from "./route-credentials"

const toastMock = vi.hoisted(() => Object.assign(vi.fn(), {
  dismiss: vi.fn(),
  error: vi.fn(),
  success: vi.fn(),
}))

vi.mock("sonner", () => ({
  toast: toastMock,
}))

const credentials: CredentialsState = {
  providers: [
    {
      id: "anthropic",
      name: "Anthropic",
      api_key: "sk-anthropic",
      available_models: [
        { id: "claude-opus-4-1", capabilities: { thinking: true } },
      ],
    },
    {
      id: "openrouter",
      name: "OpenRouter",
      api_key: "sk-openrouter",
      base_url: "https://openrouter.ai/api/v1",
      available_models: [
        { id: "~anthropic/claude-opus-4-1", capabilities: { thinking: true } },
        { id: "~anthropic/claude-sonnet-latest" },
        { id: "~anthropic/claude-3.5-haiku" },
      ],
    },
    {
      id: "openai_proxy",
      name: "OpenAI Proxy",
      api_key: "",
      available_models: [
        { id: "gpt-5", capabilities: { thinking: true } },
        { id: "deepseek-chat" },
      ],
    },
    {
      id: "gemini-official",
      name: "Gemini Official",
      api_key: "sk-gemini",
      available_models: [
        { id: "gemini-3.1-pro-preview" },
      ],
    },
  ],
}

const modelGroups: ModelGroup[] = [
  {
    canonical_id: "claude-sonnet-4-7",
    display_name: "Claude Sonnet 4.7",
    provider_models: [
      {
        route_id: "anthropic-official:claude-sonnet-4-7",
        provider_label: "Anthropic Official",
        provider_kind: "official",
        provider_model_id: "claude-sonnet-4-7",
        ui_state: "ready",
        ui_detail: null,
        retry_at: null,
        reason_code: null,
        capability_state: "known",
        capabilities: {
          thinking: { value: true, source: "probed_verified" },
        },
      },
      {
        route_id: "qiniu-anthropic:claude-sonnet-4-7",
        provider_label: "Qiniu Anthropic",
        provider_kind: "third_party",
        provider_model_id: "claude-sonnet-4-7",
        ui_state: "untested",
        ui_detail: null,
        retry_at: null,
        reason_code: null,
        capability_state: "unknown",
        capabilities: {},
      },
      {
        route_id: "broken-proxy:claude-sonnet-4-7",
        provider_label: "Broken Proxy",
        provider_kind: "third_party",
        provider_model_id: "claude-sonnet-4-7",
        ui_state: "failed",
        ui_detail: "API key is missing.",
        retry_at: null,
        reason_code: "missing_key",
        capability_state: "unknown",
        capabilities: {},
      },
    ],
    status_summary: {
      ready: 1,
      untested: 1,
      cooling_down: 0,
      historical_ready: 0,
      failed: 1,
      off: 0,
    },
    capability_summary: {
      capability_known_count: 1,
      thinking: "mixed",
      tools: "unknown",
      structured_output: "unknown",
      max_context_tokens: null,
      max_output_tokens: null,
    },
  },
]

const rolesData: RolesData = {
  models: {
    CL46T: {
      name: "Claude Sonnet 4.6 Thinking",
      providers: { anthropic: "claude-sonnet-4.6", openai_proxy: "anthropic/claude-sonnet-4.6" },
    },
    DS32R: {
      name: "DeepSeek V4 Pro",
      providers: { openai_proxy: "deepseek-v4-pro" },
    },
    GPT5: {
      name: "GPT-5",
      providers: { openai_proxy: "gpt-5" },
    },
  },
  providers: {
    anthropic: { name: "Anthropic", type: "anthropic_compatible" },
    openai_proxy: { name: "OpenAI Proxy", type: "openai_compatible" },
  },
  roles: {
    copilot_chat: {
      model_fallback_enabled: true,
      active_model: "CL46T",
      models: {
        CL46T: { providers: ["anthropic"], temperature: 0.2, max_tokens: 8192 },
        DS32R: { providers: ["openai_proxy"], temperature: null, max_tokens: null },
      },
    },
  },
}

function renderRolesHtml(overrides: Partial<Parameters<typeof LlmRolesTab>[0]> = {}) {
  return renderToStaticMarkup(
    <LlmRolesTab
      data={rolesData}
      credentials={credentials}
      modelGroups={modelGroups}
      saveStatus="idle"
      error={null}
      onChange={vi.fn()}
      {...overrides}
    />,
  )
}

describe("LlmRolesTab controls", () => {
  it("updates the backend model fallback field when toggled", () => {
    const dataWithBackendField: RolesData = {
      ...rolesData,
      roles: {
        copilot_chat: {
          ...rolesData.roles.copilot_chat,
          model_fallback_enabled: true,
        },
      },
    }

    const next = toggleModelFallback(dataWithBackendField, "copilot_chat", false)

    expect(next.roles.copilot_chat.model_fallback_enabled).toBe(false)
    expect(dataWithBackendField.roles.copilot_chat.model_fallback_enabled).toBe(true)
  })

  it("renders Available Models from backend model group DTOs instead of credential model strings", () => {
    const html = renderToStaticMarkup(<AvailableModelsSidebar modelGroups={modelGroups} />)

    expect(html).toContain("Available Models")
    expect(html).toContain("Claude Sonnet 4.7")
    expect(html).toContain("Anthropic Official")
    expect(html).toContain("Qiniu Anthropic")
    expect(html).not.toContain("1 Ready")
    expect(html).not.toContain("1 Untested")
    expect(html).not.toContain("1 Needs Setup")
    expect(html).toContain('data-provider-state="ready"')
    expect(html).toContain('data-provider-state="untested"')
    expect(html).toContain('data-provider-state="failed"')
    expect(html).toContain('data-variant="default"')
    expect(html).not.toContain("claude-sonnet-4-7</")
    expect(html).not.toContain("anthropic-official:claude-sonnet-4-7")
    expect(html).not.toContain("route")
    expect(html).not.toContain("endpoint")
    expect(html).not.toContain("canonical")
  })

  it("omits Ready text from ready provider tags", () => {
    const html = renderToStaticMarkup(
      <AvailableModelsSidebar
        modelGroups={[{
          ...modelGroups[0],
          provider_models: [{
            ...modelGroups[0].provider_models[0],
            provider_label: "Ark Official",
            ui_state: "ready",
          }],
        }]}
      />,
    )
    const providerTag = html.match(/<span[^>]*data-available-model-provider-label="true"[\s\S]*?<\/span><\/span>/)?.[0] ?? ""

    expect(providerTag).toContain("Ark Official")
    expect(providerTag).toContain('data-provider-state="ready"')
    expect(providerTag).not.toContain("Ready")
  })

  it("adds a model group to a role using every exact backend route id", () => {
    const next = appendModelGroupToRole(rolesData, "copilot_chat", modelGroups[0])

    expect(next.models["claude-sonnet-4-7"]).toMatchObject({
      name: "Claude Sonnet 4.7",
      providers: {
        "anthropic-official:claude-sonnet-4-7": "claude-sonnet-4-7",
        "qiniu-anthropic:claude-sonnet-4-7": "claude-sonnet-4-7",
      },
    })
    expect(next.roles.copilot_chat.models["claude-sonnet-4-7"].providers).toEqual([
      "anthropic-official:claude-sonnet-4-7",
      "qiniu-anthropic:claude-sonnet-4-7",
      "broken-proxy:claude-sonnet-4-7",
    ])
    expect(next.providers["anthropic-official:claude-sonnet-4-7"].name).toBe("Anthropic Official")
    expect(validateRolesDraft(next)).toBeNull()
  })

  it("adds only the best route for each provider label when a model spans duplicate endpoints", () => {
    const duplicatedProviderGroup: ModelGroup = {
      ...modelGroups[0],
      canonical_id: "deepseek-v4-flash",
      display_name: "DeepSeek V4 Flash",
      provider_models: [
        {
          ...modelGroups[0].provider_models[1],
          route_id: "qiniu-openai:deepseek-v4-flash",
          endpoint_id: "qiniu-openai",
          provider_label: "Qiniu OpenAI",
          provider_model_id: "deepseek-v4-flash",
          ui_state: "ready",
        },
        {
          ...modelGroups[0].provider_models[1],
          route_id: "qiniu-anthropic:deepseek-v4-flash",
          endpoint_id: "qiniu-anthropic",
          provider_label: "Qiniu OpenAI",
          provider_model_id: "deepseek-v4-flash",
          ui_state: "untested",
        },
        {
          ...modelGroups[0].provider_models[0],
          route_id: "ark-official:deepseek-v4-flash",
          endpoint_id: "ark-official",
          provider_label: "Ark Official",
          provider_kind: "official",
          provider_model_id: "deepseek-v4-flash",
          ui_state: "untested",
        },
      ],
    }

    const next = appendModelGroupToRole(rolesData, "copilot_chat", duplicatedProviderGroup)

    expect(next.roles.copilot_chat.models["deepseek-v4-flash"].providers).toEqual([
      "qiniu-openai:deepseek-v4-flash",
      "ark-official:deepseek-v4-flash",
    ])
    expect(next.models["deepseek-v4-flash"].providers).not.toHaveProperty("qiniu-anthropic:deepseek-v4-flash")
  })

  it("returns a drop error when a model group has no provider routes", () => {
    const result = appendModelGroupToRoleWithResult(rolesData, "copilot_chat", {
      ...modelGroups[0],
      canonical_id: "empty-bundle",
      display_name: "Empty Bundle",
      provider_models: [],
    })

    expect(result.data).toBe(rolesData)
    expect(result.error).toBe("Could not add Empty Bundle to copilot_chat: no provider routes are available.")
  })

  it("formats model drop failures for Sonner", () => {
    expect(modelDropFailureMessage({
      modelId: "bundle:analyst_bundle",
      destination: "Analyst",
      reason: "source is no longer available",
    })).toBe("Could not add bundle:analyst_bundle to Analyst: source is no longer available.")
  })

  it("keeps route provider endpoint ownership when adding a model group", () => {
    const routeId = "deepseek-official:deepseek-v4-pro"
    const next = appendModelGroupToRole(
      rolesData,
      "copilot_chat",
      {
        ...modelGroups[0],
        canonical_id: "deepseek-v4-pro",
        display_name: "DeepSeek V4 Pro",
        provider_models: [
          {
            ...modelGroups[0].provider_models[0],
            route_id: routeId,
            endpoint_id: "deepseek-official",
            provider_label: "DeepSeek Official",
            provider_model_id: "deepseek-chat",
            ui_state: "ready",
          },
        ],
      },
    )

    expect(next.providers[routeId]).toMatchObject({
      name: "DeepSeek Official",
      type: "openai_compatible",
      endpoint_id: "deepseek-official",
    })
  })

  it("uses route endpoint credentials for route-backed provider ownership", () => {
    const routeId = "deepseek-official:deepseek-v4-pro"
    const routeBackedData: RolesData = {
      models: {
        "deepseek-v4-pro": {
          name: "DeepSeek V4 Pro",
          providers: { [routeId]: "deepseek-chat" },
        },
      },
      providers: {
        [routeId]: {
          name: "DeepSeek Official",
          type: "openai_compatible",
          endpoint_id: "deepseek-official",
        },
      },
      roles: {
        analyst: {
          model_fallback_enabled: true,
          active_model: "deepseek-v4-pro",
          models: {
            "deepseek-v4-pro": { providers: [routeId], temperature: null, max_tokens: null },
          },
        },
      },
    }
    const html = renderRolesHtml({
      data: routeBackedData,
      credentials: {
        providers: [
          {
            id: "deepseek-official",
            name: "DeepSeek Official",
            api_key: "sk-deepseek",
            provider_type: "openai_compatible",
            last_test_status: "ok",
          },
        ],
      },
    })

    expect(html).toContain("DeepSeek Official")
    expect(html).not.toContain("Connected")
    expect(html).not.toContain("Unavailable")
  })

  it("does not scan credential model lists for route-backed provider ownership", () => {
    const routeId = "deepseek-official:deepseek-v4-flash"
    const routeBackedData: RolesData = {
      models: {
        "deepseek-v4-flash": {
          name: "DeepSeek V4 Flash",
          providers: { [routeId]: "deepseek-v4-flash" },
        },
      },
      providers: {
        [routeId]: {
          name: "DeepSeek Official",
          type: "openai_compatible",
          endpoint_id: "deepseek-official",
        },
      },
      roles: {
        analyst: {
          model_fallback_enabled: true,
          active_model: "deepseek-v4-flash",
          models: {
            "deepseek-v4-flash": { providers: [routeId], temperature: null, max_tokens: null },
          },
        },
      },
    }
    const routeCredential = {
      id: "deepseek-official",
      name: "DeepSeek Official",
      api_key: "sk-deepseek",
      provider_type: "openai_compatible",
    } as CredentialsState["providers"][number]
    Object.defineProperty(routeCredential, "available_models", {
      get() {
        throw new Error("route-backed ownership should not scan available_models")
      },
    })

    expect(ownedProviderCodesForModel(routeBackedData, "deepseek-v4-flash", {
      [routeId]: routeCredential,
      "deepseek-official": routeCredential,
    })).toEqual([routeId])
  })

  it("uses provider row border state and a status light instead of text badges", () => {
    const modelCode = "gpt-5-4-mini"
    const routeBackedData: RolesData = {
      models: {
        [modelCode]: {
          name: "GPT 5.4 Mini",
          providers: {
            "openrouter:gpt-5-4-mini": "openai/gpt-5.4-mini",
          },
        },
      },
      providers: {
        "openrouter:gpt-5-4-mini": {
          name: "OpenRouter",
          type: "openai_compatible",
          endpoint_id: "openrouter",
        },
      },
      roles: {
        Analyst: {
          model_fallback_enabled: true,
          active_model: modelCode,
          models: {
            [modelCode]: { providers: ["openrouter:gpt-5-4-mini"], temperature: null, max_tokens: null },
          },
        },
      },
    }
    const html = renderToStaticMarkup(
      <RoleCard
        data={routeBackedData}
        category="graph-agent"
        credentialsByCode={credentialsByProviderCode(routeBackedData, {
          providers: [{
            id: "openrouter",
            name: "OpenRouter",
            api_key: "sk-openrouter",
            provider_type: "openai_compatible",
            last_test_status: "ok",
          }],
        })}
        modelDisplayNamesByCode={new Map([[modelCode, "GPT 5.4 Mini"]])}
        ownedProviderCodesByModel={new Map([[modelCode, new Set(["openrouter:gpt-5-4-mini"])]])}
        roleName="Analyst"
        testStatuses={{
          [roleChainStatusKey(modelCode, "openrouter:gpt-5-4-mini")]: { status: "ok", message: "Connected" },
        }}
        testChainRunning={false}
        onRunTestChain={vi.fn()}
        getActiveAvailableModelDragId={() => null}
        getAvailableModelGroup={() => null}
        onChange={vi.fn()}
        onDeleteRole={vi.fn()}
      />,
    )

    const providerCardTag = html.match(/<[^>]*data-provider-card="true"[^>]*>/)?.[0] ?? ""
    const providerCardClass = providerCardTag.match(/class="([^"]*)"/)?.[1] ?? ""
    const statusLightClass = html.match(/data-role-route-status-light="true"[^>]*class="([^"]*)"/)?.[1]
    expect(html).toContain('data-provider-test-status="ok"')
    expect(html).toContain('data-provider-row-status-tooltip="true"')
    expect(html).toContain('data-role-route-status-light="true"')
    expect(html).toContain('aria-label="Role route status Can Run')
    expect(html).not.toContain("This route can run in this role")
    expect(html).not.toMatch(/>Can Run<\/span>|>Limited<\/span>|>Blocked<\/span>/)
    expect(providerCardClass).toContain("border-success-border")
    expect(statusLightClass).toContain("size-1.5")
    expect(statusLightClass).not.toContain("size-2.5")
    expect(providerCardClass).not.toContain("bg-success-background/10")
    expect(providerCardClass).not.toContain("bg-destructive-background/10")
    expect(providerCardClass).not.toContain("bg-primary/5")
    expect(html).not.toMatch(/aria-label="Provider test status Connected"[^>]*>.*Connected<\/span>/)
  })

  it("lets current provider test failures override stale endpoint success for the model badge", () => {
    const modelCode = "gpt-5-4-mini"
    const routeBackedData: RolesData = {
      models: {
        [modelCode]: {
          name: "GPT 5.4 Mini",
          providers: {
            "openrouter:gpt-5-4-mini": "openai/gpt-5.4-mini",
            "openai-official:gpt-5-4-mini": "gpt-5.4-mini",
          },
        },
      },
      providers: {
        "openrouter:gpt-5-4-mini": {
          name: "OpenRouter",
          type: "openai_compatible",
          endpoint_id: "openrouter",
        },
        "openai-official:gpt-5-4-mini": {
          name: "OpenAI Official",
          type: "openai_compatible",
          endpoint_id: "openai-official",
        },
      },
      roles: {
        Analyst: {
          model_fallback_enabled: true,
          active_model: modelCode,
          models: {
            [modelCode]: {
              providers: ["openrouter:gpt-5-4-mini", "openai-official:gpt-5-4-mini"],
              temperature: null,
              max_tokens: null,
            },
          },
        },
      },
    }
    const routeCredentials: CredentialsState = {
      providers: [
        {
          id: "openrouter",
          name: "OpenRouter",
          api_key: "sk-openrouter",
          provider_type: "openai_compatible",
          last_test_status: "ok",
        },
        {
          id: "openai-official",
          name: "OpenAI Official",
          api_key: "sk-openai",
          provider_type: "openai_compatible",
          last_test_status: "ok",
        },
      ],
    }
    const html = renderToStaticMarkup(
      <RoleCard
        data={routeBackedData}
        category="graph-agent"
        credentialsByCode={credentialsByProviderCode(routeBackedData, routeCredentials)}
        modelDisplayNamesByCode={new Map([[modelCode, "GPT 5.4 Mini"]])}
        ownedProviderCodesByModel={new Map(Object.keys(routeBackedData.models).map((modelCode) => [
          modelCode,
          new Set(Object.keys(routeBackedData.models[modelCode].providers)),
        ]))}
        roleName="Analyst"
        testStatuses={{
          [roleChainStatusKey(modelCode, "openrouter:gpt-5-4-mini")]: { status: "network_error", message: "Network error" },
          [roleChainStatusKey(modelCode, "openai-official:gpt-5-4-mini")]: { status: "timeout", message: "Timed out" },
        }}
        testChainRunning={false}
        onRunTestChain={vi.fn()}
        getActiveAvailableModelDragId={() => null}
        getAvailableModelGroup={() => null}
        onChange={vi.fn()}
        onDeleteRole={vi.fn()}
      />,
    )

    expect(html).not.toContain('aria-label="Provider status Failed"')
    expect(html).not.toContain(">Failed</")
    expect(html).toContain('aria-label="Role route status Blocked')
    expect(html).toContain('data-role-route-status="blocked"')
    expect(html).not.toContain('aria-label="Provider status Connected"')
  })

  it("adds every backend provider route from the model group in ready-first order", () => {
    const modelGroup: ModelGroup = {
      ...modelGroups[0],
      canonical_id: "gpt-5",
      display_name: "GPT 5",
      provider_models: [
        {
          ...modelGroups[0].provider_models[0],
          route_id: "cooldown:gpt-5",
          provider_label: "Cooling Provider",
          provider_kind: "official",
          provider_model_id: "gpt-5",
          ui_state: "cooling_down",
        },
        {
          ...modelGroups[0].provider_models[0],
          route_id: "off:gpt-5",
          provider_label: "Off Provider",
          provider_kind: "official",
          provider_model_id: "gpt-5",
          ui_state: "off",
        },
        {
          ...modelGroups[0].provider_models[0],
          route_id: "ready:gpt-5",
          provider_label: "Ready Provider",
          provider_kind: "third_party",
          provider_model_id: "gpt-5",
          ui_state: "ready",
        },
        {
          ...modelGroups[0].provider_models[0],
          route_id: "untested:gpt-5",
          provider_label: "Untested Provider",
          provider_kind: "third_party",
          provider_model_id: "gpt-5",
          ui_state: "untested",
        },
      ],
    }

    const next = appendModelGroupToRole(rolesData, "copilot_chat", modelGroup)

    expect(next.roles.copilot_chat.models["gpt-5"].providers).toEqual([
      "ready:gpt-5",
      "untested:gpt-5",
      "cooldown:gpt-5",
      "off:gpt-5",
    ])
  })

  it("keeps setup-needed routes when adding a model group so users can see and remove them", () => {
    const modelGroup: ModelGroup = {
      ...modelGroups[0],
      canonical_id: "deepseek-v3",
      display_name: "DeepSeek V3",
      provider_models: [
        {
          ...modelGroups[0].provider_models[0],
          route_id: "cooldown:deepseek-v3",
          provider_label: "Cooling Provider",
          provider_kind: "third_party",
          provider_model_id: "deepseek-v3",
          ui_state: "cooling_down",
        },
        {
          ...modelGroups[0].provider_models[0],
          route_id: "needs-setup:deepseek-v3",
          provider_label: "Needs Setup Provider",
          provider_kind: "official",
          provider_model_id: "deepseek-v3",
          ui_state: "failed",
        },
      ],
    }

    const next = appendModelGroupToRole(rolesData, "copilot_chat", modelGroup)

    expect(next.roles.copilot_chat.models["deepseek-v3"].providers).toEqual([
      "cooldown:deepseek-v3",
      "needs-setup:deepseek-v3",
    ])
  })

  it("uses skeleton placeholders while roles are loading", () => {
    const html = renderRolesHtml({ data: null })
    const skeletons = html.match(/data-slot="skeleton"/g) ?? []

    expect(skeletons.length).toBeGreaterThan(3)
    expect(html).not.toContain("Loading roles...")
  })

  it("uses shadcn switch primitives and auto-save status instead of manual Save", () => {
    const html = renderRolesHtml({ saveStatus: "pending" })

    expect(html).toContain("Pending")
    expect(html).toContain('data-slot="switch"')
    expect(html).not.toContain('data-slot="checkbox"')
    expect(html).not.toContain(">Save</button>")
    expect(html).not.toContain("Dirty")
  })

  it("renders roles as flat cards with add controls instead of top role tabs", () => {
    const html = renderRolesHtml()

    expect(html).toContain('data-slot="card"')
    expect(html).toContain("Add Graph Agent Role")
    expect(html).not.toContain("Add Copilot Role")
    expect(html).toContain('data-role-add-trigger="true"')
    expect(html).toContain('data-slot="empty"')
    expect(html).toContain("Drop model")
    expect(html).toContain("Add provider")
    expect(html).not.toContain('aria-label="LLM roles"')
    expect(html).not.toContain('aria-label="Add model to role"')
  })

  it("renders the model library as an unframed searchable scroll area", () => {
    const html = renderToStaticMarkup(<AvailableModelsSidebar modelGroups={modelGroups} />)

    expect(html).toContain("Available Models")
    expect(html).toContain('data-available-model-count="true"')
    expect(html).toContain('aria-label="1 available model"')
    expect(html).toContain('data-slot="input-group"')
    expect(html).toContain('data-slot="input-group-control"')
    expect(html).toContain('aria-label="Search available models"')
    expect(html).toContain('aria-label="Clear model search"')
    expect(html).toContain('data-slot="scroll-area"')
    expect(html).toContain("[&amp;_[data-slot=scroll-area-scrollbar]]:hidden")
    expect(html).not.toContain('data-slot="card"')
    expect(html).not.toContain("Reference library. Add models from each role card.")
  })

  it("uses the shared card surface with background hover and selected ring treatment", () => {
    const html = renderToStaticMarkup(<AvailableModelsSidebar modelGroups={modelGroups} />)

    expect(html).toContain("bg-card")
    expect(html).toContain("border border-border")
    expect(html).toContain("bg-muted/20")
    expect(html).toContain("shadow-xs")
    expect(html).toContain("ring-inset")
    expect(html).toContain("hover:bg-muted/35")
    expect(html).toContain("active:scale-[0.99]")
    expect(html).toContain("active:bg-muted/45")
    expect(html).toContain("transition-[background-color,box-shadow,transform]")
    expect(html).toContain("data-[selected=true]:bg-muted/40")
    expect(html).toContain("data-[selected=true]:ring-2")
    expect(html).toContain("data-[selected=true]:ring-primary/70")
    expect(html).toContain("focus-visible:ring-2")
    expect(html).not.toContain("hover:ring-2")
    expect(html).not.toContain("hover:ring-primary/70")
    expect(html).not.toContain("bg-primary/10")
    expect(html).not.toContain("border-primary")
  })

  it("renders thinking as a small brain badge with adaptive text", () => {
    const html = renderToStaticMarkup(<AvailableModelsSidebar modelGroups={modelGroups} />)

    expect(html).toContain('aria-label="Thinking capable"')
    expect(html).toContain('data-thinking-badge="true"')
    expect(html).toContain("Thinking")
    expect(html).toContain("text-[9px]")
    expect(html).toContain("hidden xl:inline")
    expect(html).not.toContain("BrainCircuit")
  })

  it("makes available model cards pointer-draggable for role drop targets", () => {
    const html = renderToStaticMarkup(<AvailableModelsSidebar modelGroups={modelGroups} />)

    expect(html).toContain('data-available-model-drag-source="true"')
    expect(html).toContain('data-available-model-pointer-drag-source="true"')
    expect(html).toContain('data-available-model-native-dnd="off"')
  })

  it("renders a pointer drag preview for available model drops", () => {
    const html = renderToStaticMarkup(
      <AvailableModelDragPreview
        nodeRef={{ current: null }}
        drag={{
          dragging: true,
          modelId: "anthropic/claude-opus-4.7",
          label: "Claude Opus 4.7",
          x: 120,
          y: 240,
        }}
      />,
    )

    expect(html).toContain('data-available-model-drag-preview="true"')
    expect(html).toContain('data-preview-update-mode="imperative-transform"')
    expect(html).toContain("Claude Opus 4.7")
    expect(html).toContain("translate3d(120px, 240px, 0)")
    expect(html).toContain("pointer-events-none")
    expect(html).toContain("ring-primary/40")
  })

  it("renders provider labels as tags without native model/provider title tooltips", () => {
    const html = renderToStaticMarkup(<AvailableModelsSidebar modelGroups={modelGroups} />)

    expect(html).toContain('data-available-model-provider-label="true"')
    expect(html).toContain('data-slot="tag"')
    expect(html).toContain('data-variant="success"')
    expect(html).toContain("border-success")
    expect(html).toContain("bg-success/10")
    expect(html).toContain('data-variant="destructive"')
    expect(html).toContain("border-destructive")
    expect(html).toContain("Qiniu Anthropic")
    expect(html).not.toContain('title="Qiniu Anthropic"')
    expect(html).not.toContain('title="Claude Sonnet 4.7"')
  })

  it("maps backend provider state and role fit into three role route statuses", () => {
    const retryAt = "2026-12-31T00:00:00Z"
    const statefulModelGroups: ModelGroup[] = [{
      canonical_id: "gpt-5",
      display_name: "GPT 5",
      section_label: "openai",
      provider_models: [
        {
          route_id: "ready:gpt-5",
          endpoint_id: "ready",
          provider_label: "Ready Provider",
          provider_kind: "official",
          provider_model_id: "gpt-5",
          ui_state: "ready",
          ui_detail: "Ready for generation.",
          retry_at: null,
          reason_code: null,
          capability_state: "known",
          capabilities: {},
        },
        {
          route_id: "untested:gpt-5",
          endpoint_id: "untested",
          provider_label: "Untested Provider",
          provider_kind: "third_party",
          provider_model_id: "gpt-5",
          ui_state: "untested",
          ui_detail: null,
          retry_at: null,
          reason_code: null,
          capability_state: "unknown",
          capabilities: {},
        },
        {
          route_id: "cooling:gpt-5",
          endpoint_id: "cooling",
          provider_label: "Cooling Provider",
          provider_kind: "third_party",
          provider_model_id: "gpt-5",
          ui_state: "cooling_down",
          ui_detail: "Retry after transient rate limit.",
          retry_at: retryAt,
          reason_code: "rate_limited",
          capability_state: "partial",
          capabilities: {},
        },
        {
          route_id: "setup:gpt-5",
          endpoint_id: "setup",
          provider_label: "Setup Provider",
          provider_kind: "custom",
          provider_model_id: "gpt-5",
          ui_state: "failed",
          ui_detail: "Model does not exist.",
          retry_at: null,
          reason_code: "invalid_model",
          capability_state: "unknown",
          capabilities: {},
        },
        {
          route_id: "off:gpt-5",
          endpoint_id: "off",
          provider_label: "Off Provider",
          provider_kind: "custom",
          provider_model_id: "gpt-5",
          ui_state: "off",
          ui_detail: "Disabled by user.",
          retry_at: null,
          reason_code: "user_disabled",
          capability_state: "unknown",
          capabilities: {},
        },
      ],
      status_summary: {
        ready: 1,
        untested: 1,
        cooling_down: 1,
        historical_ready: 0,
        failed: 1,
        off: 1,
      },
      capability_summary: {
        capability_known_count: 1,
        thinking: "unknown",
        tools: "unknown",
        structured_output: "unknown",
        max_context_tokens: null,
        max_output_tokens: null,
      },
    }]
    const statefulData: RolesData = {
      models: {
        "gpt-5": {
          name: "GPT 5",
          providers: Object.fromEntries(statefulModelGroups[0].provider_models.map((provider) => [
            provider.route_id,
            provider.provider_model_id,
          ])),
        },
      },
      providers: Object.fromEntries(statefulModelGroups[0].provider_models.map((provider) => [
        provider.route_id,
        {
          name: provider.provider_label,
          type: "openai_compatible",
          endpoint_id: provider.endpoint_id,
        },
      ])),
      roles: {
        analyst: {
          model_fallback_enabled: true,
          active_model: "gpt-5",
          models: {
            "gpt-5": {
              providers: statefulModelGroups[0].provider_models.map((provider) => provider.route_id),
              temperature: null,
              max_tokens: null,
            },
          },
          materialization_report: {
            entries: [
              { canonical_id: "gpt-5", route_id: "ready:gpt-5", role_fit: "using" },
              {
                canonical_id: "gpt-5",
                route_id: "untested:gpt-5",
                role_fit: "downgraded",
                warnings: [{ message: "Using lower max output." }],
              },
              {
                canonical_id: "gpt-5",
                route_id: "cooling:gpt-5",
                role_fit: "needs_test",
                warnings: [{ code: "thinking_capability_unknown" }],
              },
              { canonical_id: "gpt-5", route_id: "setup:gpt-5", role_fit: "not_fit" },
            ],
            warnings: [],
            skipped_provider_details: [],
          },
        },
      },
    }
    const html = renderRolesHtml({
      data: statefulData,
      modelGroups: statefulModelGroups,
      credentials: {
        providers: statefulModelGroups[0].provider_models.map((provider) => ({
          id: provider.endpoint_id ?? provider.route_id.split(":")[0],
          name: provider.provider_label,
          api_key: "sk-test",
          provider_type: "openai_compatible",
          last_test_status: "ok",
        })),
      },
    })

    expect(html).toContain('aria-label="Role route status Can Run')
    expect(html).toContain('aria-label="Role route status Limited')
    expect(html).toContain('aria-label="Role route status Blocked')
    expect(html).toContain('data-role-route-status="runnable"')
    expect(html).toContain('data-role-route-status="limited"')
    expect(html).toContain('data-role-route-status="blocked"')
    expect(html).toContain("Using lower max output.")
    expect(html).toContain("Thinking is required but capability is unknown.")
    expect(html).toContain("Cooling Down: Retry after transient rate limit.")
    expect(html).not.toMatch(/>Can Run<\/span>|>Limited<\/span>|>Blocked<\/span>/)
    expect(html).not.toContain('aria-label="Provider state Ready"')
    expect(html).not.toContain('aria-label="Role fit Using"')
    expect(html).not.toContain('data-cooling-down-countdown="true"')
    expect(html).not.toContain("Test Now")
    expect(html).not.toContain(">rate_limited<")
    expect(html).not.toContain(">invalid_model<")
    expect(html).not.toContain(">user_disabled<")
  })

  it("uses only active provider progress statuses while a persisted role test is running", () => {
    // A running role projects its live activeStatuses (from the polled backend job),
    // not the statuses derived from any prior result still on the state.
    expect(roleTestStatusesByRole({
      copilot_chat: {
        running: true,
        activeStatuses: {
          [roleChainStatusKey("CL46T", "anthropic")]: { status: "testing" },
        },
        result: {
          role_name: "copilot_chat",
          status: "warning",
          warnings: [],
          model_groups: [{
            canonical_id: "CL46T",
            display_name: "Claude Sonnet 4.6 Thinking",
            provider_results: [
              {
                route_id: "anthropic",
                provider_label: "Anthropic",
                provider_ui_state: "ready",
                role_fit: "using",
                admission_decision: "admit",
                status: "ok",
                warnings: [],
                retry_at: null,
                message: null,
                resolved_settings: {},
              },
              {
                route_id: "openai_proxy",
                provider_label: "OpenAI Proxy",
                provider_ui_state: "ready",
                role_fit: "using",
                admission_decision: "admit",
                status: "ok",
                warnings: [],
                retry_at: null,
                message: null,
                resolved_settings: {},
              },
            ],
          }],
        },
      },
    })).toEqual({
      copilot_chat: {
        [roleChainStatusKey("CL46T", "anthropic")]: { status: "testing" },
      },
    })
  })

  it("keeps testing provider rows on the border-flow status path", () => {
    const modelCode = "gpt-5-4-mini"
    const routeId = "openrouter:gpt-5-4-mini"
    const routeBackedData: RolesData = {
      models: {
        [modelCode]: {
          name: "GPT 5.4 Mini",
          providers: {
            [routeId]: "openai/gpt-5.4-mini",
          },
        },
      },
      providers: {
        [routeId]: {
          name: "OpenRouter",
          type: "openai_compatible",
          endpoint_id: "openrouter",
        },
      },
      roles: {
        Analyst: {
          model_fallback_enabled: true,
          active_model: modelCode,
          models: {
            [modelCode]: { providers: [routeId], temperature: null, max_tokens: null },
          },
        },
      },
    }
    const html = renderToStaticMarkup(
      <RoleCard
        data={routeBackedData}
        category="graph-agent"
        credentialsByCode={{}}
        modelDisplayNamesByCode={new Map([[modelCode, "GPT 5.4 Mini"]])}
        ownedProviderCodesByModel={new Map([[modelCode, new Set([routeId])]])}
        roleName="Analyst"
        testStatuses={{
          [roleChainStatusKey(modelCode, routeId)]: { status: "testing" },
        }}
        testChainRunning={true}
        onRunTestChain={vi.fn()}
        getActiveAvailableModelDragId={() => null}
        getAvailableModelGroup={() => null}
        onChange={vi.fn()}
        onDeleteRole={vi.fn()}
      />,
    )

    const providerCardTag = html.match(/<[^>]*data-provider-card="true"[^>]*>/)?.[0] ?? ""
    expect(providerCardTag).toContain('data-provider-test-status="testing"')
    expect(providerCardTag).toContain('data-role-route-status="testing"')
    expect(providerCardTag).toContain("relative")
  })

  it("renders the LLM role Test trigger with the flask icon", () => {
    const html = renderToStaticMarkup(
      <RoleCard
        data={rolesData}
        category="graph-agent"
        credentialsByCode={credentialsByProviderCode(rolesData, { providers: credentials.providers })}
        modelDisplayNamesByCode={new Map([["CL46T", "Claude Sonnet 4.6 Thinking"]])}
        ownedProviderCodesByModel={new Map([["CL46T", new Set(["anthropic"])]])}
        roleName="copilot_chat"
        testStatuses={{}}
        testChainRunning={false}
        onRunTestChain={vi.fn()}
        getActiveAvailableModelDragId={() => null}
        getAvailableModelGroup={() => null}
        onChange={vi.fn()}
        onDeleteRole={vi.fn()}
      />,
    )

    expect(html).toContain('data-role-test-trigger="true"')
    expect(html).toContain('data-role-test-icon="true"')
    expect(html).toContain('data-variant="default"')
    expect(html).toContain('>Test</button>')
  })

  it("does not render persisted role test reports inside the role card", () => {
    const html = renderToStaticMarkup(
      <RoleCard
        data={rolesData}
        category="copilot"
        credentialsByCode={credentialsByProviderCode(rolesData, { providers: credentials.providers })}
        modelDisplayNamesByCode={new Map([["CL46T", "Claude Sonnet 4.6 Thinking"]])}
        ownedProviderCodesByModel={new Map([["CL46T", new Set(["anthropic"])], ["DS32R", new Set(["openai_proxy"])]])}
        roleName="copilot_chat"
        testStatuses={{}}
        testChainRunning={false}
        roleTestResult={{
          role_name: "copilot_chat",
          status: "warning",
          warnings: [{ message: "Thinking is required but capability is unknown." }],
          model_groups: [{
            canonical_id: "CL46T",
            display_name: "Claude Sonnet 4.6 Thinking",
            provider_results: [{
              route_id: "anthropic",
              provider_label: "Anthropic",
              provider_ui_state: "ready",
              role_fit: "needs_test",
              admission_decision: "admit",
              status: "ok",
              warnings: [{ message: "Thinking is required but capability is unknown." }],
              retry_at: null,
              message: "Passed.",
              resolved_settings: {},
            }],
          }],
        }}
        onRunTestChain={vi.fn()}
        getActiveAvailableModelDragId={() => null}
        getAvailableModelGroup={() => null}
        onChange={vi.fn()}
        onDeleteRole={vi.fn()}
      />,
    )

    expect(html).not.toContain('data-role-test-result="true"')
    expect(html).not.toContain("Role Test")
    expect(html).not.toContain("Needs Attention")
  })

  it("renders model group titles in the normal UI font", () => {
    const html = renderToStaticMarkup(<AvailableModelsSidebar modelGroups={modelGroups} />)

    expect(html).toContain('data-available-model-title="true"')
    expect(html).toContain("font-medium")
    expect(html).not.toContain("font-mono")
  })

  it("uses a readable overflow count instead of truncating every provider label", () => {
    const manyProviderModelGroups: ModelGroup[] = [{
      ...modelGroups[0],
      provider_models: ["OpenRouter", "QiNiu-Anthropic", "QiNiu-DeepSeek", "team-a", "team-b"].map((name, index) => ({
        ...modelGroups[0].provider_models[0],
        route_id: `provider-${index}:deepseek-r1`,
        provider_label: name,
      })),
      status_summary: {
        ready: 5,
        untested: 0,
        cooling_down: 0,
        historical_ready: 0,
        failed: 0,
        off: 0,
      },
    }]
    const html = renderToStaticMarkup(<AvailableModelsSidebar modelGroups={manyProviderModelGroups} />)

    expect(html).toContain("OpenRouter")
    expect(html).toContain("QiNiu-Anthropic")
    expect(html).toContain("+3")
    expect(html).not.toContain("shrink truncate")
    expect(html).not.toContain("Ope...")
  })

  it("builds the model library from backend model groups instead of role abbreviations", () => {
    const groups = buildAvailableModelGroups(modelGroups)
    const allModels = groups.flatMap((group) => group.models)
    const html = renderToStaticMarkup(<AvailableModelsSidebar modelGroups={modelGroups} />)

    expect(allModels.map((model) => model.id)).toEqual(["claude-sonnet-4-7"])
    expect(groups.map((group) => group.section)).toEqual(["anthropic"])
    expect(allModels[0].providers.map((provider) => provider.label)).toEqual([
      "Anthropic Official",
      "Qiniu Anthropic",
      "Broken Proxy",
    ])
    expect(allModels[0].thinking).toBe(true)
    expect(html).toContain("Claude Sonnet 4.7")
    expect(html).toContain("Anthropic Official")
    expect(html).toContain('aria-label="Thinking capable"')
    expect(html).not.toContain("provider_routes")
    expect(html).not.toContain("GPT5")
    expect(html).not.toContain("Claude Sonnet 4.6 Thinking")
  })

  it("collapses duplicate endpoint routes to one provider label in the model library", () => {
    const duplicateEndpointGroups: ModelGroup[] = [{
      ...modelGroups[0],
      canonical_id: "deepseek-v4-flash",
      display_name: "DeepSeek V4 Flash",
      section_label: "deepseek",
      provider_models: [
        {
          ...modelGroups[0].provider_models[1],
          route_id: "qiniu-openai:deepseek-v4-flash",
          endpoint_id: "qiniu-openai",
          provider_label: "Qiniu OpenAI",
          provider_model_id: "deepseek-v4-flash",
          ui_state: "ready",
        },
        {
          ...modelGroups[0].provider_models[1],
          route_id: "qiniu-anthropic:deepseek-v4-flash",
          endpoint_id: "qiniu-anthropic",
          provider_label: "Qiniu OpenAI",
          provider_model_id: "deepseek-v4-flash",
          ui_state: "untested",
        },
        {
          ...modelGroups[0].provider_models[1],
          route_id: "ark-official:deepseek-v4-flash",
          endpoint_id: "ark-official",
          provider_label: "Ark Official",
          provider_kind: "official",
          provider_model_id: "deepseek-v4-flash",
          ui_state: "untested",
        },
      ],
    }]

    const [entry] = buildAvailableModelGroups(duplicateEndpointGroups)[0].models

    expect(entry.providers.map((provider) => `${provider.label}:${provider.state}:${provider.id}`)).toEqual([
      "Qiniu OpenAI:ready:qiniu-openai:deepseek-v4-flash",
      "Ark Official:untested:ark-official:deepseek-v4-flash",
    ])
  })

  it("pins advanced model bundles above normal Available Models and keeps exact route ids", () => {
    const bundledData: RolesData = {
      ...rolesData,
      model_bundles: {
        premium_stack: {
          model_profile_id: "premium_stack",
          display_name: "Premium Stack",
          canonical_id: "bundle:premium_stack",
          fallback_chain: [
            { route_id: "anthropic-official:claude-sonnet-4-7" },
            { route_id: "qiniu-anthropic:claude-sonnet-4-7" },
          ],
        },
      },
    }
    const providerModelsByRouteId = new Map(modelGroups[0].provider_models.map((providerModel) => [
      providerModel.route_id,
      providerModel,
    ]))
    const bundleGroups = modelBundleGroupsFromData(bundledData, providerModelsByRouteId)
    const html = renderToStaticMarkup(
      <AvailableModelsSidebar
        modelGroups={modelGroups}
        pinnedModelGroups={bundleGroups}
      />,
    )

    expect(bundleGroups[0]).toMatchObject({
      canonical_id: "bundle:premium_stack",
      display_name: "Premium Stack",
    })
    expect(bundleGroups[0].provider_models.map((providerModel) => providerModel.route_id)).toEqual([
      "anthropic-official:claude-sonnet-4-7",
      "qiniu-anthropic:claude-sonnet-4-7",
    ])
    expect(html.indexOf("Advanced Model Bundles")).toBeLessThan(html.indexOf("anthropic"))
    expect(html).toContain("Premium Stack")
    expect(html).toContain("Claude Sonnet 4.7")
    expect(html).not.toContain("model_profiles")
  })

  it("renders an advanced bundle authoring surface below role sections", () => {
    const bundledData: RolesData = {
      ...rolesData,
      models: {
        ...rolesData.models,
        "claude-sonnet-4-7": {
          name: "Claude Sonnet 4.7",
          providers: {
            "anthropic-official:claude-sonnet-4-7": "claude-sonnet-4-7",
          },
        },
      },
      providers: {
        ...rolesData.providers,
        "anthropic-official:claude-sonnet-4-7": {
          name: "Anthropic Official",
          type: "anthropic_compatible",
          endpoint_id: "anthropic-official",
        },
      },
      model_bundles: {
        premium_stack: {
          model_profile_id: "premium_stack",
          display_name: "Premium Stack",
          canonical_id: "bundle:premium_stack",
          model_fallback_enabled: true,
          intent: { provider_preference: "manual_order" },
          model_groups: [{
            canonical_id: "claude-sonnet-4-7",
            display_name: "Claude Sonnet 4.7",
            provider_models: [{ route_id: "anthropic-official:claude-sonnet-4-7" }],
          }],
          fallback_chain: [{ route_id: "anthropic-official:claude-sonnet-4-7" }],
        },
      },
    }
    const html = renderToStaticMarkup(
      <AdvancedModelBundlesSection
        data={bundledData}
        credentialsByCode={credentialsByProviderCode(bundledData, { providers: credentials.providers })}
        modelDisplayNamesByCode={new Map([["claude-sonnet-4-7", "Claude Sonnet 4.7"]])}
        modelGroups={modelGroups}
        providerModelsByRouteId={new Map(modelGroups[0].provider_models.map((providerModel) => [
          providerModel.route_id,
          providerModel,
        ]))}
        getActiveAvailableModelDragId={() => null}
        onChange={vi.fn()}
        onDeleteBundle={vi.fn()}
      />,
    )

    expect(html).toContain("Model Bundles")
    expect(html).toContain("Premium Stack")
    expect(html).toContain("Add Model Bundle")
    expect(html).toContain("Anthropic Official")
    expect(html).toContain('data-slot="card"')
    expect(html).toContain('data-slot="item"')
    expect(html).toContain('data-model-bundle-card="true"')
    expect(html).not.toContain('data-model-bundle-row="true"')
    expect(html).not.toContain("model_profiles")
  })

  it("sorts ready provider routes before untested and setup routes in model cards", () => {
    const unsortedModelGroups: ModelGroup[] = [{
      ...modelGroups[0],
      provider_models: [
        {
          ...modelGroups[0].provider_models[1],
          route_id: "qiniu-openai:deepseek-v4-flash",
          provider_label: "Qiniu-OpenAi",
          ui_state: "untested",
        },
        {
          ...modelGroups[0].provider_models[2],
          route_id: "broken:deepseek-v4-flash",
          provider_label: "Broken Proxy",
          ui_state: "failed",
        },
        {
          ...modelGroups[0].provider_models[0],
          route_id: "deepseek-official:deepseek-v4-flash",
          provider_label: "DeepSeek Official",
          provider_kind: "official",
          ui_state: "ready",
        },
      ],
    }]

    const providers = buildAvailableModelGroups(unsortedModelGroups)[0].models[0].providers

    expect(providers.map((provider) => `${provider.label}:${provider.state}`)).toEqual([
      "DeepSeek Official:ready",
      "Qiniu-OpenAi:untested",
      "Broken Proxy:failed",
    ])
  })

  it("keeps similar backend model groups under model family sections", () => {
    const mixedModelGroups: ModelGroup[] = [
      modelGroups[0],
      {
        canonical_id: "antigravity-preview-05-2026",
        display_name: "Antigravity Preview 05 2026",
        provider_models: [
          {
            route_id: "gemini-official:antigravity-preview-05-2026",
            provider_label: "Gemini Official",
            provider_kind: "official",
            provider_model_id: "antigravity-preview-05-2026",
            ui_state: "untested",
            ui_detail: null,
            retry_at: null,
            reason_code: null,
            capability_state: "unknown",
            capabilities: {},
          },
        ],
        status_summary: {
          ready: 0,
          untested: 1,
          cooling_down: 0,
          historical_ready: 0,
          failed: 0,
          off: 0,
        },
        capability_summary: {
          capability_known_count: 0,
          thinking: "unknown",
          tools: "unknown",
          structured_output: "unknown",
          max_context_tokens: null,
          max_output_tokens: null,
        },
      },
    ]
    const groups = buildAvailableModelGroups(mixedModelGroups)

    expect(groups.map((group) => group.section)).toEqual(["anthropic", "gemini"])
  })

  it("uses backend model identity projection without changing backend ids", () => {
    const rawModelGroups: ModelGroup[] = [
      {
        ...modelGroups[0],
        canonical_id: "claude-opus-4-7-2025-4-28",
        display_name: "Claude Opus 4.7 2025-04-28",
        section_label: "anthropic",
        provider_models: [{
          ...modelGroups[0].provider_models[0],
          route_id: "anthropic-official:claude-opus-4-7-2025-4-28",
          provider_model_id: "claude-opus-4-7-2025-4-28",
        }],
      },
      {
        ...modelGroups[0],
        canonical_id: "gpt-5-5",
        display_name: "GPT 5.5",
        section_label: "openai",
        provider_models: [{
          ...modelGroups[0].provider_models[0],
          route_id: "openai-official:gpt-5-5",
          provider_label: "OpenAI Official",
          provider_model_id: "gpt-5.5",
        }],
      },
      {
        ...modelGroups[0],
        canonical_id: "claude-opus-4-1-20250805",
        display_name: "Claude Opus 4.1 20250805",
        section_label: "anthropic",
        provider_models: [{
          ...modelGroups[0].provider_models[0],
          route_id: "anthropic-official:claude-opus-4-1-20250805",
          provider_model_id: "claude-opus-4-1-20250805",
        }],
      },
      {
        ...modelGroups[0],
        canonical_id: "deepseek-v3-1-terminus-thinking-spaced",
        display_name: "DeepSeek V3.1 Terminus Thinking",
        section_label: "deepseek",
        provider_models: [{
          ...modelGroups[0].provider_models[0],
          route_id: "openrouter:deepseek-v3-1-terminus-thinking-spaced",
          provider_label: "OpenRouter",
          provider_kind: "third_party",
          provider_model_id: "deepseek/deepseek-v3-1-terminus-thinking",
        }],
      },
      {
        ...modelGroups[0],
        canonical_id: "deepseek-v3-1-terminus-thinking",
        display_name: "DeepSeek V3.1 Terminus Thinking",
        section_label: "deepseek",
        provider_models: [{
          ...modelGroups[0].provider_models[0],
          route_id: "openrouter:deepseek-v3-1-terminus-thinking",
          provider_label: "OpenRouter",
          provider_kind: "third_party",
          provider_model_id: "deepseek/deepseek-v3.1-terminus-thinking",
        }],
      },
      {
        ...modelGroups[0],
        canonical_id: "deepseek-v4-flash",
        display_name: "DeepSeek V4 Flash",
        section_label: "deepseek",
        provider_models: [{
          ...modelGroups[0].provider_models[0],
          route_id: "qiniu-openai:deepseek-v4-flash",
          provider_label: "Qiniu-OpenAi",
          provider_kind: "third_party",
          provider_model_id: "deepseek-v4-flash",
        }],
      },
      {
        ...modelGroups[0],
        canonical_id: "antigravity-preview-05-2026",
        display_name: "Antigravity Preview 05 2026",
        section_label: "gemini",
        provider_models: [{
          ...modelGroups[0].provider_models[0],
          route_id: "gemini-official:antigravity-preview-05-2026",
          provider_label: "Gemini Official",
          provider_model_id: "antigravity-preview-05-2026",
        }],
      },
    ]

    const groups = buildAvailableModelGroups(rawModelGroups)
    const byId = new Map(groups.flatMap((group) => group.models.map((model) => [model.id, { ...model, section: group.section }])))

    expect(byId.get("claude-opus-4-7-2025-4-28")).toMatchObject({
      label: "Claude Opus 4.7 2025-04-28",
      section: "anthropic",
    })
    expect(byId.get("gpt-5-5")).toMatchObject({
      label: "GPT 5.5",
      section: "openai",
    })
    expect(byId.get("claude-opus-4-1-20250805")).toMatchObject({
      label: "Claude Opus 4.1 20250805",
      section: "anthropic",
    })
    expect(byId.get("deepseek-v3-1-terminus-thinking-spaced")).toMatchObject({
      label: "DeepSeek V3.1 Terminus Thinking",
      section: "deepseek",
    })
    expect(byId.get("deepseek-v3-1-terminus-thinking")).toMatchObject({
      label: "DeepSeek V3.1 Terminus Thinking",
      section: "deepseek",
    })
    expect(byId.get("deepseek-v4-flash")).toMatchObject({
      label: "DeepSeek V4 Flash",
      section: "deepseek",
    })
    expect(byId.get("antigravity-preview-05-2026")).toMatchObject({
      label: "Antigravity Preview 05 2026",
      section: "gemini",
    })
    expect(filterAvailableModelGroups(groups, "deepseek v3.1 thinking").flatMap((group) => group.models.map((model) => model.id))).toEqual([
      "deepseek-v3-1-terminus-thinking",
      "deepseek-v3-1-terminus-thinking-spaced",
    ])
  })

  it("filters available models by display name, internal id, and provider label", () => {
    const groups = buildAvailableModelGroups(modelGroups)

    expect(filterAvailableModelGroups(groups, "sonnet 4 7").flatMap((group) => group.models.map((model) => model.id))).toEqual(["claude-sonnet-4-7"])
    expect(filterAvailableModelGroups(groups, "claude-sonnet-4-7").flatMap((group) => group.models.map((model) => model.id))).toEqual(["claude-sonnet-4-7"])
    expect(filterAvailableModelGroups(groups, "anthropic").flatMap((group) => group.models.map((model) => model.id))).toEqual(["claude-sonnet-4-7"])
    expect(filterAvailableModelGroups(groups, "qiniu").flatMap((group) => group.models.map((model) => model.id))).toEqual(["claude-sonnet-4-7"])
    expect(filterAvailableModelGroups(groups, "missing")).toEqual([])
  })

  it("keeps the title inside the roles scroll area and the model library beside it", () => {
    const html = renderRolesHtml()
    const rolesScrollAreaStart = html.indexOf('data-slot="scroll-area"')
    const rolesViewportStart = html.indexOf('data-slot="scroll-area-viewport"', rolesScrollAreaStart)
    const modelsSidebarStart = html.indexOf("<aside", rolesViewportStart)
    const rolesViewportHtml = html.slice(rolesViewportStart, modelsSidebarStart)

    expect(rolesViewportHtml).toContain("LLM Roles")
    expect(rolesViewportHtml).toContain('data-role-name="copilot_chat"')
    expect(rolesViewportHtml).not.toContain("Available Models")
    expect(html.indexOf("Available Models")).toBeGreaterThan(modelsSidebarStart)
    expect(html.slice(rolesScrollAreaStart, rolesViewportStart)).toContain("[&amp;_[data-slot=scroll-area-scrollbar]]:hidden")
    expect(html).toContain("lg:grid-cols-[minmax(0,1fr)_minmax(14rem,20vw)]")
    expect(html).toContain("2xl:grid-cols-[minmax(0,1fr)_minmax(14rem,18rem)]")
    expect(html).not.toContain("lg:grid-cols-[minmax(0,1fr)_18rem]")
  })

  it("uses shadcn dropdown primitives for provider add controls", () => {
    const html = renderRolesHtml()
    const addTriggerStart = html.indexOf('data-provider-add-trigger="true"')
    const addTriggerHtml = html.slice(addTriggerStart, html.indexOf("</button>", addTriggerStart) + "</button>".length)

    expect(html).toContain('data-slot="dropdown-menu-trigger"')
    expect(html).toContain('data-provider-add-trigger="true"')
    expect(html).not.toContain('aria-label="Add provider to model"')
    expect(addTriggerHtml).not.toContain('data-slot="select-trigger"')
    expect(html).not.toContain('class="mt-1 h-8 rounded-md border border-input bg-background px-2 text-xs"')
  })

  it("keeps model row content centered without aggregate status badges or model settings", () => {
    const html = renderRolesHtml()

    expect(html).toContain('data-model-row="true"')
    expect(html).toContain("items-center")
    expect(html).toContain('data-model-title-row="true"')
    expect(html).toContain('data-model-badge-group="true"')
    expect(html).toContain("grid-cols-[minmax(0,max-content)_auto]")
    expect(html).toContain("gap-x-4")
    expect(html).toContain("gap-2.5")
    expect(html).not.toContain('aria-label="Provider status Connected"')
    expect(html).not.toContain('aria-label="Provider status Failed"')
    expect(html).not.toContain('aria-label="Provider status Unavailable"')
    expect(html).not.toContain('aria-label="Model settings for')
  })

  it("keeps provider names single-line without a provider-name tooltip", () => {
    const html = renderRolesHtml()

    expect(html).toContain('data-provider-title="true"')
    expect(html).not.toContain('data-provider-title-tooltip="true"')
    expect(html).toContain("truncate")
    expect(html).toContain("whitespace-nowrap")
    expect(html).toContain("flex-nowrap")
  })

  it("prevents text selection on every draggable surface", () => {
    const html = renderRolesHtml()
    const availableModelsHtml = renderToStaticMarkup(<AvailableModelsSidebar modelGroups={modelGroups} />)

    expect(html).toContain('data-dnd-drag-surface="model"')
    expect(html).toContain('data-dnd-drag-surface="provider"')
    expect(html).toContain("select-none")
    expect(availableModelsHtml).toContain('data-available-model-drag-source="true"')
    expect(availableModelsHtml).toContain("select-none")
  })

  it("accepts available model drops across the role card content area", () => {
    const html = renderRolesHtml()

    expect(html).toMatch(/data-slot="card"[^>]*data-role-name="copilot_chat"[^>]*data-model-drop-zone="true"/)
    expect(html).toContain('data-model-drop-zone="true"')
    expect(html).toContain('data-model-drop-target="true"')
    expect(html).toContain('data-model-drop-fallback="active-drag-ref"')
    expect(html).toContain('data-role-drop-shield="true"')
  })

  it("renders provider rows as a max-three-column responsive grid with stable aligned tracks", () => {
    const html = renderRolesHtml()

    expect(html).toContain('data-provider-grid="true"')
    expect(html).toContain("grid-cols-[repeat(auto-fill,minmax(min(100%,max(12rem,calc((100%_-_0.75rem)/3))),1fr))]")
    expect(html).toContain("justify-start")
    expect(html).not.toContain("grid-cols-[repeat(auto-fit,minmax(min(100%,max(12rem,calc((100%_-_0.75rem)/3))),1fr))]")
    expect(html).not.toContain("grid-cols-[repeat(auto-fit,minmax(min(100%,10rem),max-content))]")
    expect(html).not.toContain("max-w-64")
    expect(html).not.toContain("grid-cols-[repeat(auto-fit,minmax(12rem,1fr))]")
    expect(html).toContain('data-provider-add-trigger="true"')
    expect(html).toContain('data-variant="ghost"')
    expect(html).toContain("h-9 w-full")
    expect(html).toContain("hover:bg-muted/35")
    expect(html).toContain("Add provider")
    expect(html).not.toContain("All providers added")

    const allProvidersAddedData: RolesData = {
      ...rolesData,
      roles: {
        copilot_chat: {
          ...rolesData.roles.copilot_chat,
          models: {
            CL46T: {
              ...rolesData.roles.copilot_chat.models.CL46T,
              providers: ["anthropic", "openai_proxy"],
            },
          },
        },
      },
    }
    const filledHtml = renderRolesHtml({ data: allProvidersAddedData })

    expect(filledHtml).not.toContain('data-provider-add-trigger="true"')
  })

  it("reorders model groups without changing the selected providers", () => {
    const next = reorderModelInRole(rolesData, "copilot_chat", "DS32R", "CL46T")

    expect(Object.keys(next.roles.copilot_chat.models)).toEqual(["DS32R", "CL46T"])
    expect(next.roles.copilot_chat.active_model).toBe("DS32R")
    expect(next.roles.copilot_chat.models.CL46T.providers).toEqual(["anthropic"])
    expect(next.roles.copilot_chat.models.DS32R.providers).toEqual(["openai_proxy"])
  })

  it("reorders providers only inside the targeted model group", () => {
    const dataWithTwoProviders: RolesData = {
      ...rolesData,
      roles: {
        copilot_chat: {
          ...rolesData.roles.copilot_chat,
          models: {
            ...rolesData.roles.copilot_chat.models,
            CL46T: {
              ...rolesData.roles.copilot_chat.models.CL46T,
              providers: ["anthropic", "openai_proxy"],
            },
          },
        },
      },
    }

    const next = reorderProviderInRole(dataWithTwoProviders, "copilot_chat", "CL46T", 0, 1)

    expect(Object.keys(next.roles.copilot_chat.models)).toEqual(["CL46T", "DS32R"])
    expect(next.roles.copilot_chat.models.CL46T.providers).toEqual(["openai_proxy", "anthropic"])
    expect(next.roles.copilot_chat.models.DS32R.providers).toEqual(["openai_proxy"])
  })

  it("removes providers and model groups without disturbing adjacent rows", () => {
    const dataWithTwoProviders: RolesData = {
      ...rolesData,
      roles: {
        copilot_chat: {
          ...rolesData.roles.copilot_chat,
          models: {
            ...rolesData.roles.copilot_chat.models,
            CL46T: {
              ...rolesData.roles.copilot_chat.models.CL46T,
              providers: ["anthropic", "openai_proxy"],
            },
          },
        },
      },
    }

    const providerRemoved = removeProviderFromRole(dataWithTwoProviders, "copilot_chat", "CL46T", 1)
    const modelRemoved = removeModelFromRole(rolesData, "copilot_chat", "CL46T")

    expect(providerRemoved.roles.copilot_chat.models.CL46T.providers).toEqual(["anthropic"])
    expect(providerRemoved.roles.copilot_chat.models.DS32R.providers).toEqual(["openai_proxy"])
    expect(modelRemoved.roles.copilot_chat.models.CL46T).toBeUndefined()
    expect(modelRemoved.roles.copilot_chat.models.DS32R.providers).toEqual(["openai_proxy"])
    expect(modelRemoved.roles.copilot_chat.active_model).toBe("DS32R")
  })

  it("uses subdued provider card text and role editor icons", () => {
    const html = renderRolesHtml()

    expect(html).toContain('data-provider-title="true"')
    expect(html).not.toContain('data-provider-title-tooltip="true"')
    expect(html).toContain("text-muted-foreground")
    expect(html).toContain('data-role-icon="true"')
  })

  it("adds named roles as empty drafts that can auto-save", () => {
    const next = appendRole(rolesData, "planner_role")

    expect(Object.keys(next.roles)).toEqual(["copilot_chat", "planner_role"])
    expect(next.roles.planner_role).toEqual({
      model_fallback_enabled: true,
      active_model: "",
      models: {},
    })
    expect(validateRolesDraft(next)).toBeNull()
  })

  it("normalizes stale active models before roles autosave", () => {
    const next = normalizeRolesDraft({
      ...rolesData,
      roles: {
        ...rolesData.roles,
        test: {
          model_fallback_enabled: true,
          active_model: "unknown model",
          models: {},
        },
        stale_model: {
          model_fallback_enabled: true,
          active_model: "unknown model",
          models: {
            "unknown model": { providers: [] },
          },
        },
      },
    })

    expect(next.roles.test.active_model).toBe("")
    expect(next.roles.stale_model.active_model).toBe("")
    expect(next.roles.stale_model.models).toEqual({})
    expect(validateRolesDraft(next)).toBeNull()
  })

  it("renames role keys without changing role configuration", () => {
    const dataWithSingleModelRole: RolesData = {
      ...rolesData,
      single_model_roles: ["copilot_chat"],
    }

    const next = renameRole(dataWithSingleModelRole, "copilot_chat", "planner_role")

    expect(Object.keys(next.roles)).toEqual(["planner_role"])
    expect(next.roles.planner_role).toEqual(rolesData.roles.copilot_chat)
    expect(next.roles.copilot_chat).toBeUndefined()
    expect(next.single_model_roles).toEqual(["planner_role"])
  })

  it("uses a role name dialog for add and edit flows", () => {
    const html = renderRolesHtml()
    const dialogHtml = renderToStaticMarkup(
      <RoleNameDialog
        title="New role"
        initialName=""
        existingNames={Object.keys(rolesData.roles)}
        open
        trigger={<button type="button">Open</button>}
        onSubmit={vi.fn()}
      />,
    )
    const fieldsHtml = renderToStaticMarkup(
      <RoleNameFields
        inputId="role-name-test"
        nameDraft="planner_role"
        error={null}
        onNameChange={vi.fn()}
      />,
    )

    expect(html).toContain('data-role-actions-trigger="true"')
    expect(html).not.toContain(">Edit</button>")
    expect(dialogHtml).toContain('data-slot="dialog-trigger"')
    expect(fieldsHtml).toContain('data-slot="field-set"')
    expect(fieldsHtml).toContain("Role name")
    expect(fieldsHtml).toContain('value="planner_role"')
    expect(dialogHtml).not.toContain("disabled")
  })

  it("shows only the graph agent accordion section in LLM Roles", () => {
    const groupedData: RolesData = {
      ...rolesData,
      roles: {
        planner: {
          model_fallback_enabled: true,
          active_model: "",
          models: {},
        },
        copilot_chat: rolesData.roles.copilot_chat,
      },
    }
    const html = renderRolesHtml({ data: groupedData })

    expect(html).toContain('data-slot="catalog-accordion"')
    expect(html).toContain('data-slot="catalog-accordion-trigger"')
    expect(html).toContain('data-role-category="graph-agent"')
    expect(html).toContain("Graph Agent Roles")
    expect(html).not.toContain('data-role-category="copilot"')
    expect(html).not.toContain("Copilot Roles")
    expect(html).not.toContain("Add Copilot Role")
    expect(html).toContain('data-role-name="copilot_chat"')
    expect(html.indexOf("catalog-accordion-state-icon")).toBeLessThan(html.indexOf("Graph Agent Roles"))
    expect(html.indexOf("Graph Agent Roles")).toBeLessThan(html.indexOf("lucide-cog"))
    expect(html).not.toContain("lucide-workflow")
  })

  it("uses role_kind to keep graph-agent roles with copilot-like names visible", () => {
    const groupedData: RolesData = {
      ...rolesData,
      roles: {
        assistant: {
          role_kind: "copilot",
          model_fallback_enabled: true,
          active_model: "",
          models: {},
        },
        copilot_planner: {
          role_kind: "graph_agent",
          model_fallback_enabled: true,
          active_model: "",
          models: {},
        },
      },
    }
    const html = renderRolesHtml({ data: groupedData })
    const graphSectionStart = html.indexOf('data-role-category="graph-agent"')
    const graphSection = html.slice(graphSectionStart)

    expect(graphSection).toContain('data-role-name="copilot_planner"')
    expect(graphSection).not.toContain('data-role-name="assistant"')
    expect(html).not.toContain('data-role-category="copilot"')
  })

  it("keeps the graph-agent category visible and uses default title typography", () => {
    const graphOnlyData: RolesData = {
      ...rolesData,
      roles: {
        Premium: {
          model_fallback_enabled: true,
          active_model: "",
          models: {},
        },
      },
    }
    const html = renderRolesHtml({ data: graphOnlyData })
    const titleIndex = html.indexOf('data-slot="card-title"')
    const titleEnd = html.indexOf("</div>", titleIndex)
    const titleHtml = html.slice(titleIndex, titleEnd)

    expect(html).toContain('data-role-category="graph-agent"')
    expect(html).toContain("Add Graph Agent Role")
    expect(html).not.toContain('data-role-category="copilot"')
    expect(html).not.toContain("No Copilot roles configured.")
    expect(html).not.toContain("Add Copilot Role")
    expect(titleHtml).not.toContain("font-mono")
  })

  it("uses a role title icon and dropdown actions for edit and delete", () => {
    const html = renderRolesHtml()

    expect(html).toContain('data-role-title-icon="true"')
    expect(html).toContain('data-role-actions-trigger="true"')
    expect(html).toContain('aria-label="More actions for copilot_chat"')
    expect(html).not.toContain('data-role-edit-trigger="true"')
    expect(html).not.toContain(">Edit</button>")
  })

  // R6-2: the delete confirmation is now a Radix AlertDialog request (rendered
  // inside the Settings dialog tree, not a body-level sonner toast that closed
  // the modal on click). buildRoleDeleteRequest is the pure request builder.
  it("builds an AlertDialog delete request without deleting yet", () => {
    const onDeleteRole = vi.fn()

    const request = buildRoleDeleteRequest("copilot_chat", onDeleteRole)

    expect(request).toMatchObject({
      title: "Delete copilot_chat?",
      description: "Remove copilot_chat and its model fallback chain.",
    })
    expect(onDeleteRole).not.toHaveBeenCalled()
  })

  it("wires the confirm request onConfirm to persisted role deletion", () => {
    const onDeleteRole = vi.fn()

    const request = buildRoleDeleteRequest("copilot_chat", onDeleteRole)
    void request.onConfirm()

    expect(onDeleteRole).toHaveBeenCalledWith("copilot_chat")
  })

  it("removes role entries from role maps and grouping metadata", () => {
    const dataWithMetadata: RolesData = {
      ...rolesData,
      single_model_roles: ["copilot_chat"],
      peer_model_groups: {
        default: ["copilot_chat", "planner"],
      },
      roles: {
        ...rolesData.roles,
        planner: {
          model_fallback_enabled: true,
          active_model: "",
          models: {},
        },
      },
    }

    const next = removeRole(dataWithMetadata, "copilot_chat")

    expect(next.roles.copilot_chat).toBeUndefined()
    expect(next.roles.planner).toBeTruthy()
    expect(next.single_model_roles).toEqual([])
    expect(next.peer_model_groups).toEqual({ default: ["planner"] })
  })

  it("does not show role name errors until submit and checks duplicates case-insensitively", () => {
    expect(roleNameDisplayError("", ["copilot_chat"], "", false)).toBeNull()
    expect(roleNameDisplayError("copilot_chat", ["copilot_chat"], "", false)).toBeNull()
    expect(roleNameDisplayError("", ["copilot_chat"], "", true)).toBe("Role name is required.")
    expect(roleNameDisplayError("copilot_chat", ["copilot_chat"], "", true)).toBe("Role name already exists.")
    expect(roleNameDisplayError("Copilot_Chat", ["copilot_chat"], "", true)).toBe("Role name already exists.")
  })

  it("keeps role test actions in the header and model fallback in the compact settings form", () => {
    const html = renderRolesHtml()
    const headerActionsStart = html.indexOf('data-role-header-actions="true"')
    const settingsPanelStart = html.indexOf('data-role-settings-panel="true"')
    const headerActionsHtml = html.slice(headerActionsStart, settingsPanelStart)

    expect(html).toContain('data-role-card-title-row="true"')
    expect(html).toContain('data-role-header-actions="true"')
    expect(html).toContain("items-center")
    expect(html).toContain("self-center")
    expect(html).toContain("row-span-1")
    expect(html).toContain("row-start-2")
    expect(html).toContain("sm:row-start-1")
    expect(html).toContain("sm:col-start-2")
    expect(html).toContain("flex-nowrap")
    expect(html).toContain("h-8")
    expect(headerActionsHtml).not.toContain("model_fallback_enabled")
    expect(html).toContain('data-role-test-trigger="true"')
    expect(html).toContain('data-role-model-fallback-setting="true"')
    expect(html).toContain("Model Fallback")
  })

  it("lazy renders available model cards without changing the full result count", () => {
    const manyModelGroups = Array.from({ length: 50 }, (_, index): ModelGroup => ({
      ...modelGroups[0],
      canonical_id: `bulk-model-${index}`,
      display_name: `Bulk Model ${index}`,
      provider_models: modelGroups[0].provider_models.map((providerModel) => ({
        ...providerModel,
        route_id: `${providerModel.route_id}-${index}`,
      })),
    }))
    const html = renderToStaticMarkup(<AvailableModelsSidebar modelGroups={manyModelGroups} />)
    const renderedCards = html.match(/data-available-model-drag-source="true"/g) ?? []

    expect(html).toContain('data-lazy-list="available-models"')
    expect(html).toContain('data-lazy-sentinel="available-models"')
    expect(html).toContain('aria-label="50 available models"')
    expect(renderedCards.length).toBeGreaterThan(0)
    expect(renderedCards.length).toBeLessThan(50)
  })

  it("lazy renders role cards before the add-role action", () => {
    const manyRolesData: RolesData = {
      ...rolesData,
      roles: Object.fromEntries(
        Array.from({ length: 12 }, (_, index) => [
          `role_${index}`,
          {
            model_fallback_enabled: true,
            active_model: "CL46T",
            models: {
              CL46T: { providers: ["anthropic"], temperature: null, max_tokens: null },
            },
          },
        ]),
      ),
    }
    const html = renderRolesHtml({ data: manyRolesData })
    const renderedRoles = html.match(/data-role-name="/g) ?? []

    expect(html).toContain('data-lazy-list="roles"')
    expect(html).toContain('data-lazy-sentinel="roles"')
    expect(renderedRoles.length).toBeGreaterThan(0)
    expect(renderedRoles.length).toBeLessThan(12)
    expect(html).toContain("Add Graph Agent Role")
    expect(html).not.toContain("Add Copilot Role")
  })

  it("shows readable model names instead of active model controls or model abbreviations", () => {
    const html = renderRolesHtml()

    expect(html).toContain("Claude Sonnet 4.6 Thinking")
    expect(html).toContain("DeepSeek V4 Pro")
    expect(html).toContain('aria-label="Claude Sonnet 4.6 Thinking provider fallback order"')
    expect(html).not.toContain("configured for this model")
    expect(html).not.toContain("Provider chain")
    expect(html).not.toContain("Active model")
    expect(html).not.toContain("First model attempted before fallback.")
    expect(html).not.toContain(">CL46T<")
    expect(html).not.toContain(">DS32R<")
    expect(html).not.toContain(">GPT5<")
    expect(html).not.toContain(">active<")
    expect(html).not.toContain('aria-label="CL46T provider fallback order"')
  })

  it("prefers backend Model Group names when role model names are short codes", () => {
    const shortCodeData: RolesData = {
      ...rolesData,
      models: {
        DSV4F: {
          name: "DSV4F",
          providers: { anthropic: "deepseek-chat" },
        },
      },
      roles: {
        Analyst: {
          model_fallback_enabled: true,
          active_model: "DSV4F",
          models: {
            DSV4F: { providers: ["anthropic"], temperature: null, max_tokens: null },
          },
        },
      },
    }
    const shortCodeModelGroups: ModelGroup[] = [{
      ...modelGroups[0],
      canonical_id: "DSV4F",
      display_name: "DeepSeek V4 Flash",
      provider_models: [{
        ...modelGroups[0].provider_models[0],
        route_id: "anthropic",
        provider_label: "Anthropic",
        provider_model_id: "deepseek-chat",
      }],
    }]
    const html = renderRolesHtml({ data: shortCodeData, modelGroups: shortCodeModelGroups })

    expect(html).toContain("DeepSeek V4 Flash")
    expect(html).toContain('aria-label="DeepSeek V4 Flash provider fallback order"')
    expect(html).not.toContain(">DSV4F<")
    expect(html).not.toContain('aria-label="DSV4F provider fallback order"')
  })

  it("filters role providers to the providers owned by that model", () => {
    const dataWithMismatchedProvider: RolesData = {
      ...rolesData,
      providers: {
        ...rolesData.providers,
        gemini: { name: "Gemini Official", type: "google_genai" },
      },
      models: {
        ...rolesData.models,
        CL46T: {
          ...rolesData.models.CL46T,
          name: "claude-opus-4-1",
          providers: {
            anthropic: "claude-opus-4-1",
            gemini: "gemini-3.1-pro-preview",
          },
        },
      },
      roles: {
        copilot_chat: {
          ...rolesData.roles.copilot_chat,
          models: {
            CL46T: { providers: ["anthropic", "gemini"], temperature: 0.2, max_tokens: 8192 },
          },
        },
      },
    }
    const html = renderRolesHtml({ data: dataWithMismatchedProvider })
    const roleCardStart = html.indexOf('data-role-name="copilot_chat"')
    const sidebarStart = html.indexOf("<aside", roleCardStart)
    const roleCardHtml = html.slice(roleCardStart, sidebarStart)

    expect(roleCardHtml).toContain("Anthropic")
    expect(roleCardHtml).not.toContain("Gemini Official")
  })

  it("materializes credential providers when adding available models to a role", () => {
    const customCredentials: CredentialsState = {
      providers: [{
        id: "custom-532dc361-de53-480e-864f-188d9271ef34",
        name: "Anthropic Custom",
        api_key: "sk-custom",
        base_url: "https://example.test/v1",
        provider_type: "anthropic_compatible",
        available_models: [
          { id: "anthropic/claude-opus-4.7", capabilities: { thinking: true } },
        ],
      }],
    }
    const next = appendAvailableModelToRole(
      rolesData,
      "copilot_chat",
      "anthropic/claude-opus-4.7",
      Object.fromEntries(customCredentials.providers.map((provider) => [provider.id, provider])),
    )
    const modelCode = Object.keys(next.roles.copilot_chat.models)
      .find((code) => next.models[code]?.name === "anthropic/claude-opus-4.7")

    expect(modelCode).toBeTruthy()
    expect(next.providers["custom-532dc361-de53-480e-864f-188d9271ef34"]).toEqual({
      name: "Anthropic Custom",
      type: "anthropic_compatible",
      base_url: "https://example.test/v1",
    })
    expect(next.models[modelCode!].providers).toEqual({
      "custom-532dc361-de53-480e-864f-188d9271ef34": "anthropic/claude-opus-4.7",
    })
    expect(next.roles.copilot_chat.models[modelCode!].providers).toEqual([
      "custom-532dc361-de53-480e-864f-188d9271ef34",
    ])
    expect(validateRolesDraft(next)).toBeNull()
  })

  it("flags unknown role providers before the backend rejects the save", () => {
    const invalidData: RolesData = {
      ...rolesData,
      roles: {
        ...rolesData.roles,
        copilot_chat: {
          ...rolesData.roles.copilot_chat,
          models: {
            CL46T: { providers: ["missing-provider"], temperature: null, max_tokens: null },
          },
        },
      },
    }

    expect(validateRolesDraft(invalidData)).toBe(
      "copilot_chat: Model CL46T references unknown provider missing-provider",
    )
  })

  it("repairs a failed custom-provider draft when credential metadata is available", () => {
    const providerId = "custom-532dc361-de53-480e-864f-188d9271ef34"
    const customCredentials: CredentialsState = {
      providers: [{
        id: providerId,
        name: "Anthropic Custom",
        api_key: "sk-custom",
        base_url: "https://example.test/v1",
        provider_type: "anthropic_compatible",
        available_models: [{ id: "anthropic/claude-opus-4.7" }],
      }],
    }
    const failedDraft: RolesData = {
      ...rolesData,
      models: {
        ...rolesData.models,
        "anthropic/claude-opus-4.7": {
          name: "anthropic/claude-opus-4.7",
          reasoning: true,
          providers: { [providerId]: "anthropic/claude-opus-4.7" },
        },
      },
      roles: {
        copilot_chat: {
          ...rolesData.roles.copilot_chat,
          active_model: "anthropic/claude-opus-4.7",
          models: {
            "anthropic/claude-opus-4.7": { providers: [providerId], temperature: null, max_tokens: null },
          },
        },
      },
    }

    const repaired = pruneInvalidRoleProviders(
      failedDraft,
      Object.fromEntries(customCredentials.providers.map((provider) => [provider.id, provider])),
    )

    expect(repaired.providers[providerId]).toEqual({
      name: "Anthropic Custom",
      type: "anthropic_compatible",
      base_url: "https://example.test/v1",
    })
    expect(repaired.roles.copilot_chat.models["anthropic/claude-opus-4.7"].providers).toEqual([providerId])
    expect(validateRolesDraft(repaired)).toBeNull()
  })

  it("does not wipe role providers when the model directory has not hydrated yet (registry still loading)", () => {
    // The top-level `models`/`providers` directories are built from the slow
    // registry snapshot; while it's still loading (or was momentarily
    // invalidated — see api/llm.ts syncVerifiedCommunityCatalog nulling
    // cachedRegistry), `data.models` can legitimately be `{}` even though a
    // role's OWN model_groups-derived provider list (route ids) is already
    // correct. Pruning must never mistake "not yet known" for "confirmed
    // invalid" — that previously wiped real fallback-chain routes on the next
    // debounced autosave.
    const roleName = "fast"
    const notYetHydrated: RolesData = {
      ...rolesData,
      models: {},
      providers: {},
      roles: {
        [roleName]: {
          model_fallback_enabled: true,
          active_model: "claude-haiku-4.5",
          models: {
            "claude-haiku-4.5": {
              providers: [
                "anthropic-official:claude-haiku-4-5-20251001",
                "wavespeed:anthropic.claude-haiku-4.5",
              ],
              temperature: null,
              max_tokens: null,
            },
          },
        },
      },
    }

    const result = pruneInvalidRoleProviders(notYetHydrated, {})

    expect(result).toBe(notYetHydrated)
    expect(result.roles[roleName].models["claude-haiku-4.5"].providers).toEqual([
      "anthropic-official:claude-haiku-4-5-20251001",
      "wavespeed:anthropic.claude-haiku-4.5",
    ])
  })

  it("uses whole-row drag surfaces without explicit drag or arrow controls", () => {
    const html = renderRolesHtml()

    expect(html).toContain('data-dnd-drag-surface="model"')
    expect(html).toContain('data-dnd-drag-surface="provider"')
    expect(html).toContain('data-slot="item"')
    expect(html).toContain('data-variant="outline"')
    expect(html).toContain('data-variant="muted"')
    expect(html).not.toContain('aria-label="Drag')
    expect(html).not.toContain('aria-label="Move')
  })

  it("uses a primary default-size test button on the role header", () => {
    const html = renderRolesHtml()

    expect(html).toContain('data-role-test-trigger="true"')
    expect(html).toContain('data-variant="default"')
    expect(html).toContain('data-size="default"')
    expect(html).toContain("min-w-20")
    expect(html).toContain(">Test</button>")
    expect(html).not.toContain("Test Chain")
  })

  it("uses semantic destructive role route states instead of hard-coded red utility colors", () => {
    const blockedRouteId = "broken-proxy:claude-sonnet-4-7"
    const html = renderRolesHtml({
      data: {
        models: {
          "claude-sonnet-4-7": {
            name: "Claude Sonnet 4.7",
            providers: { [blockedRouteId]: "claude-sonnet-4-7" },
          },
        },
        providers: {
          [blockedRouteId]: {
            name: "Broken Proxy",
            type: "openai_compatible",
            endpoint_id: "broken-proxy",
          },
        },
        roles: {
          analyst: {
            model_fallback_enabled: true,
            active_model: "claude-sonnet-4-7",
            models: {
              "claude-sonnet-4-7": {
                providers: [blockedRouteId],
                temperature: null,
                max_tokens: null,
              },
            },
          },
        },
      },
    })

    expect(html).toContain('data-role-route-status="blocked"')
    expect(html).toContain('data-variant="destructive"')
    expect(html).not.toContain("border-red")
    expect(html).not.toContain("bg-red")
    expect(html).not.toContain("text-red")
  })

  it("renders the three simple role params as an inline header panel without context/mode controls", () => {
    const dataWithIntent: RolesData = {
      ...rolesData,
      roles: {
        ...rolesData.roles,
        copilot_chat: {
          ...rolesData.roles.copilot_chat,
          intent: {
            provider_preference: "manual_order",
            thinking: true,
            max_output_tokens: 8192,
            temperature: 0.7,
          },
        },
      },
    }
    const html = renderRolesHtml({ data: dataWithIntent })
    const fieldsHtml = renderToStaticMarkup(
      <RoleSettingsFields
        roleName="copilot_chat"
        modelFallbackEnabled={true}
        draft={{
          providerPreference: "manual_order",
          thinking: true,
          maxOutputTokens: "128000",
          temperature: "0.7",
        }}
        tokenLimitSummary={{
          context: {
            knownCount: 2,
            totalCount: 3,
            min: 65536,
            max: 200000,
          },
          output: {
            knownCount: 2,
            totalCount: 3,
            min: 4096,
            max: 16384,
          },
        }}
        onModelFallbackChange={vi.fn()}
        onDraftChange={vi.fn()}
      />,
    )

    expect(html).toContain('data-role-settings-toggle="true"')
    expect(html).toContain('data-role-settings-panel="true"')
    expect(html).not.toContain('data-role-settings-trigger="true"')
    expect(html).not.toContain('data-slot="dialog-content"')
    expect(fieldsHtml).toContain('data-role-settings-fields="true"')
    expect(fieldsHtml).toContain('data-role-settings-toggles="true"')
    // Model Fallback and Thinking each get their own bordered box and fill the
    // row (2-col grid) the same way the Max output tokens / Temperature row below
    // does, instead of being nested inside one merged outer box.
    expect(fieldsHtml).toContain('<div data-role-settings-toggles="true" class="grid gap-3 lg:grid-cols-2">')
    expect(fieldsHtml).toContain('data-role-thinking-setting="true"')
    expect(fieldsHtml).toContain('data-role-output-settings="true"')
    expect(fieldsHtml).toContain('data-role-output-token-input="true"')
    expect(fieldsHtml).toContain('data-role-temperature-settings="true"')
    expect(fieldsHtml).toContain('data-role-temperature-input="true"')
    expect(fieldsHtml).toContain('data-slot="field-set"')
    expect(fieldsHtml).not.toContain("Provider Order")
    expect(fieldsHtml).not.toContain("Manual order")
    expect(fieldsHtml).toContain("Model Fallback")
    expect(fieldsHtml).toContain("model_fallback_enabled")
    expect(fieldsHtml).toContain("Thinking")
    // Thinking is now a single Switch, not a 3-way radio group.
    expect(fieldsHtml).toContain('data-slot="switch"')
    expect(fieldsHtml).not.toContain('data-slot="radio-group"')
    expect(fieldsHtml).not.toContain("Preferred")
    expect(fieldsHtml).not.toContain('data-slot="select-trigger"')
    // Context Tokens field is removed entirely.
    expect(fieldsHtml).not.toContain('data-role-context-settings="true"')
    expect(fieldsHtml).not.toContain("Context Tokens")
    expect(fieldsHtml).not.toContain("Required Min")
    expect(fieldsHtml).not.toContain("Use Max")
    // Output field is renamed and carries thousands-separated value + Temperature.
    expect(fieldsHtml).toContain("Max output tokens")
    expect(fieldsHtml).toContain('value="128,000"')
    expect(fieldsHtml).toContain("Temperature")
    // Temperature is a Slider (data-slot="slider"), not a text Input; its current
    // value is surfaced via the readout span next to it, not a `value=` attribute.
    expect(fieldsHtml).toContain('data-slot="slider"')
    expect(fieldsHtml).toContain('data-role-temperature-input="true"')
    expect(fieldsHtml).toContain(">0.7<")
    expect(fieldsHtml).toContain("Route max output token range: min 4,096 / max 16,384. 1 route cap unavailable.")
  })

  it("maps the draft to the three-param role intent (empty output/temperature -> null)", () => {
    expect(roleIntentFromSettingsDraft({
      providerPreference: "manual_order",
      thinking: true,
      maxOutputTokens: "128000",
      temperature: "0.7",
    })).toEqual({
      provider_preference: "manual_order",
      thinking: true,
      max_output_tokens: 128000,
      temperature: 0.7,
    })

    expect(roleIntentFromSettingsDraft({
      providerPreference: "manual_order",
      thinking: false,
      maxOutputTokens: "",
      temperature: "",
    })).toEqual({
      provider_preference: "manual_order",
      thinking: false,
      max_output_tokens: null,
      temperature: null,
    })
  })

  it("formats and strips thousands separators for the output token input", () => {
    expect(formatThousands("128000")).toBe("128,000")
    expect(formatThousands("1")).toBe("1")
    expect(formatThousands("")).toBe("")
    // Tolerates separators / stray chars already in the string (live typing).
    expect(formatThousands("128,00")).toBe("12,800")
    expect(stripThousands("128,000")).toBe("128000")
    expect(stripThousands("12ab34")).toBe("1234")
  })

  it("shows an unavailable-caps hint for the output field when route caps are unknown", () => {
    const fieldsHtml = renderToStaticMarkup(
      <RoleSettingsFields
        roleName="copilot_chat"
        modelFallbackEnabled={true}
        draft={{
          providerPreference: "manual_order",
          thinking: false,
          maxOutputTokens: "",
          temperature: "",
        }}
        tokenLimitSummary={{
          context: {
            knownCount: 0,
            totalCount: 2,
            min: null,
            max: null,
          },
          output: {
            knownCount: 0,
            totalCount: 2,
            min: null,
            max: null,
          },
        }}
        onModelFallbackChange={vi.fn()}
        onDraftChange={vi.fn()}
      />,
    )

    expect(fieldsHtml).toContain("Route max output token caps are unavailable.")
    expect(fieldsHtml).not.toContain("Test first")
  })
})

describe("#35 available models configure + deprecated section", () => {
  const stateModelGroups: ModelGroup[] = [{
    canonical_id: "gpt-5",
    display_name: "GPT 5",
    section_label: "openai",
    provider_models: [
      {
        route_id: "ready:gpt-5",
        provider_label: "Ready Provider",
        provider_kind: "official",
        provider_model_id: "gpt-5",
        ui_state: "ready",
        ui_detail: null,
        retry_at: null,
        reason_code: null,
        capability_state: "known",
        capabilities: {},
      },
      {
        route_id: "missing-config:gpt-5",
        provider_label: "Misconfigured Provider",
        provider_kind: "third_party",
        provider_model_id: "gpt-5",
        ui_state: "failed",
        ui_detail: "API key is missing.",
        retry_at: null,
        reason_code: "missing_config",
        capability_state: "unknown",
        capabilities: {},
      },
      {
        route_id: "off:gpt-5",
        provider_label: "Disabled Provider",
        provider_kind: "custom",
        provider_model_id: "gpt-5",
        ui_state: "off",
        ui_detail: "Disabled by user.",
        retry_at: null,
        reason_code: "user_disabled",
        capability_state: "unknown",
        capabilities: {},
      },
    ],
    status_summary: { ready: 1, untested: 0, cooling_down: 0, historical_ready: 0, failed: 1, off: 1 },
    capability_summary: {
      capability_known_count: 1,
      thinking: "unknown",
      tools: "unknown",
      structured_output: "unknown",
      max_context_tokens: null,
      max_output_tokens: null,
    },
  }]

  it("shows a Configure affordance on a missing_config failed provider row", () => {
    const html = renderToStaticMarkup(
      <AvailableModelsSidebar modelGroups={stateModelGroups} onNavigateToApiKeys={vi.fn()} />,
    )

    expect(html).toContain('data-available-model-provider-configure="true"')
    expect(html).toContain('data-provider-reason-code="missing_config"')
    expect(html).toContain("Configure")
    expect(html).toContain('aria-label="Configure Misconfigured Provider in API Keys"')
  })

  it("renders off/disabled routes inside a non-draggable collapsible deprecated section", () => {
    const html = renderToStaticMarkup(
      <AvailableModelsSidebar modelGroups={stateModelGroups} />,
    )

    expect(html).toContain('data-available-model-deprecated-toggle="true"')
    expect(html).toContain('data-available-model-deprecated-section="true"')
    expect(html).toContain("Deprecated (1)")
    // The off route's name renders inside the deprecated section, marked non-draggable.
    const deprecatedSection = html.match(/data-available-model-deprecated-section="true"[\s\S]*$/)?.[0] ?? ""
    expect(deprecatedSection).toContain("Disabled Provider")
    expect(deprecatedSection).toContain('data-available-model-deprecated-row="true"')
    expect(deprecatedSection).toContain('data-available-model-native-dnd="off"')
    expect(deprecatedSection).not.toContain('data-available-model-drag-source="true"')
    expect(html).toContain('data-available-model-deprecated-copy="true"')
    expect(html).toContain('data-available-model-deprecated-reprobe="true"')
    // The off route is NOT in the draggable provider row.
    const draggableButton = html.match(/<button[^>]*data-available-model-drag-source="true"[\s\S]*?<\/button>/)?.[0] ?? ""
    expect(draggableButton).not.toContain("Disabled Provider")
  })
})

describe("#50a model bundle status lights", () => {
  const bundleModelGroups: ModelGroup[] = [{
    canonical_id: "claude-sonnet-4-7",
    display_name: "Claude Sonnet 4.7",
    section_label: "anthropic",
    provider_models: [{
      route_id: "anthropic-official:claude-sonnet-4-7",
      endpoint_id: "anthropic-official",
      provider_label: "Anthropic Official",
      provider_kind: "official",
      provider_model_id: "claude-sonnet-4-7",
      ui_state: "ready",
      ui_detail: null,
      retry_at: null,
      reason_code: null,
      capability_state: "known",
      capabilities: {},
    }],
    status_summary: { ready: 1, untested: 0, cooling_down: 0, historical_ready: 0, failed: 0, off: 0 },
    capability_summary: {
      capability_known_count: 1,
      thinking: "unknown",
      tools: "unknown",
      structured_output: "unknown",
      max_context_tokens: null,
      max_output_tokens: null,
    },
  }]
  const bundleData: RolesData = {
    models: {
      "claude-sonnet-4-7": {
        name: "Claude Sonnet 4.7",
        providers: { "anthropic-official:claude-sonnet-4-7": "claude-sonnet-4-7" },
      },
    },
    providers: {
      "anthropic-official:claude-sonnet-4-7": {
        name: "Anthropic Official",
        type: "anthropic_compatible",
        endpoint_id: "anthropic-official",
      },
    },
    roles: {},
    model_bundles: {
      premium_stack: {
        model_profile_id: "premium_stack",
        display_name: "Premium Stack",
        canonical_id: "bundle:premium_stack",
        model_fallback_enabled: true,
        intent: { provider_preference: "manual_order" },
        model_groups: [{
          canonical_id: "claude-sonnet-4-7",
          display_name: "Claude Sonnet 4.7",
          provider_models: [{ route_id: "anthropic-official:claude-sonnet-4-7" }],
        }],
        fallback_chain: [{ route_id: "anthropic-official:claude-sonnet-4-7" }],
        materialization_report: {
          entries: [{
            canonical_id: "claude-sonnet-4-7",
            route_id: "anthropic-official:claude-sonnet-4-7",
            role_fit: "using",
          }],
          warnings: [],
          skipped_provider_details: [],
        },
      },
    },
  }

  const bundleCredentialsByCode = credentialsByProviderCode(bundleData, {
    providers: [{
      id: "anthropic-official",
      name: "Anthropic Official",
      api_key: "sk-anthropic",
      provider_type: "anthropic_compatible",
      last_test_status: "ok",
    }],
  })
  const bundleProviderModelsByRouteId = new Map(
    bundleModelGroups[0].provider_models.map((providerModel) => [providerModel.route_id, providerModel]),
  )

  function renderBundleCardWithRoleFit(
    materializationReport: NonNullable<RolesData["model_bundles"]>[string]["materialization_report"],
    extra?: {
      onRunTest?: (bundleId: string) => void
      testStatuses?: RoleChainStatusMap
      testRunning?: boolean
      bundleTestError?: string
    },
  ): string {
    const bundle = {
      ...bundleData.model_bundles!.premium_stack,
      materialization_report: materializationReport,
    }
    return renderToStaticMarkup(
      <ModelBundleCard
        bundle={bundle}
        bundleId="premium_stack"
        data={{ ...bundleData, model_bundles: { premium_stack: bundle } }}
        credentialsByCode={bundleCredentialsByCode}
        modelDisplayNamesByCode={new Map([["claude-sonnet-4-7", "Claude Sonnet 4.7"]])}
        providerModelsByRouteId={bundleProviderModelsByRouteId}
        onRunTest={extra?.onRunTest}
        testStatuses={extra?.testStatuses}
        testRunning={extra?.testRunning}
        bundleTestError={extra?.bundleTestError}
        getActiveAvailableModelDragId={() => null}
        getAvailableModelGroup={() => null}
        onChange={vi.fn()}
        onDeleteBundle={vi.fn()}
      />,
    )
  }

  it("feeds bundle role-fit into ModelItem status lights (#50a)", () => {
    const html = renderBundleCardWithRoleFit(bundleData.model_bundles!.premium_stack.materialization_report)

    // Status light wiring present: role-fit drives a Can Run light fed via ModelItem.
    expect(html).toContain('data-role-route-status-light="true"')
    expect(html).toContain('aria-label="Role route status Can Run')
    expect(html).toContain('data-role-route-status="runnable"')
  })

  it("projects every backend role_fit verdict from the bundle materialization_report into the light", () => {
    // #50/#45: role_fit is authoritative from the backend materialize report — the
    // card only renders it, never re-derives fit client-side. Each verdict must map
    // to the correct user state: using→Can Run, downgraded/needs_test→Limited,
    // not_fit→Blocked.
    const downgraded = renderBundleCardWithRoleFit({
      entries: [{
        canonical_id: "claude-sonnet-4-7",
        route_id: "anthropic-official:claude-sonnet-4-7",
        role_fit: "downgraded",
        warnings: [{ code: "thinking_preferred_unsupported" }],
      }],
      warnings: [],
      skipped_provider_details: [],
    })
    expect(downgraded).toContain('data-role-route-status="limited"')
    expect(downgraded).toContain('aria-label="Role route status Limited')

    const needsTest = renderBundleCardWithRoleFit({
      entries: [{
        canonical_id: "claude-sonnet-4-7",
        route_id: "anthropic-official:claude-sonnet-4-7",
        role_fit: "needs_test",
        warnings: [{ code: "thinking_capability_unknown" }],
      }],
      warnings: [],
      skipped_provider_details: [],
    })
    expect(needsTest).toContain('data-role-route-status="limited"')

    const notFit = renderBundleCardWithRoleFit({
      entries: [{
        canonical_id: "claude-sonnet-4-7",
        route_id: "anthropic-official:claude-sonnet-4-7",
        role_fit: "not_fit",
        warnings: [{ code: "output_tokens_below_required_minimum" }],
      }],
      warnings: [],
      skipped_provider_details: [],
    })
    expect(notFit).toContain('data-role-route-status="blocked"')
    expect(notFit).toContain('aria-label="Role route status Blocked')
  })

  it("renders a single top-level role-route diagnostic tooltip for a downgraded bundle route", () => {
    // #45: the diagnostic is a single top-level tooltip wrapping the row (no nested
    // tooltip, no separate result panel). The warning reason from the report drives
    // the diagnostic text.
    const html = renderBundleCardWithRoleFit({
      entries: [{
        canonical_id: "claude-sonnet-4-7",
        route_id: "anthropic-official:claude-sonnet-4-7",
        role_fit: "downgraded",
        warnings: [{ code: "thinking_preferred_unsupported" }],
      }],
      warnings: [],
      skipped_provider_details: [],
    })

    expect(html).toContain('data-provider-row-status-tooltip="true"')
    // Single light per row — no parallel RoleTestResultPanel surface (spec §2.4 "不要").
    expect(html).not.toContain('data-role-test-result-panel="true"')
  })

  it("still renders the light from ui_state when the bundle has no materialization_report (empty / undefined report)", () => {
    // Empty report and a totally missing report must not crash and must still light
    // the row from the 6-state ui_state alone (ready→Can Run). This guards the
    // empty/error projection path the design requires.
    const emptyReport = renderBundleCardWithRoleFit({
      entries: [],
      warnings: [],
      skipped_provider_details: [],
    })
    expect(emptyReport).toContain('data-role-route-status="runnable"')

    const undefinedReport = renderBundleCardWithRoleFit(undefined)
    expect(undefinedReport).toContain('data-role-route-status="runnable"')
    expect(undefinedReport).toContain('data-role-route-status-light="true"')
  })

  it("renders a bundle Test button when onRunTest is wired (#50b)", () => {
    const html = renderBundleCardWithRoleFit(
      bundleData.model_bundles!.premium_stack.materialization_report,
      { onRunTest: vi.fn() },
    )
    expect(html).toContain('data-model-bundle-test-trigger="true"')
    expect(html).toMatch(/>Test<\/button>/)
  })

  it("shows Testing + projects live test statuses while a bundle test runs (#50b)", () => {
    const html = renderBundleCardWithRoleFit(
      bundleData.model_bundles!.premium_stack.materialization_report,
      {
        onRunTest: vi.fn(),
        testRunning: true,
        testStatuses: {
          [roleChainStatusKey("claude-sonnet-4-7", "anthropic-official:claude-sonnet-4-7")]: {
            status: "testing",
          },
        },
      },
    )
    expect(html).toContain("Testing")
    expect(html).toContain('data-role-route-status="testing"')
  })

  it("shows the bundle test error banner without a Test trigger when there is no handler", () => {
    const html = renderBundleCardWithRoleFit(
      bundleData.model_bundles!.premium_stack.materialization_report,
      { bundleTestError: "probe exploded" },
    )
    expect(html).toContain('data-model-bundle-test-error="true"')
    expect(html).toContain("probe exploded")
  })
})

describe("#46 role test state projects from the module store on (re)mount", () => {
  afterEach(() => {
    __resetRoleTestStoreForTests()
  })

  it("restores a running test's live progress from the store when the tab remounts", () => {
    // Simulate an in-flight test owned by the module-scoped backend mirror — the
    // exact state that survives a tab switch / remount. The freshly rendered tab
    // must project that running progress, not a blank untested card.
    __setRoleTestStoreForTests({
      copilot_chat: {
        running: true,
        activeStatuses: {
          [roleChainStatusKey("CL46T", "anthropic")]: { status: "testing" },
        },
      },
    })

    const html = renderRolesHtml()

    expect(html).toContain("Testing")
    expect(html).toContain('data-provider-test-status="testing"')
    expect(html).toContain('data-role-route-status="testing"')
  })

  it("restores a settled test's last result from the store when the tab remounts", () => {
    __setRoleTestStoreForTests({
      copilot_chat: {
        running: false,
        result: {
          role_name: "copilot_chat",
          status: "ok",
          warnings: [],
          model_groups: [{
            canonical_id: "CL46T",
            display_name: "Claude Sonnet 4.6 Thinking",
            provider_results: [{
              route_id: "anthropic",
              provider_label: "Anthropic",
              provider_ui_state: "ready",
              role_fit: "using",
              admission_decision: "admit",
              status: "ok",
              warnings: [],
              retry_at: null,
              message: null,
              resolved_settings: {},
            }],
          }],
        },
      },
    })

    const html = renderRolesHtml()

    expect(html).toContain('data-provider-test-status="ok"')
  })

  it("projects the store error banner without an in-component test state copy", () => {
    __setRoleTestStoreForTests({
      copilot_chat: {
        running: false,
        error: "Save the role before testing: copilot_chat: model must contain at least one provider",
      },
    })

    const html = renderRolesHtml()

    expect(html).toContain('data-role-test-error="true"')
    expect(html).toContain("Role Test failed: Save the role before testing:")
  })
})

describe("#51 bundle drop creates a reference, not a snapshot", () => {
  const referenceData: RolesData = {
    models: {},
    providers: {
      "anthropic-official:claude-sonnet-4-7": {
        name: "Anthropic Official",
        type: "anthropic_compatible",
        endpoint_id: "anthropic-official",
      },
    },
    roles: {
      analyst: { model_fallback_enabled: true, active_model: "", models: {} },
    },
    model_bundles: {
      premium_stack: {
        model_profile_id: "premium_stack",
        display_name: "Premium Stack",
        canonical_id: "bundle:premium_stack",
        model_fallback_enabled: true,
        intent: { provider_preference: "manual_order" },
        model_groups: [{
          canonical_id: "claude-sonnet-4-7",
          display_name: "Claude Sonnet 4.7",
          provider_models: [{ route_id: "anthropic-official:claude-sonnet-4-7" }],
        }],
        fallback_chain: [{ route_id: "anthropic-official:claude-sonnet-4-7" }],
      },
    },
  }

  it("sets role.bundle_id (reference) without snapshot-copying the bundle routes", () => {
    const next = attachBundleReferenceToRole(referenceData, "analyst", "bundle:premium_stack")

    // Reference, not snapshot: bundle_id points at the bundle, and the role's own
    // model groups (the local delta layer) are NOT populated with the bundle routes.
    expect(next.roles.analyst.bundle_id).toBe("premium_stack")
    expect(Object.keys(next.roles.analyst.models)).toEqual([])
    // The original is untouched (pure function).
    expect(referenceData.roles.analyst.bundle_id).toBeUndefined()
  })

  it("ignores a non-bundle drag id (only bundle: ids attach a reference)", () => {
    const next = attachBundleReferenceToRole(referenceData, "analyst", "claude-sonnet-4-7")
    expect(next).toBe(referenceData)
  })

  it("round-trips bundle_id through the role serializer (reflects live bundle on re-projection)", () => {
    const withReference = attachBundleReferenceToRole(referenceData, "analyst", "bundle:premium_stack")
    const backend = rolesDataToBackend(withReference)
    expect(backend.roles.analyst.bundle_id).toBe("premium_stack")
  })

  it("renders a 'Linked to bundle X' badge on a reference role (not a snapshot label)", () => {
    const withReference = attachBundleReferenceToRole(referenceData, "analyst", "bundle:premium_stack")
    const html = renderToStaticMarkup(
      <RoleCard
        data={withReference}
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
    expect(html).toContain('data-role-linked-bundle="true"')
    expect(html).toContain("Linked to bundle: Premium Stack")
  })
})
