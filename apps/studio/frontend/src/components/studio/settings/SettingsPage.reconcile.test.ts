import { describe, expect, it } from "vitest"
import type { CredentialsState } from "../../../api/llm"
import { reconcileDraftsWithCredentials } from "./SettingsPage"
import { draftFromAddProviderSubmission } from "./provider-utils"

// Regression: adding one third-party provider must not render TWO identical
// cards. The add-flow mints a local draft id `custom-abc`; the backend persists
// it under a protocol-suffixed id (`custom-abc-<protocol>`); reconcile used to
// keep BOTH (id-only "not persisted yet" check), producing a duplicate card.
describe("reconcileDraftsWithCredentials — no duplicate card after adding a provider", () => {
  function credentialsWith(providers: CredentialsState["providers"]): CredentialsState {
    return { providers } as CredentialsState
  }

  it("collapses the just-added local draft into its persisted (protocol-suffixed) form", () => {
    const localDraft = draftFromAddProviderSubmission({
      providerCode: "custom-abc",
      name: "OpenRouter",
      baseUrl: "https://openrouter.ai/api",
      apiKey: "sk-or",
      type: "third-party",
    })
    expect(localDraft.id).toBe("custom-abc")

    const credentials = credentialsWith([
      {
        id: "custom-abc-openai_compatible",
        name: "OpenRouter",
        api_key: "sk-or",
        base_url: "https://openrouter.ai/api",
        provider_type: "openai_compatible",
      },
    ])

    const result = reconcileDraftsWithCredentials(
      credentials,
      [localDraft],
      new Set(["custom-abc"]),
      new Set(),
    )

    expect(result.filter((draft) => draft.name === "OpenRouter")).toHaveLength(1)
  })

  it("keeps a genuinely-unsaved provider whose identity is not yet in credentials", () => {
    const localDraft = draftFromAddProviderSubmission({
      providerCode: "custom-xyz",
      name: "Fresh Co",
      baseUrl: "https://fresh.example/api",
      apiKey: "sk-fresh",
      type: "third-party",
    })

    const result = reconcileDraftsWithCredentials(
      credentialsWith([]),
      [localDraft],
      new Set(["custom-xyz"]),
      new Set(),
    )

    expect(result.filter((draft) => draft.name === "Fresh Co")).toHaveLength(1)
  })

  it("does not merge two DIFFERENT providers that share a name but differ by api_key", () => {
    const a = draftFromAddProviderSubmission({
      providerCode: "custom-a",
      name: "OpenRouter",
      baseUrl: "https://openrouter.ai/api",
      apiKey: "sk-a",
      type: "third-party",
    })
    const credentials = credentialsWith([
      {
        id: "custom-b-openai_compatible",
        name: "OpenRouter",
        api_key: "sk-b",
        base_url: "https://openrouter.ai/api",
        provider_type: "openai_compatible",
      },
    ])

    const result = reconcileDraftsWithCredentials(
      credentials,
      [a],
      new Set(["custom-a"]),
      new Set(),
    )

    // Different api_key => different provider identity => both survive.
    expect(result.filter((draft) => draft.name === "OpenRouter")).toHaveLength(2)
  })
})
