import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it, vi } from "vitest"
import { ProviderCard, apiKeyInputClassName } from "./ProviderCard"
import type { ProviderDraft } from "../SettingsPage"

const draft: ProviderDraft = {
  id: "p1",
  name: "OpenAI",
  api_key: "sk-secret-123",
  base_url: "",
  provider_type: "openai_compatible",
  isTesting: false,
}

describe("ProviderCard API key masking", () => {
  it("renders API key as masked text input by default", () => {
    const html = renderToStaticMarkup(
      <ProviderCard
        draft={draft}
        persisted={null}
        onFieldChange={vi.fn()}
        onTest={vi.fn()}
        onDelete={vi.fn()}
      />,
    )

    expect(html).toContain('type="text"')
    expect(html).toContain('value="sk-secret-123"')
    expect(html).toContain("mask-input")
    expect(html).toContain('name="provider-secret-p1"')
    expect(html).toContain('data-1p-ignore=""')
    expect(html).toContain('data-lpignore="true"')
    expect(html).toContain('data-form-type="other"')
    expect(html).toContain('aria-label="Show API key"')
    expect(html).toContain("transition-none")
    expect(html).toContain("px-6")
  })

  it("visibility toggle changes only mask class and does not mutate draft api key", () => {
    const onFieldChange = vi.fn()
    const hiddenClassName = apiKeyInputClassName(false)
    const visibleClassName = apiKeyInputClassName(true)

    expect(hiddenClassName).toContain("mask-input")
    expect(visibleClassName).not.toContain("mask-input")
    expect(onFieldChange).not.toHaveBeenCalled()
    expect(draft.api_key).toBe("sk-secret-123")
  })
})
