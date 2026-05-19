import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it, vi } from "vitest"
import {
  AddProviderForm,
  canSubmitAddProviderForm,
  deriveAddProviderFormSubmission,
  providerCodeFromCustomName,
} from "./AddProviderForm"
import { OFFICIAL_VENDORS } from "./OfficialVendorSelect"

describe("AddProviderForm", () => {
  it("renders official mode by default with vendor select", () => {
    const html = renderToStaticMarkup(<AddProviderForm onSubmit={vi.fn()} onCancel={vi.fn()} />)

    expect(html).toContain('data-testid="add-provider-form"')
    expect(html).toContain("Official Provider")
    expect(html).toContain("Third-party Provider")
    expect(html).toContain("选择官方厂商...")
    expect(html).toContain("Provider Name")
    expect(html).toContain("Base URL")
  })

  it("derives third-party provider code from custom name", () => {
    expect(providerCodeFromCustomName("My OpenRouter")).toBe("my-openrouter")
  })

  it("auto-fills official name and base URL from selected vendor", () => {
    const anthropic = OFFICIAL_VENDORS.find((vendor) => vendor.code === "anthropic")!
    const submission = deriveAddProviderFormSubmission({
      type: "official",
      vendor: anthropic,
      customName: "",
      customBaseUrl: "",
      apiKey: "sk-test",
    })

    expect(submission).toEqual({
      providerCode: "anthropic",
      name: "Anthropic-Official",
      baseUrl: "https://api.anthropic.com",
      apiKey: "sk-test",
      type: "official",
    })
  })

  it("disables submit until apiKey plus required provider fields are present", () => {
    const anthropic = OFFICIAL_VENDORS.find((vendor) => vendor.code === "anthropic")!

    expect(canSubmitAddProviderForm({
      type: "official",
      vendor: null,
      customName: "",
      customBaseUrl: "",
      apiKey: "sk-test",
    })).toBe(false)
    expect(canSubmitAddProviderForm({
      type: "official",
      vendor: anthropic,
      customName: "",
      customBaseUrl: "",
      apiKey: "sk-test",
    })).toBe(true)
    expect(canSubmitAddProviderForm({
      type: "third-party",
      vendor: null,
      customName: "My OpenRouter",
      customBaseUrl: "",
      apiKey: "sk-test",
    })).toBe(false)
    expect(canSubmitAddProviderForm({
      type: "third-party",
      vendor: null,
      customName: "My OpenRouter",
      customBaseUrl: "https://openrouter.ai/api/v1",
      apiKey: "sk-test",
    })).toBe(true)
  })

  it("derives submit payload for official provider", () => {
    const deepseek = OFFICIAL_VENDORS.find((vendor) => vendor.code === "deepseek")!

    expect(deriveAddProviderFormSubmission({
      type: "official",
      vendor: deepseek,
      customName: "",
      customBaseUrl: "",
      apiKey: "sk-deep",
    })).toEqual({
      providerCode: "deepseek",
      name: "DeepSeek-Official",
      baseUrl: "https://api.deepseek.com",
      apiKey: "sk-deep",
      type: "official",
    })
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
