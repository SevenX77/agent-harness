import { describe, expect, it } from "vitest"
import type { CompileError, LintError } from "@/api/types"
import { compileErrorsByNode, lintErrorsByNode } from "./node-compile-errors"

function err(file: string | null, severity: CompileError["severity"] = "fatal"): CompileError {
  return { file, line: 1, field: null, severity, message: "boom" }
}

function lintErr(file: string | null | undefined): LintError {
  return {
    file,
    line: 1,
    column: null,
    error_code: "F-v3-001",
    severity: "error",
    message: "boom",
    phase_name: null,
  }
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

  it("matches the backend phase-id char class (upper-case / digit-leading ids)", () => {
    const byNode = compileErrorsByNode([
      err("phases/Segment_1/LOGIC.md"),
      err("phases/2nd-pass/SKILL.md"),
    ])
    expect(Object.keys(byNode).sort()).toEqual(["2nd-pass", "Segment_1"])
  })
})

describe("lintErrorsByNode", () => {
  it("groups lint diagnostics by the phase id derived from the file path", () => {
    const byNode = lintErrorsByNode([
      lintErr("phases/segment/LOGIC.md"),
      lintErr("phases/segment/actions/strip.py"),
      lintErr("phases/expand/SKILL.md"),
    ])
    expect(Object.keys(byNode).sort()).toEqual(["expand", "segment"])
    expect(byNode.segment).toHaveLength(2)
    expect(byNode.expand).toHaveLength(1)
  })

  it("omits graph-level / unattributable diagnostics (GRAPH.md, null or undefined file)", () => {
    const byNode = lintErrorsByNode([
      lintErr("GRAPH.md"),
      lintErr(null),
      lintErr(undefined),
      lintErr("phases/p/LOGIC.md"),
    ])
    expect(Object.keys(byNode)).toEqual(["p"])
  })

  it("returns an empty map for null/empty input", () => {
    expect(lintErrorsByNode(null)).toEqual({})
    expect(lintErrorsByNode([])).toEqual({})
  })
})
