// @vitest-environment jsdom
import { act, createElement } from "react"
import { createRoot, type Root } from "react-dom/client"
import useSWR, { SWRConfig } from "swr"
import type { Cache } from "swr"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { STUDIO_TRUTH_SWR_CONFIG } from "./studio-swr-policy"

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const fetcher = vi.fn()

function HookHost({ enabled }: { enabled: boolean }): null {
  useSWR(enabled ? "truth/settings" : null, fetcher)
  return null
}

describe("STUDIO_TRUTH_SWR_CONFIG", () => {
  let container: HTMLDivElement
  let root: Root
  let cache: Cache

  beforeEach(() => {
    fetcher.mockReset()
    fetcher.mockResolvedValue({ ok: true })
    cache = new Map()
    container = document.createElement("div")
    document.body.appendChild(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => {
      root.unmount()
    })
    container.remove()
  })

  it("loads uncached truth once and ignores focus, reconnect, and stale remounts", async () => {
    await act(async () => {
      root.render(
        createElement(
          SWRConfig,
          {
            value: {
              provider: () => cache,
              dedupingInterval: 0,
              focusThrottleInterval: 0,
              ...STUDIO_TRUTH_SWR_CONFIG,
            },
          },
          createElement(HookHost, { enabled: true }),
        ),
      )
    })
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(fetcher).toHaveBeenCalledTimes(1)
    fetcher.mockClear()

    act(() => {
      window.dispatchEvent(new Event("focus"))
      window.dispatchEvent(new Event("online"))
    })
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(fetcher).not.toHaveBeenCalled()

    await act(async () => {
      root.render(
        createElement(
          SWRConfig,
          {
            value: {
              provider: () => cache,
              dedupingInterval: 0,
              focusThrottleInterval: 0,
              ...STUDIO_TRUTH_SWR_CONFIG,
            },
          },
          createElement(HookHost, { enabled: false }),
        ),
      )
    })
    await act(async () => {
      root.render(
        createElement(
          SWRConfig,
          {
            value: {
              provider: () => cache,
              dedupingInterval: 0,
              focusThrottleInterval: 0,
              ...STUDIO_TRUTH_SWR_CONFIG,
            },
          },
          createElement(HookHost, { enabled: true }),
        ),
      )
    })
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(fetcher).not.toHaveBeenCalled()
  })
})
