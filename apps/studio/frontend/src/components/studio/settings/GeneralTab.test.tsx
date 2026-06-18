import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it, vi } from "vitest"
import { GeneralTab } from "./GeneralTab"
import type { SettingsPageContentProps } from "./types"

/**
 * GeneralTab render-contract tests (N0 Settings · General, atoms #10–#15).
 *
 * The repo convention for component coverage is static rendering via
 * `renderToStaticMarkup` (no `@testing-library/react` dependency); interactive
 * behaviour (debounced PUT, picker, reset click, error toast) is exercised by
 * the Playwright e2e `tests/e2e/general-settings.spec.ts`. These tests lock the
 * rendering contract: every field is bound to its app-settings value, the save
 * badge reflects status, and loading/disabled wiring is present — so a future
 * edit that unbinds a field or drops the badge is caught.
 *
 * #15.1 (language persistence into app_settings) is intentionally NOT covered
 * here: it is backend-blocked (AppSettings has extra="forbid" + no `language`
 * field) and deferred. The language dropdown's current presence is asserted so
 * it is not accidentally removed before the backend field lands.
 */

type AppSettingsProp = SettingsPageContentProps["appSettings"]

function makeAppSettings(overrides: Partial<AppSettingsProp> = {}): AppSettingsProp {
  return {
    userId: "alice",
    giteaHost: "https://gitea.example.com",
    defaultSkillsDirectory: "/Users/alice/AgentStudio/Skills",
    isLoading: false,
    saveStatus: "saved",
    setUserId: vi.fn(),
    setGiteaHost: vi.fn(),
    setDefaultSkillsDirectory: vi.fn(),
    ...overrides,
  }
}

function renderTab(overrides?: Partial<AppSettingsProp>): string {
  return renderToStaticMarkup(<GeneralTab appSettings={makeAppSettings(overrides)} />)
}

function inputTag(html: string, id: string): string {
  const match = html.match(new RegExp(`<input[^>]*\\bid="${id}"[^>]*>`))
  if (!match) throw new Error(`input #${id} not found in markup`)
  return match[0]
}

describe("GeneralTab render contract", () => {
  it("#10 binds the Studio User ID input to appSettings.userId", () => {
    const html = renderTab({ userId: "carol" })
    expect(inputTag(html, "studio-user-id")).toContain('value="carol"')
  })

  it("#11 binds the Gitea Host input to appSettings.giteaHost", () => {
    const html = renderTab({ giteaHost: "https://git.internal.example" })
    expect(inputTag(html, "gitea-host")).toContain('value="https://git.internal.example"')
  })

  it("#12 binds the default skill folder input to appSettings.defaultSkillsDirectory", () => {
    const html = renderTab({ defaultSkillsDirectory: "/tmp/custom-skills" })
    expect(inputTag(html, "default-skill-folder")).toContain('value="/tmp/custom-skills"')
  })

  it("#13 renders the native folder Choose button", () => {
    expect(renderTab()).toContain("Choose")
  })

  it("#14 renders a Reset control that is disabled when no runtime default is available", () => {
    // In the node test env getRuntimeConfig() is null, so the runtime-default
    // fallback resolves to empty and Reset must be disabled (no target to reset to).
    const html = renderTab()
    const resetMatch = html.match(/<button[^>]*aria-label="Reset default skill folder"[^>]*>/)
    expect(resetMatch).not.toBeNull()
    expect(resetMatch?.[0]).toContain('disabled=""')
  })

  it("#15 renders the save-status badge reflecting the current save status", () => {
    expect(renderTab({ saveStatus: "saved" })).toContain('data-save-status="saved"')
    expect(renderTab({ saveStatus: "pending" })).toContain('data-save-status="pending"')
    expect(renderTab({ saveStatus: "error" })).toContain('data-save-status="error"')
  })

  it("#15 hides the save-status badge when idle", () => {
    expect(renderTab({ saveStatus: "idle" })).not.toContain("data-save-status-badge")
  })

  it("disables the editable inputs while settings are loading", () => {
    const html = renderTab({ isLoading: true })
    expect(inputTag(html, "studio-user-id")).toContain('disabled=""')
    expect(inputTag(html, "gitea-host")).toContain('disabled=""')
    expect(inputTag(html, "default-skill-folder")).toContain('disabled=""')
  })

  it("keeps the editable inputs enabled once loaded", () => {
    const html = renderTab({ isLoading: false })
    expect(inputTag(html, "studio-user-id")).not.toContain('disabled=""')
    expect(inputTag(html, "gitea-host")).not.toContain('disabled=""')
  })

  it("renders all three identity/output fields and the language selector", () => {
    const html = renderTab()
    expect(html).toContain("Studio User ID")
    expect(html).toContain("Gitea Host")
    expect(html).toContain("Default skill folder")
    // #15.1 language dropdown is present today (i18n-only); persistence deferred.
    expect(html).toContain('aria-label="Studio language"')
  })
})
