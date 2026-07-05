// @vitest-environment jsdom
import { act, createElement } from "react"
import { createRoot, type Root } from "react-dom/client"
import { SWRConfig } from "swr"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { useTemplates } from "./useTemplates"

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const mocks = vi.hoisted(() => ({
  fetcher: vi.fn(),
}))

vi.mock("../api/client", () => ({
  fetcher: mocks.fetcher,
}))

function HookHost(): null {
  useTemplates()
  return null
}

describe("useTemplates", () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    vi.clearAllMocks()
    mocks.fetcher.mockResolvedValue([{ id: "basic", name: "Basic" }])
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

  it("loads once and does not revalidate templates on focus or reconnect", async () => {
    await act(async () => {
      root.render(
        createElement(
          SWRConfig,
          {
            value: {
              provider: () => new Map(),
              dedupingInterval: 0,
              focusThrottleInterval: 0,
            },
          },
          createElement(HookHost),
        ),
      )
    })
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(mocks.fetcher).toHaveBeenCalledTimes(1)
    mocks.fetcher.mockClear()

    act(() => {
      window.dispatchEvent(new Event("focus"))
      window.dispatchEvent(new Event("online"))
    })
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(mocks.fetcher).not.toHaveBeenCalled()
  })
})
