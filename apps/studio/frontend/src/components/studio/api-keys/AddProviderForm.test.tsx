import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it, vi } from "vitest"
import {
  AddProviderForm,
  addProviderNameError,
  createBlankAddProviderSubmission,
  deriveAddProviderFormSubmission,
  providerCodeFromCustomName,
} from "./AddProviderForm"

describe("AddProviderForm", () => {
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

  it("creates a blank third-party submission so Add Provider immediately inserts a normal card", () => {
    const uuid = vi.spyOn(globalThis.crypto, "randomUUID").mockReturnValue("00000000-0000-4000-8000-000000000001")

    expect(createBlankAddProviderSubmission()).toEqual({
      providerCode: "custom-00000000-0000-4000-8000-000000000001",
      name: "New Provider",
      baseUrl: "",
      apiKey: "",
      type: "third-party",
    })

    uuid.mockRestore()
  })
})

describe("addProviderNameError", () => {
  it("requires a non-empty name", () => {
    expect(addProviderNameError("   ", [])).toBe("Provider name is required.")
  })

  it("rejects a duplicate name (case/space-insensitive)", () => {
    expect(addProviderNameError(" My OpenRouter ", ["my openrouter"])).toBe(
      "A provider with this name already exists.",
    )
  })

  it("accepts a unique non-empty name", () => {
    expect(addProviderNameError("Fresh Provider", ["My OpenRouter"])).toBeNull()
  })
})

describe("AddProviderForm component (atom-19 one-step inline form)", () => {
  function renderForm(): string {
    return renderToStaticMarkup(
      <AddProviderForm existingNames={[]} onSubmit={() => {}} onCancel={() => {}} />,
    )
  }

  it("renders a single inline form with name, base_url and api_key inputs", () => {
    const html = renderForm()
    expect(html).toContain('data-add-provider-form="true"')
    expect(html).toContain('id="add-provider-name"')
    expect(html).toContain('id="add-provider-base-url"')
    expect(html).toContain('id="add-provider-api-key"')
    expect(html).toContain('data-add-provider-submit="true"')
  })

  it("keeps the empty api_key placeholder readable while still using type=text", () => {
    const html = renderForm()
    const apiKeyInput = html.match(/<input[^>]*id="add-provider-api-key"[^>]*>/)
    expect(apiKeyInput).not.toBeNull()
    expect(apiKeyInput?.[0]).toContain('type="text"')
    expect(apiKeyInput?.[0]).toContain('placeholder="Enter the provider API Key"')
    expect(apiKeyInput?.[0]).not.toContain("mask-input")
    expect(apiKeyInput?.[0]).not.toContain('type="password"')
  })
})
