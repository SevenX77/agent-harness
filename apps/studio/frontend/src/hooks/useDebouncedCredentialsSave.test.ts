import { describe, expect, it } from "vitest"
import { buildPutPayload } from "./useDebouncedCredentialsSave"

/**
 * Only `buildPutPayload` is unit-tested here — it is pure and is the most
 * error-prone surface (must mirror the backend's `ProviderCredentialWrite`
 * `extra="forbid"` shape exactly, otherwise PUT 422s).
 *
 * The hook itself (debouncing, in-flight coalescing, status transitions) is
 * exercised end-to-end via the Playwright smoke that drives the live
 * SettingsPage. Reproducing it in jsdom would need `@testing-library/react`,
 * which is not currently a project dependency.
 */
describe("buildPutPayload", () => {
  it("emits editable fields with empty-string defaults for unset ones", () => {
    const result = buildPutPayload([
      { id: "AAA", name: "Alpha", api_key: "sk-xxx" },
      { id: "BBB", name: "Beta", api_key: "", provider_type: "openai_compatible" },
    ])
    expect(result).toEqual([
      { id: "AAA", name: "Alpha", api_key: "sk-xxx", base_url: "", provider_type: null },
      { id: "BBB", name: "Beta", api_key: "", base_url: "", provider_type: "openai_compatible" },
    ])
  })

  it("ignores fields not part of ProviderCredentialUpdate", () => {
    const result = buildPutPayload([
      // @ts-expect-error — has_key is intentionally not in the input type
      // but may leak in via spread; confirm it gets stripped so the PUT
      // doesn't trip backend's extra="forbid".
      { id: "AAA", name: "Alpha", api_key: "sk", has_key: true },
    ])
    expect(result[0]).not.toHaveProperty("has_key")
    expect(Object.keys(result[0]).sort()).toEqual([
      "api_key",
      "base_url",
      "id",
      "name",
      "provider_type",
    ])
  })

  it("preserves an explicit null provider_type (used to clear the field server-side)", () => {
    const result = buildPutPayload([
      { id: "AAA", name: "Alpha", api_key: "sk", provider_type: null },
    ])
    expect(result[0].provider_type).toBeNull()
  })
})
