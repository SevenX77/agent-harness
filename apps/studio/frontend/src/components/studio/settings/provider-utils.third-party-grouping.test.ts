import { describe, expect, it } from "vitest"
import { REDACTED_ENDPOINT_SECRET, type CredentialsState } from "../../../api/llm"
import { draftsFromCredentials, thirdPartyProviderDrafts } from "./provider-utils"

// Regression (2026-08-19): one third-party provider rendered as TWO cards on a
// cold load. The registry read-back is 3 sibling endpoint records per provider
// (one per probed protocol) whose `api_key` fields are NOT a stable identity:
// a record with a stored secret reads back as the redaction placeholder while
// a sibling without one reads back empty — grouping by name+api_key split the
// same provider into two cards. Per the settings UX spec (00_settings-ux-spec.md
// 确认②), the registry has no "card" concept: the card is a frontend authoring
// convenience whose identity is the provider NAME (AddProviderForm rejects
// duplicate names), so grouping keys on the name alone.
describe("draftsFromCredentials — one third-party card per provider name", () => {
  function credentialsWith(providers: CredentialsState["providers"]): CredentialsState {
    return { providers } as CredentialsState
  }

  it("keeps sibling protocol records in ONE card even when api_key read-back differs", () => {
    const credentials = credentialsWith([
      {
        id: "api-jiekou-ai-anthropic-openai-32f687cbee",
        name: "Jiekou",
        api_key: REDACTED_ENDPOINT_SECRET,
        base_url: "https://api.jiekou.ai/anthropic",
        provider_type: "openai_compatible",
      },
      {
        id: "api-jiekou-ai-anthropic-anthropic-5565f497d8",
        name: "Jiekou",
        api_key: REDACTED_ENDPOINT_SECRET,
        base_url: "https://api.jiekou.ai/anthropic",
        provider_type: "anthropic_compatible",
      },
      // A sibling persisted WITHOUT a secret (e.g. created by an upsert that
      // could not resolve the redacted key) reads back with an empty api_key.
      {
        id: "api-jiekou-ai-anthropic-google-5ae8a94fb4",
        name: "Jiekou",
        api_key: "",
        base_url: "https://api.jiekou.ai/anthropic",
        provider_type: "google_genai",
      },
    ])

    const cards = thirdPartyProviderDrafts(draftsFromCredentials(credentials))

    expect(cards).toHaveLength(1)
    // The card's key comes from the sibling that HAS one, so the field does not
    // render empty just because the keyless sibling happened to sort first.
    expect(cards[0].api_key).toBe(REDACTED_ENDPOINT_SECRET)
    expect(cards[0].base_urls?.map((row) => row.value)).toEqual(["https://api.jiekou.ai/anthropic"])
  })

  it("takes the card api_key from the first sibling with one, regardless of record order", () => {
    const credentials = credentialsWith([
      {
        id: "example-google-1",
        name: "Example",
        api_key: "",
        base_url: "https://example.test",
        provider_type: "google_genai",
      },
      {
        id: "example-openai-1",
        name: "Example",
        api_key: REDACTED_ENDPOINT_SECRET,
        base_url: "https://example.test",
        provider_type: "openai_compatible",
      },
    ])

    const cards = thirdPartyProviderDrafts(draftsFromCredentials(credentials))

    expect(cards).toHaveLength(1)
    expect(cards[0].api_key).toBe(REDACTED_ENDPOINT_SECRET)
  })
})
