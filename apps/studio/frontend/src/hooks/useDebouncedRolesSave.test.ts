// @vitest-environment jsdom
import { act, createElement, useEffect, type ReactNode } from "react"
import { createRoot, type Root } from "react-dom/client"
import { afterEach, describe, expect, it, vi } from "vitest"
import type { RolesData } from "@/api/llm"
import {
  flushPendingRolesSaveOnUnmount,
  rolesSaveErrorDisposition,
  shouldApplyExternalRolesRefresh,
  useDebouncedRolesSave,
} from "./useDebouncedRolesSave"

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

function sampleRoles(label: string): RolesData {
  return {
    schema_version: 3,
    models: {},
    providers: {},
    roles: {
      [label]: {
        title: label,
        role_kind: "copilot",
        active_model: "",
        models: {},
        fallback_chain: [],
      },
    },
  } as unknown as RolesData
}

afterEach(() => {
  vi.useRealTimers()
  document.body.innerHTML = ""
  vi.clearAllMocks()
})

describe("rolesSaveErrorDisposition", () => {
  it("recovers a non-buffered stale role save error", () => {
    const error = new Error("stale route")

    expect(rolesSaveErrorDisposition(error, false, () => true)).toBe("recoverable")
  })

  it("defers to the buffered save instead of reporting an older error", () => {
    const recoverable = vi.fn(() => true)

    expect(rolesSaveErrorDisposition(new Error("stale route"), true, recoverable)).toBe("buffered")
    expect(recoverable).not.toHaveBeenCalled()
  })

  it("reports non-recoverable errors when no newer snapshot is queued", () => {
    expect(rolesSaveErrorDisposition(new Error("server down"), false, () => false)).toBe("fatal")
  })
})

describe("useDebouncedRolesSave", () => {
  it("keeps only the newest queued roles snapshot while an older save is in flight", async () => {
    vi.useFakeTimers()
    const first = deferred<RolesData>()
    const second = deferred<RolesData>()
    const putFn = vi.fn<(data: RolesData) => Promise<RolesData>>()
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise)
    let hook: ReturnType<typeof useDebouncedRolesSave> | null = null

    function Harness() {
      const result = useDebouncedRolesSave({ delayMs: 20, putFn })
      useEffect(() => {
        hook = result
      })
      return null
    }

    const { root } = renderJsx(createElement(Harness))

    act(() => {
      hook?.queue(() => sampleRoles("first"))
      vi.advanceTimersByTime(20)
    })
    expect(putFn).toHaveBeenCalledTimes(1)
    expect(Object.keys(putFn.mock.calls[0]?.[0].roles ?? {})).toEqual(["first"])

    act(() => {
      hook?.queue(() => sampleRoles("stale-second"))
      hook?.queue(() => sampleRoles("latest-second"))
    })
    expect(putFn).toHaveBeenCalledTimes(1)

    await act(async () => {
      first.resolve(sampleRoles("first"))
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(putFn).toHaveBeenCalledTimes(2)
    expect(Object.keys(putFn.mock.calls[1]?.[0].roles ?? {})).toEqual(["latest-second"])

    await act(async () => {
      second.resolve(sampleRoles("latest-second"))
      await Promise.resolve()
      await Promise.resolve()
    })

    act(() => root.unmount())
  })
})

describe("shouldApplyExternalRolesRefresh", () => {
  it("blocks external role refetches while a local roles save is buffered or in flight", () => {
    expect(shouldApplyExternalRolesRefresh("idle")).toBe(true)
    expect(shouldApplyExternalRolesRefresh("saved")).toBe(true)
    expect(shouldApplyExternalRolesRefresh("error")).toBe(true)
    expect(shouldApplyExternalRolesRefresh("pending")).toBe(false)
    expect(shouldApplyExternalRolesRefresh("saving")).toBe(false)
  })
})

/**
 * R-F19.1 coverage — `useDebouncedRolesSave`'s `useEffect` cleanup delegates
 * to `flushPendingRolesSaveOnUnmount`, so unit-testing this pure helper covers
 * the unmount path without pulling in `@testing-library/react`. The hook's
 * cleanup discards the result; we exercise the return value directly so we
 * can also assert the failure-logging contract.
 */
describe("flushPendingRolesSaveOnUnmount", () => {
  const samplePayload: RolesData = {
    roles: {
      copilot_custom_1: {
        title: "Custom 1",
        role_kind: "copilot",
        active_model: "",
        models: {},
        fallback_chain: [],
      },
    },
  } as unknown as RolesData

  it("calls putFn exactly once with the buffered payload", () => {
    const putFn = vi.fn(async (data: RolesData) => data)
    const snapshot = () => samplePayload

    const result = flushPendingRolesSaveOnUnmount(snapshot, putFn)

    expect(putFn).toHaveBeenCalledTimes(1)
    expect(putFn).toHaveBeenCalledWith(samplePayload)
    expect(result).toBeInstanceOf(Promise)
  })

  it("is a no-op when no payload is buffered", () => {
    const putFn = vi.fn(async (data: RolesData) => data)

    const result = flushPendingRolesSaveOnUnmount(null, putFn)

    expect(putFn).not.toHaveBeenCalled()
    expect(result).toBeNull()
  })

  it("is a no-op when the snapshot getter returns null (no live snapshot)", () => {
    const putFn = vi.fn(async (data: RolesData) => data)

    const result = flushPendingRolesSaveOnUnmount(() => null, putFn)

    expect(putFn).not.toHaveBeenCalled()
    expect(result).toBeNull()
  })

  it("logs putFn failures via the injected logger (no silent degradation)", async () => {
    const failure = new Error("network down")
    const putFn = vi.fn(async () => {
      throw failure
    })
    const log = vi.fn()

    const result = flushPendingRolesSaveOnUnmount(() => samplePayload, putFn, log)
    await expect(result).rejects.toBe(failure)
    expect(log).toHaveBeenCalledTimes(1)
    expect(log.mock.calls[0]?.[0]).toContain("cleanup-flush-failed")
    expect(log.mock.calls[0]?.[1]).toBe(failure)
  })
})
