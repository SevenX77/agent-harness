import { describe, expect, it } from "vitest"
import type { CompileError, LintError } from "@/api/types"
import {
  activeLintErrors,
  compileErrorsByNode,
  lintErrorToCompileError,
  lintErrorsByNode,
  mergeNodeErrors,
} from "./node-compile-errors"

function err(file: string | null, severity: CompileError["severity"] = "fatal"): CompileError {
  return { file, line: 1, field: null, severity, message: "boom" }
}

// N4 atom #35: the golden-field compile gate emits a FILE-LESS error scoped by
// field = "<node_id>.<missing_field>" (skills.py _validate_golden_against_output_schema).
function goldenFieldErr(field: string): CompileError {
  return { file: null, line: null, field, severity: "fatal", message: "golden missing field" }
}

function lintErr(file: string | null | undefined, overrides: Partial<LintError> = {}): LintError {
  return {
    file,
    line: 1,
    column: null,
    error_code: "F-v3-001",
    severity: "error",
    message: "boom",
    phase_name: null,
    ...overrides,
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

  it("attributes a file-less golden-field error to its node via the field prefix (atom #35)", () => {
    // field = "<node_id>.<missing_field>"; the node id is the prefix before the first dot.
    const byNode = compileErrorsByNode([goldenFieldErr("review.summary")])
    expect(Object.keys(byNode)).toEqual(["review"])
    expect(byNode.review).toHaveLength(1)
    expect(byNode.review[0].field).toBe("review.summary")
  })

  it("prefers the file phase path over the field prefix when both are present", () => {
    const byNode = compileErrorsByNode([
      { file: "phases/expand/SKILL.md", line: 1, field: "review.summary", severity: "fatal", message: "x" },
    ])
    expect(Object.keys(byNode)).toEqual(["expand"])
  })

  it("omits a file-less error whose field carries no node-id prefix", () => {
    // A bare field with no "<node>." prefix isn't node-attributable — stays in the drawer only.
    expect(compileErrorsByNode([goldenFieldErr("summary")])).toEqual({})
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

describe("lintErrorToCompileError (N3 atom #4 — feed lint into the node tooltip)", () => {
  it("renames the engine field_path locator onto the CompileError field axis", () => {
    const compile = lintErrorToCompileError(
      lintErr("phases/segment/SKILL.md", {
        line: 12,
        field_path: "validator",
        message: "validator must be a boolean",
        severity: "error",
      }),
    )
    expect(compile).toEqual({
      file: "phases/segment/SKILL.md",
      line: 12,
      field: "validator",
      severity: "fatal",
      message: "validator must be a boolean",
    })
  })

  it("maps a warning severity to the CompileError warning severity", () => {
    expect(lintErrorToCompileError(lintErr("phases/p/LOGIC.md", { severity: "warning" })).severity).toBe(
      "warning",
    )
  })

  it("leaves field null when the engine attributed no field_path", () => {
    expect(lintErrorToCompileError(lintErr("phases/p/LOGIC.md", { field_path: null })).field).toBeNull()
  })
})

describe("activeLintErrors (N3 atom #4 — first-screen vs realtime override)", () => {
  const firstScreenLint = [lintErr("phases/draft/SKILL.md", { message: "first-screen lint" })]
  const manifestErrors = [lintErr("GRAPH.md", { message: "manifest error" })]
  const realtime = [lintErr("phases/draft/SKILL.md", { message: "realtime lint" })]

  it("returns the first-screen SkillDetail sources (lint_result + manifest_errors) before any realtime lint", () => {
    const errors = activeLintErrors({ firstScreenLint, manifestErrors, realtime: null })
    const messages = errors.map((error) => error.message)
    expect(messages).toContain("first-screen lint")
    expect(messages).toContain("manifest error")
  })

  it("overrides with the realtime LintResult errors once a realtime lint has resolved", () => {
    const errors = activeLintErrors({ firstScreenLint, manifestErrors, realtime })
    expect(errors.map((error) => error.message)).toEqual(["realtime lint"])
  })

  it("treats an empty realtime errors array as a resolved (clean) lint that clears first-screen errors", () => {
    const errors = activeLintErrors({ firstScreenLint, manifestErrors, realtime: [] })
    expect(errors).toEqual([])
  })

  it("returns an empty list when nothing is available", () => {
    expect(activeLintErrors({ firstScreenLint: null, manifestErrors: null, realtime: null })).toEqual([])
  })
})

describe("mergeNodeErrors (N3 atom #4 — compile + lint without dropping either)", () => {
  it("concatenates compile and lint errors per node, keeping both channels", () => {
    const compileByNode = { draft: [err("phases/draft/SKILL.md")] }
    const lintByNode = {
      draft: [lintErrorToCompileError(lintErr("phases/draft/SKILL.md", { message: "lint" }))],
      review: [lintErrorToCompileError(lintErr("phases/review/LOGIC.md", { message: "lint-review" }))],
    }
    const merged = mergeNodeErrors(compileByNode, lintByNode)
    expect(merged.draft).toHaveLength(2)
    expect(merged.draft.map((error) => error.message).sort()).toEqual(["boom", "lint"])
    expect(merged.review).toHaveLength(1)
    expect(merged.review[0].message).toBe("lint-review")
  })

  it("returns compile-only nodes untouched when there is no lint", () => {
    const merged = mergeNodeErrors({ draft: [err("phases/draft/SKILL.md")] }, {})
    expect(merged.draft).toHaveLength(1)
  })

  it("returns an empty map when both sources are empty", () => {
    expect(mergeNodeErrors({}, {})).toEqual({})
  })
})
