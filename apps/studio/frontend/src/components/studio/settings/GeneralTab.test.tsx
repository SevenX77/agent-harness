import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it, vi } from "vitest"
import { GeneralTab, TruthSourcesPanel, formatChangeValue } from "./GeneralTab"
import type { TruthSourceSection } from "@/api/client"
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
 * #15.1 (language persistence into app_settings) is now wired: the language
 * dropdown is bound to `appSettings.language` (the persisted value) and, on
 * change, both drives `i18n.changeLanguage` and persists via
 * `appSettings.setLanguage` (the two-call behaviour is unit-tested in
 * `language-switch.test.ts`). Here we lock the render contract: the dropdown is
 * present and reflects the persisted language value.
 */

type AppSettingsProp = SettingsPageContentProps["appSettings"]

function makeAppSettings(overrides: Partial<AppSettingsProp> = {}): AppSettingsProp {
  return {
    userId: "alice",
    giteaHost: "https://gitea.example.com",
    defaultSkillsDirectory: "/Users/alice/AgentStudio/Skills",
    language: "en",
    remoteModelCatalogEnabled: true,
    isLoading: false,
    saveStatus: "saved",
    setUserId: vi.fn(),
    setGiteaHost: vi.fn(),
    setDefaultSkillsDirectory: vi.fn(),
    setLanguage: vi.fn(),
    setRemoteModelCatalogEnabled: vi.fn(),
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

  it("never disables the editable inputs on loading (the shell renders GeneralTabSkeleton instead)", () => {
    // B fix: General no longer disables its whole form while appSettings load —
    // SettingsPageContent shows GeneralTabSkeleton during isLoading, consistent
    // with the other tabs. So whenever GeneralTab itself renders, its inputs are
    // editable regardless of the (incidental) isLoading flag value.
    const html = renderTab({ isLoading: true })
    expect(inputTag(html, "studio-user-id")).not.toContain('disabled=""')
    expect(inputTag(html, "gitea-host")).not.toContain('disabled=""')
    expect(inputTag(html, "default-skill-folder")).not.toContain('disabled=""')
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
    // #15.1 language dropdown is wired to persisted appSettings.language.
    expect(html).toContain('aria-label="Studio language"')
  })

  it("#15.1 binds the language selector for the persisted language value", () => {
    // Radix Select renders the chosen label and its options client-side / in a
    // portal (the static select-value span is empty and SelectContent is not in
    // static markup), so neither the selected text nor the option labels can be
    // asserted from renderToStaticMarkup. What we can lock here: the language
    // trigger mounts (bound by id + aria-label) for either persisted value — i.e.
    // the persisted `appSettings.language` drives the control without throwing.
    // The change-time two-call behaviour is unit-tested in language-switch.test.ts.
    for (const language of ["en", "zh-CN"] as const) {
      const html = renderTab({ language })
      expect(html).toContain('id="studio-language"')
      expect(html).toContain('aria-label="Studio language"')
      expect(html).toContain("Switch Studio UI copy without restarting the app.")
    }
  })

  it("renders the remote model catalog switch using the local shadcn switch primitive", () => {
    const html = renderTab({ remoteModelCatalogEnabled: true })
    expect(html).toContain("Community model catalog")
    expect(html).toContain(
      "Download the verified community catalog for local route evidence and allow sanitized successful probe evidence to be contributed back. Turn off to stop both read and contribute paths.",
    )
    expect(html).toContain('data-slot="switch"')
    expect(html).toContain('aria-label="Community model catalog"')
  })

  it("renders grouped runtime truth sources with paths and recent logs", () => {
    const sections: TruthSourceSection[] = [
      {
        id: "llm_runtime",
        label: "LLM runtime truth",
        description: "Credential and route stores.",
        sources: [
          {
            id: "llm_credentials",
            label: "LLM credentials",
            path: "C:\\Users\\test\\AppData\\Roaming\\AgentStudio\\llm\\llm_credentials.json",
            kind: "json",
            description: "Credential truth.",
            open_mode: "file",
            exists: true,
            size_bytes: 2048,
            updated_at: "2026-06-28T11:45:00+08:00",
            can_preview: true,
            logs: [
              {
                id: "log-1",
                recorded_at: "2026-06-28T11:46:10+08:00",
                source_id: "llm_credentials",
                action: "endpoint_test",
                message: "Saved endpoint test result and applied matching cached community evidence.",
                changes: {
                  endpoint_id: "deepseek-official",
                  promoted_catalog_records: 2,
                },
              },
            ],
          },
        ],
      },
    ]

    const html = renderToStaticMarkup(
      <TruthSourcesPanel sections={sections} onOpenSource={vi.fn()} />,
    )

    expect(html).toContain("LLM credentials")
    expect(html).toContain("llm_credentials.json")
    expect(html).toContain("Runtime log (1)")
    expect(html).toContain("endpoint_test")
    expect(html).toContain('data-state="closed"')
    expect(html).not.toContain("promoted_catalog_records")
  })
})

describe("formatChangeValue — runtime-log detail rendering", () => {
  // PM 2026-07-03 (point 3): endpoint_test entries DO record probe_attempts
  // (model / protocol / status), but they used to render as a raw
  // JSON.stringify blob, so the log read as "no detail". Nested objects/arrays
  // must render as readable key:value lines instead.
  it("renders an array of probe-attempt objects as readable key:value lines, not a JSON blob", () => {
    const out = formatChangeValue([
      { model: "anthropic/claude-haiku-4.5", protocol: "anthropic_compatible", status: "ok" },
    ])
    expect(out).not.toContain('{"')
    expect(out).not.toContain('"model"')
    expect(out).toContain("model: anthropic/claude-haiku-4.5")
    expect(out).toContain("protocol: anthropic_compatible")
    expect(out).toContain("status: ok")
  })

  it("renders each object in a multi-attempt array on its own line", () => {
    const out = formatChangeValue([
      { status: "invalid_model", latency_ms: 527, message: "HTTP 404" },
      { status: "ok", latency_ms: 210 },
    ])
    const lines = out.split("\n")
    expect(lines.length).toBe(2)
    expect(lines[0]).toContain("status: invalid_model")
    expect(lines[0]).toContain("latency_ms: 527")
    expect(lines[1]).toContain("status: ok")
  })

  it("still renders a from/to diff object with an arrow", () => {
    expect(formatChangeValue({ from: "untested", to: "verified" })).toBe("untested -> verified")
  })

  it("collapses empty arrays and null/undefined to a dash", () => {
    expect(formatChangeValue([])).toBe("-")
    expect(formatChangeValue(null)).toBe("-")
    expect(formatChangeValue(undefined)).toBe("-")
    expect(formatChangeValue({})).toBe("-")
  })

  it("passes primitives through as strings", () => {
    expect(formatChangeValue("verified")).toBe("verified")
    expect(formatChangeValue(66)).toBe("66")
    expect(formatChangeValue(true)).toBe("true")
  })
})
