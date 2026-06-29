import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it, vi } from "vitest"
import { SettingsPageContent } from "./SettingsPageContent"
import type { SettingsPageContentProps, SettingsTab } from "./types"
import type { CredentialsState, ModelGroup, RolesData } from "../../../api/llm"

const emptyCredentials: CredentialsState = { providers: [] }
const emptyRolesData: RolesData = { models: {}, providers: {}, roles: {} }
const modelGroups: ModelGroup[] = []

function baseProps(overrides: Partial<SettingsPageContentProps> = {}): SettingsPageContentProps {
  return {
    activeTab: "general",
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
      giteaHost: "https://gitea.example.com",
      defaultSkillsDirectory: "/Users/alice/Skills",
      language: "en",
      remoteModelCatalogEnabled: true,
      isLoading: false,
      saveStatus: "idle",
      setUserId: vi.fn(),
      setGiteaHost: vi.fn(),
      setDefaultSkillsDirectory: vi.fn(),
      setLanguage: vi.fn(),
      setRemoteModelCatalogEnabled: vi.fn(),
    },
    connectionLost: false,
    onClose: vi.fn(),
    onTabChange: vi.fn(),
    onProviderFieldChange: vi.fn(),
    onGetProviderModels: vi.fn(),
    onDeleteProvider: vi.fn(),
    onDeleteProviderEndpoints: vi.fn(),
    onBeginAddProvider: vi.fn(),
    onAddProvider: vi.fn(),
    onCancelAddProvider: vi.fn(),
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

function render(overrides: Partial<SettingsPageContentProps> = {}): string {
  return renderToStaticMarkup(<SettingsPageContent {...baseProps(overrides)} />)
}

describe("Settings shell per-tab skeleton gate", () => {
  it("shows the role-card skeleton for LLM Roles while rolesData is null", () => {
    const html = render({ activeTab: "llm_roles", rolesData: null })
    expect(html).toContain('data-roles-tab-skeleton="true"')
    expect(html).toContain('data-roles-tab-skeleton-sidebar="true"')
    expect(html).toContain('data-slot="skeleton"')
  })

  it("shows the same role-card skeleton for Copilot while rolesData is null", () => {
    const html = render({ activeTab: "copilot", rolesData: null })
    expect(html).toContain('data-roles-tab-skeleton="true"')
    expect(html).toContain('data-roles-tab-skeleton-sidebar="true"')
  })

  it("replaces the skeleton with real Roles content once rolesData is present", () => {
    const html = render({ activeTab: "llm_roles", rolesData: emptyRolesData })
    expect(html).not.toContain('data-roles-tab-skeleton="true"')
  })

  it("never shows the roles skeleton on General", () => {
    const html = render({ activeTab: "general", rolesData: null })
    expect(html).not.toContain('data-roles-tab-skeleton="true"')
  })

  it("shows the General-tab skeleton while appSettings are loading", () => {
    const html = render({
      activeTab: "general",
      appSettings: { ...baseProps().appSettings, isLoading: true },
    })
    expect(html).toContain('data-general-tab-skeleton="true"')
    expect(html).toContain('data-slot="skeleton"')
    expect(html).not.toContain('id="studio-user-id"')
  })

  it("replaces the General skeleton with the editable form once appSettings load", () => {
    const html = render({
      activeTab: "general",
      appSettings: { ...baseProps().appSettings, isLoading: false },
    })
    expect(html).not.toContain('data-general-tab-skeleton="true"')
    expect(html).toContain('id="studio-user-id"')
  })

  it("surfaces the roles error instead of a perpetual skeleton when the fetch failed", () => {
    const html = render({ activeTab: "copilot", rolesData: null, rolesError: "Roles unavailable" })
    expect(html).not.toContain('data-roles-tab-skeleton="true"')
    expect(html).toContain('data-copilot-settings-page="true"')
  })
})

describe("Settings shell chrome", () => {
  it("keeps the top chrome close-only and leaves save status to each tab", () => {
    const html = render({ saveStatus: "pending", rolesSaveStatus: "saving" })
    expect(html).toContain('aria-label="Close settings"')
    expect(html).not.toContain("data-shell-save-status")
    expect(html).not.toContain('data-shell-connection-lost="true"')
  })

  it("does not render a second shell warning badge when the connection drops", () => {
    const html = render({ connectionLost: true })
    expect(html).not.toContain('data-shell-connection-lost="true"')
  })
})

describe("Settings shell error boundaries", () => {
  const tabs: SettingsTab[] = ["general", "api_keys", "llm_roles", "copilot"]
  it.each(tabs)("renders %s tab content without crashing", (activeTab) => {
    const html = render({ activeTab })
    expect(html.length).toBeGreaterThan(0)
    expect(html).not.toContain("failed to render")
  })
})
