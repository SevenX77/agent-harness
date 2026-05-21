import { describe, expect, it, vi } from "vitest"
import {
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
