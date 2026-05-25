import { describe, expect, it } from "vitest"
import { buildEndpointUpsertPayload } from "./useDebouncedCredentialsSave"

type EndpointInput = Parameters<typeof buildEndpointUpsertPayload>[0][number]

/**
 * Only the request builder is unit-tested here — it is pure and is the most
 * error-prone surface (must mirror the backend's endpoint upsert shape exactly,
 * otherwise PUT 422s).
 *
 * The hook itself (debouncing, in-flight coalescing, status transitions) is
 * exercised end-to-end via the Playwright smoke that drives the live
 * SettingsPage. Reproducing it in jsdom would need `@testing-library/react`,
 * which is not currently a project dependency.
 */
describe("buildEndpointUpsertPayload", () => {
  it("keys endpoint upserts by endpoint_id and emits only endpoint fields", () => {
    const endpoint = {
      endpoint_id: "anthropic-official",
      display_name: "Anthropic",
      protocol: "anthropic_compatible",
      base_url: "https://api.anthropic.com",
      api_key: "sk-xxx",
      status: "verified",
      timeout_seconds: 60,
      trust_env: false,
      proxy_env: null,
      metadata: { vendor: "anthropic" },
      last_test_at: "2026-05-24T00:00:00Z",
      last_test_message: "ok",
    } satisfies EndpointInput & {
      last_test_at: string
      last_test_message: string
    }

    const result = buildEndpointUpsertPayload([
      endpoint,
    ])
    expect(result).toEqual({
      "anthropic-official": {
        endpoint_id: "anthropic-official",
        display_name: "Anthropic",
        protocol: "anthropic_compatible",
        base_url: "https://api.anthropic.com",
        api_key: "sk-xxx",
        status: "verified",
        timeout_seconds: 60,
        trust_env: false,
        proxy_env: null,
        metadata: { vendor: "anthropic" },
      },
    })
  })

  it("normalizes optional secret/proxy fields without forwarding route or test state", () => {
    const endpoint = {
      endpoint_id: "openai-main",
      display_name: "OpenAI",
      protocol: "openai_compatible",
      base_url: "",
      status: "unverified_manual",
      timeout_seconds: 30,
      trust_env: true,
      metadata: {},
      provider_routes: {},
      last_test_message: "ignored",
    } satisfies EndpointInput & {
      provider_routes: Record<string, unknown>
      last_test_message: string
    }

    const result = buildEndpointUpsertPayload([
      endpoint,
    ])
    expect(result["openai-main"]).not.toHaveProperty("provider_routes")
    expect(result["openai-main"]).not.toHaveProperty("last_test_message")
    expect(result["openai-main"].api_key).toBeNull()
    expect(result["openai-main"].proxy_env).toBeNull()
    expect(Object.keys(result["openai-main"]).sort()).toEqual([
      "api_key",
      "base_url",
      "display_name",
      "endpoint_id",
      "metadata",
      "protocol",
      "proxy_env",
      "status",
      "timeout_seconds",
      "trust_env",
    ])
  })

  it("preserves empty api_key as an explicit backend no-op secret update", () => {
    const result = buildEndpointUpsertPayload([
      {
        endpoint_id: "openrouter-main",
        display_name: "OpenRouter",
        protocol: "openai_compatible",
        base_url: "https://openrouter.ai/api/v1",
        api_key: "",
        status: "unverified_manual",
        timeout_seconds: 45,
        trust_env: false,
        proxy_env: "",
        metadata: {},
      },
    ])
    expect(result["openrouter-main"].api_key).toBe("")
    expect(result["openrouter-main"].proxy_env).toBe("")
  })
})
