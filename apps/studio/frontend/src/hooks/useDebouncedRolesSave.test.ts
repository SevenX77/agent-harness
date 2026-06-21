import { describe, expect, it, vi } from "vitest"
import type { RolesData } from "@/api/llm"
import {
  flushPendingRolesSaveOnUnmount,
  rolesSaveErrorDisposition,
} from "./useDebouncedRolesSave"

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
