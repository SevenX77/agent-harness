import { describe, expect, it, vi } from "vitest"
import { rolesSaveErrorDisposition } from "./useDebouncedRolesSave"

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
