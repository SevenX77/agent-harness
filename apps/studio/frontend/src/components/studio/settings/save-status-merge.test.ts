import { describe, expect, it } from "vitest"
import type { SaveStatus } from "@/hooks/useDebouncedCredentialsSave"
import { mergeSaveStatuses } from "./save-status-merge"

/**
 * N0 Settings · Shell (atom #4 settings-save-badge).
 *
 * The shell top bar projects the three per-tab save statuses (credentials /
 * roles / app settings) into one badge via this pure merge. These tests lock
 * every priority branch: error > saving > pending > saved > idle.
 */
describe("mergeSaveStatuses", () => {
  it("returns idle when every source is idle", () => {
    expect(mergeSaveStatuses(["idle", "idle", "idle"])).toBe("idle")
  })

  it("returns idle for an empty list", () => {
    expect(mergeSaveStatuses([])).toBe("idle")
  })

  it("surfaces error above every other status", () => {
    expect(mergeSaveStatuses(["saved", "saving", "error"])).toBe("error")
    expect(mergeSaveStatuses(["error", "idle", "idle"])).toBe("error")
    expect(mergeSaveStatuses(["pending", "error", "saving"])).toBe("error")
  })

  it("surfaces saving when no error is present", () => {
    expect(mergeSaveStatuses(["saved", "saving", "idle"])).toBe("saving")
    expect(mergeSaveStatuses(["pending", "saving", "pending"])).toBe("saving")
  })

  it("surfaces pending when no error or saving is present", () => {
    expect(mergeSaveStatuses(["saved", "pending", "idle"])).toBe("pending")
    expect(mergeSaveStatuses(["idle", "idle", "pending"])).toBe("pending")
  })

  it("surfaces saved when only saved/idle are present", () => {
    expect(mergeSaveStatuses(["saved", "idle", "idle"])).toBe("saved")
    expect(mergeSaveStatuses(["idle", "saved", "saved"])).toBe("saved")
  })

  it("respects the full priority chain across all five states at once", () => {
    const all: SaveStatus[] = ["idle", "saved", "pending", "saving", "error"]
    expect(mergeSaveStatuses(all)).toBe("error")
    expect(mergeSaveStatuses(all.filter((s) => s !== "error"))).toBe("saving")
    expect(mergeSaveStatuses(all.filter((s) => s !== "error" && s !== "saving"))).toBe("pending")
    expect(mergeSaveStatuses(["idle", "saved"])).toBe("saved")
  })
})
