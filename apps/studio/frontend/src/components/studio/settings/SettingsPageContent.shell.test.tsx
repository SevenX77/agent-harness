import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it, vi } from "vitest"
import { SettingsPageContent } from "./SettingsPageContent"
import type { SettingsPageContentProps, SettingsTab } from "./types"
import type { CredentialsState, ModelGroup, RolesData } from "../../../api/llm"

/**
 * N0 Settings · Shell render contracts (atoms #2 skeleton, #4 global save badge,
 * #5/#6 connection-lost indicator, #9 error-boundary wrapping).
 *
 * Static rendering via `renderToStaticMarkup` per the repo convention (no
 * @testing-library/react). Interactive/WS behaviour is covered by the Playwright
 * e2e `tests/e2e/settings-shell.spec.ts`; crash → fallback (which SSR can't
 * trigger) is covered there and in SettingsErrorBoundary.test.tsx.
 */

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
    saveStatus: "idle",
    rolesData: emptyRolesData,
    modelGroups,
    rolesSaveStatus: "idle",
    rolesError: null,
    appSettings: {
      userId: "alice",
      giteaHost: "https://gitea.example.com",
      defaultSkillsDirectory: "/Users/alice/Skills",
      isLoading: false,
      saveStatus: "idle",
      setUserId: vi.fn(),
      setGiteaHost: vi.fn(),
      setDefaultSkillsDirectory: vi.fn(),
    },
    connectionLost: false,
    onClose: vi.fn(),
    onTabChange: vi.fn(),
    onProviderFieldChange: vi.fn(),
    onGetProviderModels: vi.fn(),
    onTestProviderEndpoint: vi.fn(),
    onDeleteProvider: vi.fn(),
    onAddProvider: vi.fn(),
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

describe("Settings shell — #2 per-tab skeleton gate", () => {
  it("shows the role-card skeleton (cards + sidebar) for LLM Roles while rolesData is null", () => {
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

  it("never shows the roles skeleton on General (renders instantly, no skeleton)", () => {
    const html = render({ activeTab: "general", rolesData: null })
    expect(html).not.toContain('data-roles-tab-skeleton="true"')
  })

  it("surfaces the roles error instead of a perpetual skeleton when the fetch failed (rolesData null + rolesError)", () => {
    // Regression guard: a roles fetch failure leaves rolesData null AND sets
    // rolesError. The skeleton gate must fall through to the tab (which renders
    // the error) rather than show a forever-loading skeleton.
    const html = render({ activeTab: "copilot", rolesData: null, rolesError: "Roles unavailable" })
    expect(html).not.toContain('data-roles-tab-skeleton="true"')
    expect(html).toContain('data-copilot-settings-page="true"')
  })
})

describe("Settings shell — #4 global save badge in the top bar", () => {
  function topBarStatus(html: string): string | null {
    const match = html.match(/data-shell-save-status="([^"]+)"/)
    return match ? match[1] : null
  }

  it("merges three idle statuses into idle (badge hidden)", () => {
    const html = render({ saveStatus: "idle", rolesSaveStatus: "idle" })
    expect(topBarStatus(html)).toBe("idle")
    // SaveStatusBadge returns null for idle, so no badge element is emitted.
    expect(html).not.toContain('data-save-status-badge="true"')
  })

  it("shows error in the top bar when any one source errors (warning colour)", () => {
    const html = render({ saveStatus: "saved", rolesSaveStatus: "error" })
    expect(topBarStatus(html)).toBe("error")
    expect(html).toContain('data-save-status-badge="true"')
    expect(html).toContain('data-save-status="error"')
  })

  it("shows saving when no error but a save is in flight", () => {
    const html = render({ saveStatus: "pending", rolesSaveStatus: "saving" })
    expect(topBarStatus(html)).toBe("saving")
  })

  it("shows pending when only a debounce is queued", () => {
    const html = render({
      saveStatus: "idle",
      rolesSaveStatus: "pending",
      appSettings: { ...baseProps().appSettings, saveStatus: "idle" },
    })
    expect(topBarStatus(html)).toBe("pending")
  })
})

describe("Settings shell — #5/#6 connection-lost indicator", () => {
  it("hides the connection-lost warning by default", () => {
    const html = render({ connectionLost: false })
    expect(html).not.toContain('data-shell-connection-lost="true"')
  })

  it("renders the connection-lost warning to the right of the save badge when connectionLost is true", () => {
    const html = render({ connectionLost: true })
    expect(html).toContain('data-shell-connection-lost="true"')
    // It sits after the save-status slot in source order (right of the badge).
    const saveIdx = html.indexOf("data-shell-save-status")
    const lostIdx = html.indexOf('data-shell-connection-lost="true"')
    expect(saveIdx).toBeGreaterThanOrEqual(0)
    expect(lostIdx).toBeGreaterThan(saveIdx)
  })
})

describe("Settings shell — #9 every tab is wrapped (passthrough render)", () => {
  const tabs: SettingsTab[] = ["general", "api_keys", "llm_roles", "copilot"]
  it.each(tabs)("renders %s tab content without crashing (boundary passthrough)", (activeTab) => {
    const html = render({ activeTab })
    expect(html.length).toBeGreaterThan(0)
    // Healthy tabs never show the destructive fallback.
    expect(html).not.toContain("failed to render")
  })
})
