import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it, vi } from "vitest"
import {
  AddProviderForm,
  canSubmitAddProviderForm,
  deriveAddProviderFormSubmission,
  providerCodeFromCustomName,
} from "./AddProviderForm"

describe("AddProviderForm", () => {
  it("renders the collapsed third-party form fields", () => {
    const html = renderToStaticMarkup(<AddProviderForm onSubmit={vi.fn()} onCancel={vi.fn()} />)

    expect(html).toContain('data-testid="add-provider-form"')
    expect(html).toContain("Provider Name")
    expect(html).toContain("Base URL")
    expect(html).toContain("API Key")
    expect(html).toContain("Cancel")
    expect(html).toContain("Add")
    expect(html).not.toContain("Official Provider")
    expect(html).not.toContain("Third-party Provider")
    expect(html).not.toContain("选择官方厂商...")
  })

  it("derives third-party provider code from custom name", () => {
    expect(providerCodeFromCustomName("My OpenRouter")).toBe("my-openrouter")
  })

  it("derives submit payload for a third-party provider", () => {
    const submission = deriveAddProviderFormSubmission({
      customName: "My OpenRouter",
      customBaseUrl: "https://openrouter.ai/api/v1",
      apiKey: "sk-test",
    })

    expect(submission).toEqual({
      providerCode: "my-openrouter",
      name: "My OpenRouter",
      baseUrl: "https://openrouter.ai/api/v1",
      apiKey: "sk-test",
      type: "third-party",
    })
  })

  it("disables submit until apiKey plus required provider fields are present", () => {
    expect(canSubmitAddProviderForm({
      customName: "",
      customBaseUrl: "",
      apiKey: "sk-test",
    })).toBe(false)
    expect(canSubmitAddProviderForm({
      customName: "My OpenRouter",
      customBaseUrl: "https://openrouter.ai/api/v1",
      apiKey: "",
    })).toBe(false)
    expect(canSubmitAddProviderForm({
      customName: "My OpenRouter",
      customBaseUrl: "",
      apiKey: "sk-test",
    })).toBe(false)
    expect(canSubmitAddProviderForm({
      customName: "My OpenRouter",
      customBaseUrl: "https://openrouter.ai/api/v1",
      apiKey: "sk-test",
    })).toBe(true)
  })

  it("API key input defaults to masked text with password-manager suppression attributes", () => {
    const html = renderToStaticMarkup(<AddProviderForm onSubmit={vi.fn()} onCancel={vi.fn()} />)

    expect(html).toContain('type="text"')
    expect(html).toContain("mask-input")
    expect(html).toContain('aria-label="Show API key"')
    expect(html).toContain('autoComplete="off"')
    expect(html).toContain('data-1p-ignore=""')
    expect(html).toContain('data-lpignore="true"')
    expect(html).toContain('data-form-type="other"')
  })
})
