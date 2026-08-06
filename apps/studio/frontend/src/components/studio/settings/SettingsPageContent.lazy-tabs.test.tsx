// @vitest-environment jsdom

import { act } from "react"
import { createRoot, type Root } from "react-dom/client"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { SettingsPageContent } from "./SettingsPageContent"
import type { SettingsPageContentProps } from "./types"
import type { CredentialsState, ModelGroup, RolesData } from "../../../api/llm"

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

vi.mock("./GeneralTab", () => ({
  GeneralTab: () => <div data-testid="general-tab-content" />,
}))

vi.mock("./api-keys/ApiKeysTab", () => ({
  ApiKeysTab: () => <div data-testid="api-keys-tab-content" />,
}))

vi.mock("./LlmRolesTab", () => ({
  LlmRolesTab: () => <div data-testid="llm-roles-tab-content" />,
}))

vi.mock("./copilot/CopilotTab", () => ({
  CopilotTab: () => <div data-testid="copilot-tab-content" />,
}))

const emptyCredentials: CredentialsState = { providers: [] }
const emptyRolesData: RolesData = { models: {}, providers: {}, roles: {} }
const modelGroups: ModelGroup[] = []

function baseProps(overrides: Partial<SettingsPageContentProps> = {}): SettingsPageContentProps {
  return {
    activeTab: "api_keys",
    credentials: emptyCredentials,
    credentialsLoading: false,
    credentialsError: null,
    drafts: [],
    pendingAddProviderId: null,
    saveStatus: "idle",
    rolesData: emptyRolesData,
    modelGroups,
    rolesSaveStatus: "idle",
    rolesError: null,
    appSettings: {
      userId: "alice",
      giteaHost: "",
      defaultSkillsDirectory: "",
      language: "en",
      remoteModelCatalogEnabled: false,
      isLoading: false,
      saveStatus: "idle",
      setUserId: vi.fn(),
      setGiteaHost: vi.fn(),
      setDefaultSkillsDirectory: vi.fn(),
      setLanguage: vi.fn(),
      setRemoteModelCatalogEnabled: vi.fn(),
      cliSessions: { claude: { model: '', effort: '' }, codex: { model: '', effort: '' }, agents: {} },
      setCliSessions: vi.fn(),
    },
    connectionLost: false,
    onClose: vi.fn(),
    onTabChange: vi.fn(),
    onProviderFieldChange: vi.fn(),
    onGetProviderModels: vi.fn(),
    onProbeEndpoint: vi.fn(),
    onForceEndpointTest: vi.fn(),
    onDeleteProvider: vi.fn(),
    onDeleteProviderEndpoints: vi.fn(),
    onRemoveModel: vi.fn(),
    onBeginAddProvider: vi.fn(),
    onAddProvider: vi.fn(),
    onCancelAddProvider: vi.fn(),
    onRevealProviderSecret: vi.fn().mockResolvedValue(null),
    onProviderModelsUpdated: vi.fn(),
    onRolesDataChange: vi.fn(),
    onDeleteRole: vi.fn(),
    onDeleteModelBundle: vi.fn(),
    onBeforeRoleTest: vi.fn().mockResolvedValue(null),
    onAfterRoleTest: vi.fn(),
    onNavigateToApiKeys: vi.fn(),
    ...overrides,
  }
}

describe("SettingsPageContent lazy tab mounting", () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    container = document.createElement("div")
    document.body.appendChild(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => {
      root.unmount()
    })
    container.remove()
  })

  it("does not mount LLM Roles or Copilot while opening API Keys, then keeps visited tabs mounted", () => {
    act(() => {
      root.render(<SettingsPageContent {...baseProps({ activeTab: "api_keys" })} />)
    })

    expect(container.querySelector("[data-testid='api-keys-tab-content']")).not.toBeNull()
    expect(container.querySelector("[data-testid='llm-roles-tab-content']")).toBeNull()
    expect(container.querySelector("[data-testid='copilot-tab-content']")).toBeNull()

    act(() => {
      root.render(<SettingsPageContent {...baseProps({ activeTab: "llm_roles" })} />)
    })

    expect(container.querySelector("[data-testid='api-keys-tab-content']")).not.toBeNull()
    expect(container.querySelector("[data-testid='llm-roles-tab-content']")).not.toBeNull()
    expect(container.querySelector("[data-settings-tab-panel='api_keys']")?.hasAttribute("hidden")).toBe(true)

    act(() => {
      root.render(<SettingsPageContent {...baseProps({ activeTab: "api_keys" })} />)
    })

    expect(container.querySelector("[data-testid='llm-roles-tab-content']")).not.toBeNull()
    expect(container.querySelector("[data-settings-tab-panel='llm_roles']")?.hasAttribute("hidden")).toBe(true)
  })
})
