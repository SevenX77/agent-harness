import { describe, expect, it } from "vitest"
import type { CompileError } from "@/api/types"
import { compileErrorsByNode, hasFatalCompileError } from "./node-compile-errors"

function err(file: string | null, severity: CompileError["severity"] = "fatal"): CompileError {
  return { file, line: 1, field: null, severity, message: "boom" }
}

describe("compileErrorsByNode", () => {
  it("groups errors by the phase id derived from the file path", () => {
    const byNode = compileErrorsByNode([
      err("phases/segment/LOGIC.md"),
      err("phases/segment/actions/strip.py"),
      err("phases/expand/SKILL.md"),
    ])
    expect(Object.keys(byNode).sort()).toEqual(["expand", "segment"])
    expect(byNode.segment).toHaveLength(2)
    expect(byNode.expand).toHaveLength(1)
  })

  it("omits graph-level errors (GRAPH.md / null file) — not attributable to a node", () => {
    const byNode = compileErrorsByNode([err("GRAPH.md"), err(null), err("phases/p/LOGIC.md")])
    expect(Object.keys(byNode)).toEqual(["p"])
  })

  it("returns an empty map for null/empty input", () => {
    expect(compileErrorsByNode(null)).toEqual({})
    expect(compileErrorsByNode([])).toEqual({})
  })
})

describe("hasFatalCompileError", () => {
  it("is true only when a fatal error is present", () => {
    expect(hasFatalCompileError([err("phases/p/LOGIC.md", "warning")])).toBe(false)
    expect(hasFatalCompileError([err("phases/p/LOGIC.md", "fatal")])).toBe(true)
    expect(hasFatalCompileError(undefined)).toBe(false)
  })
})
