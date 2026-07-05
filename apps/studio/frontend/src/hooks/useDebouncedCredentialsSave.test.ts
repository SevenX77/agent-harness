// @vitest-environment jsdom
import { act, createElement, useEffect, type ReactNode } from "react"
import { createRoot, type Root } from "react-dom/client"
import { afterEach, describe, expect, it, vi } from "vitest"
import type { CredentialsState, ProviderCredentialUpdate } from "@/api/llm"
import { buildPutPayload, useDebouncedCredentialsSave } from "./useDebouncedCredentialsSave"

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

vi.mock("sonner", () => ({
  toast: {
    error: vi.fn(),
  },
}))

function renderJsx(node: ReactNode): { container: HTMLDivElement; root: Root } {
  const container = document.createElement("div")
  document.body.appendChild(container)
  const root = createRoot(container)
  act(() => {
    root.render(node)
  })
  return { container, root }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

function sampleCredential(id: string): ProviderCredentialUpdate {
  return {
    id,
    name: id,
    api_key: `sk-${id}`,
    base_url: "",
    provider_type: null,
  }
}

function sampleCredentialsState(id: string): CredentialsState {
  return {
    providers: [
      {
        id,
        name: id,
        api_key: `sk-${id}`,
        base_url: "",
        provider_type: null,
      },
    ],
  } as unknown as CredentialsState
}

afterEach(() => {
  vi.useRealTimers()
  document.body.innerHTML = ""
  vi.clearAllMocks()
})

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
      // @ts-expect-error — last_test_status is intentionally not in the input type
      // but may leak in via spread; confirm it gets stripped so the PUT
      // doesn't trip backend's extra="forbid".
      { id: "AAA", name: "Alpha", api_key: "sk", last_test_status: "ok" },
    ])
    expect(result[0]).not.toHaveProperty("last_test_status")
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

  it("expands each third-party base URL row into protocol-specific endpoints", () => {
    const result = buildPutPayload([
      {
        id: "qiniu-openai",
        name: "Qiniu",
        api_key: "sk-qiniu",
        base_urls: [{
          id: "qiniu-openai",
          value: "https://api.qnaigc.com/v1",
          endpoint_ids: { openai_compatible: "qiniu-openai" },
        }],
      },
    ])

    expect(result).toEqual([
      {
        id: "qiniu-openai",
        name: "Qiniu",
        api_key: "sk-qiniu",
        base_url: "https://api.qnaigc.com/v1",
        provider_type: "openai_compatible",
      },
      {
        id: "qiniu-openai-anthropic",
        name: "Qiniu",
        api_key: "sk-qiniu",
        base_url: "https://api.qnaigc.com/v1",
        provider_type: "anthropic_compatible",
      },
      {
        id: "qiniu-openai-google",
        name: "Qiniu",
        api_key: "sk-qiniu",
        base_url: "https://api.qnaigc.com/v1",
        provider_type: "google_genai",
      },
    ])
  })

  it("uses canonical official endpoint identities even when a draft carries stale endpoint_ids", () => {
    const result = buildPutPayload([
      {
        id: "ark-official",
        name: "Ark Official",
        api_key: "volc-key",
        base_url: "https://ark.cn-beijing.volces.com/api/v3",
        provider_type: "ark_runtime",
        base_urls: [{
          id: "ark-official",
          value: "https://ark.cn-beijing.volces.com/api/v3",
          provider_type: "ark_runtime",
          endpoint_ids: {
            ark_runtime: "ark-official",
            openai_compatible: "ark-official",
          },
        }],
      },
    ])

    expect(result).toEqual([
      {
        id: "ark-official",
        name: "Ark Official",
        api_key: "volc-key",
        base_url: "https://ark.cn-beijing.volces.com/api/v3",
        provider_type: "ark_runtime",
      },
      {
        id: "ark-openai-official",
        name: "Ark Official",
        api_key: "volc-key",
        base_url: "https://ark.cn-beijing.volces.com/api/v3",
        provider_type: "openai_compatible",
      },
    ])
  })
})

describe("useDebouncedCredentialsSave", () => {
  it("keeps only the newest queued credentials payload while an older save is in flight", async () => {
    vi.useFakeTimers()
    const first = deferred<CredentialsState>()
    const second = deferred<CredentialsState>()
    const putFn = vi.fn<(updates: ProviderCredentialUpdate[]) => Promise<CredentialsState>>()
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise)
    const onSaved = vi.fn()
    let hook: ReturnType<typeof useDebouncedCredentialsSave> | null = null

    function Harness() {
      const result = useDebouncedCredentialsSave({ delayMs: 20, putFn, onSaved })
      useEffect(() => {
        hook = result
      })
      return null
    }

    const { root } = renderJsx(createElement(Harness))

    act(() => {
      hook?.queue(() => [sampleCredential("first")])
      vi.advanceTimersByTime(20)
    })
    expect(putFn).toHaveBeenCalledTimes(1)
    expect(putFn.mock.calls[0]?.[0].map((item) => item.id)).toEqual(["first"])

    act(() => {
      hook?.queue(() => [sampleCredential("stale-second")])
      hook?.queue(() => [sampleCredential("latest-second")])
    })
    expect(putFn).toHaveBeenCalledTimes(1)

    await act(async () => {
      first.resolve(sampleCredentialsState("first"))
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(onSaved).not.toHaveBeenCalled()
    expect(putFn).toHaveBeenCalledTimes(2)
    expect(putFn.mock.calls[1]?.[0].map((item) => item.id)).toEqual(["latest-second"])

    await act(async () => {
      second.resolve(sampleCredentialsState("latest-second"))
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(onSaved).toHaveBeenCalledTimes(1)
    expect(onSaved).toHaveBeenCalledWith(sampleCredentialsState("latest-second"))

    act(() => root.unmount())
  })
})
