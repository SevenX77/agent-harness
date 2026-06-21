import { describe, expect, it } from "vitest"
import { subgraphPathFieldState } from "./subgraph-path"

describe("subgraphPathFieldState", () => {
  it("resolves a usable absolute path (trimming surrounding whitespace)", () => {
    expect(subgraphPathFieldState("/abs/skills/translator", null)).toEqual({
      path: "/abs/skills/translator",
      legacyTargetSkill: null,
      status: "resolved",
    })
    expect(subgraphPathFieldState("  /abs/child  ", null)).toEqual({
      path: "/abs/child",
      legacyTargetSkill: null,
      status: "resolved",
    })
  })

  it("marks an empty or blank path as missing", () => {
    expect(subgraphPathFieldState("", null).status).toBe("missing")
    expect(subgraphPathFieldState("   ", null).status).toBe("missing")
  })

  it("marks a non-absolute path as missing", () => {
    expect(subgraphPathFieldState("relative/child_graph", null).status).toBe("missing")
  })

  it("marks an empty path with a legacy target_skill as migration-required", () => {
    expect(subgraphPathFieldState("", "legacy.registry.child")).toEqual({
      path: null,
      legacyTargetSkill: "legacy.registry.child",
      status: "migration-required",
    })
  })

  it("prefers a usable absolute path over a still-present legacy target_skill", () => {
    expect(subgraphPathFieldState("/abs/child", "legacy.registry.child")).toEqual({
      path: "/abs/child",
      legacyTargetSkill: null,
      status: "resolved",
    })
  })
})
