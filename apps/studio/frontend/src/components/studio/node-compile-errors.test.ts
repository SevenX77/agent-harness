import { describe, expect, it } from "vitest"
import type { CompileError, LintError } from "@/api/types"
import { INPUT_ID } from "@/components/nodes"
import {
  activeLintErrors,
  compileErrorsByNode,
  lintErrorToCompileError,
  lintErrorsByNode,
  selectActiveNodeErrors,
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

/*
 * A diagnostic path is relative to the COMPILE ROOT, so only a path starting at the root
 * names a root-graph node. Measured engine output for a defect inside a child skill
 * (fixture `packages/graph-agent/tests/core/test_compile_issue_source_path_is_root_relative.py`
 * `_skill()`, unknown frontmatter field added to `subgraph/first/phases/review/SKILL.md`,
 * run 2026-08-16):
 *
 *   [F-v3-agent-schema-unknown-field] | 'subgraph/first/phases/review/SKILL.md' | 'no_such_field'
 *   [F-v3-agent-subgraph-invalid]     | 'phases/alpha/SUBGRAPH.md'              | 'path'
 *
 * The first line is the child's own defect: it has no root node, because the root phase
 * that hosts the child is `alpha` while the child's directory is `first` — the path cannot
 * name the hosting node. The second line is the engine's OWN root-node diagnostic for the
 * same event, so dropping the first one does not leave the canvas silent.
 *
 * Observable defect before this change: `PHASE_FILE_RE = /(?:^|\/)phases\/([A-Za-z0-9_-]+)\//`
 * matched at any position, so the first line was badged onto a root node named `review`
 * — another skill's phase. See
 * `.kiro/specs/decision-2026-08-15-compile-diagnostics-name-the-file-they-are-in.md:85`.
 */
describe("child-skill diagnostics never reach a root node", () => {
  it("compileErrorsByNode: a subgraph phase file yields no node bucket", () => {
    const byNode = compileErrorsByNode([
      err("subgraph/first/phases/review/SKILL.md"),
      err("phases/review/SKILL.md"),
    ])
    expect(Object.keys(byNode)).toEqual(["review"])
    expect(byNode.review).toHaveLength(1)
  })

  it("lintErrorsByNode: a subgraph phase file yields no node bucket", () => {
    const byNode = lintErrorsByNode([
      lintErr("subgraph/first/phases/review/SKILL.md"),
      lintErr("subgraph/event-timeline/subgraph/event-extraction/phases/review/SKILL.md"),
    ])
    expect(byNode).toEqual({})
  })

  /*
   * Same fixture, child graph declaring an output its phase does not produce (run
   * 2026-08-16):
   *
   *   [F-v3-graph-io-schema-invalid] | 'subgraph/first/GRAPH.md' | 'io.outputs.required'
   *
   * The field locator `io.outputs.required` is the CHILD graph's output block, but
   * `boundaryNodeIdFromField` reads it as the root graph's global Output node. A file
   * that already says "I am inside a child skill" must not be re-attributed by its
   * field locator.
   */
  it("does not badge a child graph's io diagnostic onto the root global Output node", () => {
    const byNode = compileErrorsByNode([
      {
        file: "subgraph/first/GRAPH.md",
        line: 5,
        field: "io.outputs.required",
        severity: "fatal",
        message: "child output block is invalid",
      },
    ])
    expect(byNode).toEqual({})
  })

  it("still badges the engine's own root-node diagnostic for the broken child", () => {
    const byNode = compileErrorsByNode([err("phases/alpha/SUBGRAPH.md")])
    expect(Object.keys(byNode)).toEqual(["alpha"])
  })
})

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

  it("attributes engine dataflow compile errors to their node via field_path", () => {
    const byNode = compileErrorsByNode([
      {
        file: null,
        line: 1,
        field: "review.io.inputs.properties.summary",
        severity: "fatal",
        message: "phase 'review' input 'summary' has no root, upstream, or runtime input provider",
      },
    ])
    expect(Object.keys(byNode)).toEqual(["review"])
    expect(byNode.review[0].field).toBe("review.io.inputs.properties.summary")
  })

  it("attributes Studio runtime-input preflight errors to the global Input node", () => {
    const byNode = compileErrorsByNode([
      {
        file: ".workspace/runtime_config.json",
        line: null,
        field: "chapter",
        severity: "fatal",
        message: "Graph input schema requires runtime input field 'chapter'",
        error_code: "STUDIO_RUNTIME_INPUT_MISSING",
      },
      {
        file: ".workspace/runtime_config.json",
        line: null,
        field: "chapters",
        severity: "fatal",
        message: "Runtime input field 'chapters' has type 'string'",
        error_code: "STUDIO_RUNTIME_INPUT_SCHEMA_INVALID",
      },
    ])
    expect(Object.keys(byNode)).toEqual([INPUT_ID])
    expect(byNode[INPUT_ID]).toHaveLength(2)
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

  // Surfacing parity with the manual-Compile node channel: a GRAPH.md-located
  // topology diagnostic (e.g. [F-v3-graph-phase-island]) that carries a node
  // locator must badge the offending node in realtime lint too, not just the
  // GRAPH.md editor markers + compile drawer.
  it("attributes a GRAPH.md-located diagnostic to its node via phase_name", () => {
    const byNode = lintErrorsByNode([
      lintErr("GRAPH.md", { phase_name: "orphan", message: "orphan is unreachable from input" }),
    ])
    expect(Object.keys(byNode)).toEqual(["orphan"])
    expect(byNode.orphan).toHaveLength(1)
  })

  it("attributes a GRAPH.md-located diagnostic to its node via the field_path node-id prefix", () => {
    const byNode = lintErrorsByNode([
      lintErr("GRAPH.md", { field_path: "orphan.depends_on", message: "orphan is unreachable from input" }),
    ])
    expect(Object.keys(byNode)).toEqual(["orphan"])
  })

  it("attributes engine dataflow lint errors to their node via field_path", () => {
    const byNode = lintErrorsByNode([
      lintErr("phases/review/SKILL.md", {
        field_path: "review.io.inputs.properties.summary",
        message: "phase 'review' input 'summary' has no root, upstream, or runtime input provider",
      }),
    ])
    expect(Object.keys(byNode)).toEqual(["review"])
  })

  it("still omits a GRAPH.md diagnostic with no node locator (no phase_name, no field_path)", () => {
    const byNode = lintErrorsByNode([lintErr("GRAPH.md", { field_path: null, phase_name: null })])
    expect(byNode).toEqual({})
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
      error_code: "F-v3-001",
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

  it("dedupes first-screen lint_result and manifest_errors when they carry the same engine diagnostic", () => {
    const duplicate = lintErr("phases/review/SKILL.md", {
      field_path: "review.io.inputs.properties.chapter_lines",
      message: "phase 'review' input 'chapter_lines' has no root, upstream, or runtime input provider",
      error_code: "F-v3-graph-dataflow-source-missing",
    })

    const errors = activeLintErrors({ firstScreenLint: [duplicate], manifestErrors: [duplicate], realtime: null })

    expect(errors).toHaveLength(1)
    expect(errors[0].field_path).toBe("review.io.inputs.properties.chapter_lines")
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

describe("selectActiveNodeErrors (J-03.B — latest pass replaces, no union)", () => {
  const compileByNode = { draft: [err("phases/draft/SKILL.md")] }
  const lintByNode = {
    draft: [lintErrorToCompileError(lintErr("phases/draft/SKILL.md", { message: "lint" }))],
    review: [lintErrorToCompileError(lintErr("phases/review/LOGIC.md", { message: "lint-review" }))],
  }

  it("returns the compile-channel map wholesale when source is compile", () => {
    expect(selectActiveNodeErrors("compile", compileByNode, lintByNode)).toBe(compileByNode)
  })

  it("returns the lint-channel map wholesale when source is lint", () => {
    expect(selectActiveNodeErrors("lint", compileByNode, lintByNode)).toBe(lintByNode)
  })

  it("does not carry a node from the other channel into the selected one", () => {
    // "review" only exists in the lint channel — selecting compile must not
    // surface it, proving this is a replace, not a merge of the two node sets.
    const selected = selectActiveNodeErrors("compile", compileByNode, lintByNode)
    expect(selected.review).toBeUndefined()
  })

  it("returns an empty map when the active channel is empty, even if the other channel has errors", () => {
    expect(selectActiveNodeErrors("compile", {}, lintByNode)).toEqual({})
    expect(selectActiveNodeErrors("lint", compileByNode, {})).toEqual({})
  })
})
