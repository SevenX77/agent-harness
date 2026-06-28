import { describe, expect, it } from "vitest"
import { roleTestStatusBadge } from "./role-test-status"

describe("roleTestStatusBadge — node Properties role-test projection (R23)", () => {
  it("maps running to a Testing/secondary badge regardless of stale status", () => {
    const badge = roleTestStatusBadge({ running: true, status: "ok" })
    expect(badge).toEqual({ label: "Testing", variant: "secondary", running: true })
  })

  it("maps an error to a Failed/destructive badge", () => {
    const badge = roleTestStatusBadge({ running: false, error: "boom" })
    expect(badge).toEqual({ label: "Failed", variant: "destructive", running: false })
  })

  it("maps ok result status to Passed/success", () => {
    expect(roleTestStatusBadge({ running: false, status: "ok" })).toEqual({
      label: "Passed",
      variant: "success",
      running: false,
    })
  })

  it("maps warning result status to Needs Attention/warning", () => {
    expect(roleTestStatusBadge({ running: false, status: "warning" })).toEqual({
      label: "Needs Attention",
      variant: "warning",
      running: false,
    })
  })

  it("maps blocked and failed result status to Failed/destructive", () => {
    expect(roleTestStatusBadge({ running: false, status: "blocked" }).label).toBe("Failed")
    expect(roleTestStatusBadge({ running: false, status: "blocked" }).variant).toBe("destructive")
    expect(roleTestStatusBadge({ running: false, status: "failed" }).variant).toBe("destructive")
  })

  it("maps the untested/no-result default to Untested/secondary", () => {
    expect(roleTestStatusBadge({ running: false })).toEqual({
      label: "Untested",
      variant: "secondary",
      running: false,
    })
    expect(roleTestStatusBadge({ running: false, status: null })).toEqual({
      label: "Untested",
      variant: "secondary",
      running: false,
    })
  })
})
