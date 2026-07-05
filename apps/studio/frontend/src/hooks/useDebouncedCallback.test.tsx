// @vitest-environment jsdom
import { act } from "react"
import { createRoot, type Root } from "react-dom/client"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { useDebouncedCallback, type DebouncedCallback } from "./useDebouncedCallback"

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

type DebouncedStringCallback = DebouncedCallback<[string]>

function renderHookHarness(onRun: (value: string) => void): {
  api: () => DebouncedStringCallback
  root: Root
  container: HTMLDivElement
} {
  const container = document.createElement("div")
  document.body.appendChild(container)
  const root = createRoot(container)
  let api: DebouncedStringCallback | null = null

  function Harness() {
    api = useDebouncedCallback(onRun, 300)
    return null
  }

  act(() => {
    root.render(<Harness />)
  })

  return {
    api: () => {
      if (!api) throw new Error("hook api was not initialised")
      return api
    },
    root,
    container,
  }
}

describe("useDebouncedCallback", () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    document.body.innerHTML = ""
  })

  it("runs only the latest scheduled callback after the debounce window", () => {
    const onRun = vi.fn()
    const { api, root } = renderHookHarness(onRun)

    act(() => {
      api().schedule("0.7")
      api().schedule("1.5")
      vi.advanceTimersByTime(299)
    })

    expect(onRun).not.toHaveBeenCalled()

    act(() => {
      vi.advanceTimersByTime(1)
    })

    expect(onRun).toHaveBeenCalledTimes(1)
    expect(onRun).toHaveBeenCalledWith("1.5")

    act(() => {
      root.unmount()
    })
  })

  it("flushes immediately and cancels stale pending work", () => {
    const onRun = vi.fn()
    const { api, root } = renderHookHarness(onRun)

    act(() => {
      api().schedule("0.2")
      api().flush()
      vi.advanceTimersByTime(300)
    })

    expect(onRun).toHaveBeenCalledTimes(1)
    expect(onRun).toHaveBeenCalledWith("0.2")

    act(() => {
      api().schedule("1.0")
      api().cancel()
      vi.advanceTimersByTime(300)
    })

    expect(onRun).toHaveBeenCalledTimes(1)

    act(() => {
      root.unmount()
    })
  })

  it("cancels pending work on unmount", () => {
    const onRun = vi.fn()
    const { api, root } = renderHookHarness(onRun)

    act(() => {
      api().schedule("1.0")
      root.unmount()
      vi.advanceTimersByTime(300)
    })

    expect(onRun).not.toHaveBeenCalled()
  })
})
