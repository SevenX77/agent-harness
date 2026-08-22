import { describe, expect, it } from "vitest"

import type { RoleTestResponse } from "@/api/llm"
import { chainReachFromResult, chainReachSummary } from "./role-test-status"

function response(statuses: string[]): RoleTestResponse {
  return {
    role_name: "__compare__probe",
    status: "warning",
    warnings: [],
    model_groups: [
      {
        canonical_id: "deepseek-v4-flash",
        display_name: "DeepSeek V4 Flash",
        provider_results: statuses.map((status, index) => ({
          route_id: `route-${index}`,
          provider_label: `Provider ${index}`,
          status,
          warnings: [],
          resolved_settings: {},
        })),
      },
    ],
  } as unknown as RoleTestResponse
}

describe("what a Test says about a chain that only partly answered", () => {
  it("counts the routes that answered against the routes that were asked", () => {
    expect(chainReachFromResult(response(["ok", "failed", "ok", "ok"]))).toEqual({
      answered: 3,
      total: 4,
    })
  })

  it("says how much of the chain answered, because the verdict alone cannot", () => {
    // A candidate with 12 working routes and 4 dead ones is usable. Reporting
    // only the 4 dead ones — which is what the dialog used to do — reads as
    // "this is broken".
    expect(chainReachSummary("warning", { answered: 12, total: 16 })).toBe(
      "Answered on 12 of 16 routes",
    )
  })

  it("keeps the plain verdict when everything answered", () => {
    expect(chainReachSummary("ok", { answered: 16, total: 16 })).toBe("Test passed")
  })

  it("keeps Needs Attention when every route answered but something was downgraded", () => {
    // Nothing failed here, so a count would say "16 of 16" and explain nothing;
    // the reason to look is in the detail lines.
    expect(chainReachSummary("warning", { answered: 16, total: 16 })).toBe("Needs Attention")
  })

  it("says failed when nothing answered", () => {
    expect(chainReachSummary("failed", { answered: 0, total: 4 })).toBe("Test failed")
  })

  it("counts nothing when the result carried no routes", () => {
    expect(chainReachFromResult(response([]))).toEqual({ answered: 0, total: 0 })
  })
})
