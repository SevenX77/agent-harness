import { describe, expect, it } from "vitest"
import { REDACTED_ENDPOINT_SECRET, type CredentialsState } from "../../../api/llm"
import { reconcileDraftsWithCredentials } from "./SettingsPage"
import { draftFromAddProviderSubmission } from "./provider-utils"

// Regression: adding one third-party provider must not render TWO identical
// cards. The add-flow mints a local draft id `custom-<uuid>`; the backend
// persists it under a URL-stable id (`{url-slug}-{protocol}-{hash}`) and its
// registry response redacts every api_key — so NEITHER the id NOR the api_key
// of the local draft ever matches the reconciled server copy. Provider identity
// for the merge is therefore the NAME alone (AddProviderForm rejects duplicate
// names, so the name is the third-party card's identity per the settings UX
// spec 确认②: the registry has no "card" concept).
describe("reconcileDraftsWithCredentials — no duplicate card after adding a provider", () => {
  function credentialsWith(providers: CredentialsState["providers"]): CredentialsState {
    return { providers } as CredentialsState
  }

  it("collapses the just-added local draft into its persisted (URL-stable, redacted) form", () => {
    const localDraft = draftFromAddProviderSubmission({
      providerCode: "custom-abc",
      name: "aaaaaaa",
      baseUrl: "12341234",
      apiKey: "1234123",
      type: "third-party",
    })
    expect(localDraft.id).toBe("custom-abc")

    // What the backend actually returns after the PUT: three sibling protocol
    // records under server-minted URL-stable ids, api_key redacted.
    const credentials = credentialsWith([
      {
        id: "12341234-openai-223fdbfc58",
        name: "aaaaaaa",
        api_key: REDACTED_ENDPOINT_SECRET,
        base_url: "12341234",
        provider_type: "openai_compatible",
      },
      {
        id: "12341234-anthropic-99316aafcb",
        name: "aaaaaaa",
        api_key: REDACTED_ENDPOINT_SECRET,
        base_url: "12341234",
        provider_type: "anthropic_compatible",
      },
      {
        id: "12341234-google-afab7d4812",
        name: "aaaaaaa",
        api_key: REDACTED_ENDPOINT_SECRET,
        base_url: "12341234",
        provider_type: "google_genai",
      },
    ])

    const dirtyIds = new Set(["custom-abc"])
    const result = reconcileDraftsWithCredentials(
      credentials,
      [localDraft],
      dirtyIds,
      new Set(),
    )

    expect(result.filter((draft) => draft.name === "aaaaaaa")).toHaveLength(1)
    // The merged-away local id can never reappear in credentials — its dirty
    // marker must not leak forever.
    expect(dirtyIds.has("custom-abc")).toBe(false)
  })

  it("collapses the local draft when the backend keeps a protocol-suffixed variant of its id", () => {
    const localDraft = draftFromAddProviderSubmission({
      providerCode: "custom-abc",
      name: "OpenRouter",
      baseUrl: "https://openrouter.ai/api",
      apiKey: "sk-or",
      type: "third-party",
    })

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

  it("keeps a genuinely-unsaved provider whose name is not yet in credentials", () => {
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
})
