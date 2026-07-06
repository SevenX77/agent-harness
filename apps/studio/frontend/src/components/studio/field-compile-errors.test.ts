import { describe, expect, it } from "vitest"
import type { CompileError, LintError } from "@/api/types"
import {
  fieldDiagnosticsForPanels,
  fieldErrorsByKey,
  lintErrorsForBoundary,
  lintErrorsForFile,
  lintErrorsToMarkers,
} from "./field-compile-errors"

function lintErr(overrides: Partial<LintError>): LintError {
  return {
    file: "phases/setup/LOGIC.md",
    line: null,
    column: null,
    error_code: "F-v3-runtime-state-mapping-failed",
    severity: "error",
    message: "boom",
    phase_name: "setup",
    field_path: null,
    source_path: null,
    ...overrides,
  }
}

describe("fieldErrorsByKey", () => {
  it("groups a node's errors by the engine field_path (nearest field)", () => {
    const byField = fieldErrorsByKey(
      [
        lintErr({ field_path: "validator", message: "validator must be bool" }),
        lintErr({ field_path: "tools", message: "tool not found" }),
        lintErr({ field_path: "tools", message: "second tool issue", severity: "warning" }),
      ],
      "setup",
    )
    expect(Object.keys(byField).sort()).toEqual(["tools", "validator"])
    expect(byField.tools).toHaveLength(2)
    expect(byField.validator).toHaveLength(1)
  })

  it("degrades: errors with no field_path are omitted (they fall back to the node badge)", () => {
    const byField = fieldErrorsByKey(
      [
        lintErr({ field_path: null, message: "GRAPH-level" }),
        lintErr({ field_path: "path", message: "field-level" }),
      ],
      "setup",
    )
    expect(Object.keys(byField)).toEqual(["path"])
  })

  it("scopes to the selected node — other phases' field errors are excluded", () => {
    const byField = fieldErrorsByKey(
      [
        lintErr({ phase_name: "setup", file: "phases/setup/LOGIC.md", field_path: "tools" }),
        lintErr({ phase_name: "expand", file: "phases/expand/SKILL.md", field_path: "llm_role" }),
      ],
      "setup",
    )
    expect(Object.keys(byField)).toEqual(["tools"])
  })

  it("falls back to the file phase path when phase_name is absent", () => {
    const byField = fieldErrorsByKey(
      [lintErr({ phase_name: null, file: "phases/setup/LOGIC.md", field_path: "validator" })],
      "setup",
    )
    expect(Object.keys(byField)).toEqual(["validator"])
  })

  it("returns an empty map for null/empty input", () => {
    expect(fieldErrorsByKey(null, "setup")).toEqual({})
    expect(fieldErrorsByKey([], "setup")).toEqual({})
  })
})

describe("lintErrorsForFile", () => {
  it("keeps only diagnostics that belong to the open file (realtime lint = this file's context)", () => {
    const scoped = lintErrorsForFile(
      [
        lintErr({ file: "phases/aggregate/SKILL.md", line: 1, message: "mine" }),
        lintErr({ file: "phases/agent/SKILL.md", line: 1, message: "another file" }),
        lintErr({ file: "GRAPH.md", line: 2, message: "structural" }),
      ],
      "phases/aggregate/SKILL.md",
    )
    expect(scoped.map((error) => error.message)).toEqual(["mine"])
  })

  it("matches separator-insensitively and tolerates an absolute sandbox-path leak", () => {
    const scoped = lintErrorsForFile(
      [
        lintErr({ file: "phases\\aggregate\\SKILL.md", message: "win-seps" }),
        lintErr({ file: "C:/tmp/studio-lint-xxx/skill/phases/aggregate/SKILL.md", message: "abs-leak" }),
      ],
      "phases/aggregate/SKILL.md",
    )
    expect(scoped.map((error) => error.message).sort()).toEqual(["abs-leak", "win-seps"])
  })

  it("drops diagnostics with no file (skill-level → Compile drawer, never inline on this file)", () => {
    const scoped = lintErrorsForFile(
      [lintErr({ file: null, line: 1, message: "no file" })],
      "phases/aggregate/SKILL.md",
    )
    expect(scoped).toEqual([])
  })

  it("returns an empty array for null/empty input", () => {
    expect(lintErrorsForFile(null, "phases/aggregate/SKILL.md")).toEqual([])
    expect(lintErrorsForFile([], "phases/aggregate/SKILL.md")).toEqual([])
  })

  it("renders a GRAPH.md-located topology diagnostic as an inline marker when GRAPH.md is open", () => {
    // The realtime-lint GRAPH.md surface for structural topology errors (e.g.
    // [F-v3-graph-phase-island]): scoping to GRAPH.md keeps it, and it carries a
    // line so it becomes a Monaco marker — the editor counterpart of the node badge.
    const island = lintErr({
      file: "GRAPH.md",
      line: 7,
      error_code: "F-v3-graph-phase-island",
      message: "phase 'orphan' is unreachable from input",
      field_path: "orphan.depends_on",
    })
    const scoped = lintErrorsForFile([island], "GRAPH.md")
    expect(scoped).toHaveLength(1)
    const markers = lintErrorsToMarkers(scoped)
    expect(markers).toHaveLength(1)
    expect(markers[0].startLineNumber).toBe(7)
    expect(markers[0].message).toContain("unreachable from input")
  })
})

describe("lintErrorsForBoundary", () => {
  it("keeps Studio runtime-input diagnostics on the input boundary", () => {
    const scoped = lintErrorsForBoundary(
      [
        lintErr({
          file: ".workspace/runtime_config.json",
          field_path: "chapter",
          message: "Graph input schema requires runtime input field 'chapter'",
        }),
        lintErr({
          file: ".workspace/runtime_config.json",
          field_path: "chapters",
          message: "Runtime input field 'chapters' has type 'string'",
        }),
        lintErr({ file: "phases/review/SKILL.md", field_path: "validator", message: "node field" }),
      ],
      "input",
    )

    expect(scoped.map((error) => error.message)).toEqual([
      "Graph input schema requires runtime input field 'chapter'",
      "Runtime input field 'chapters' has type 'string'",
    ])
  })

  it("keeps io.inputs field diagnostics on the input boundary", () => {
    const scoped = lintErrorsForBoundary(
      [lintErr({ file: "GRAPH.md", field_path: "io.inputs.properties.chapter", message: "bad graph input" })],
      "input",
    )

    expect(scoped).toHaveLength(1)
  })
})

describe("fieldDiagnosticsForPanels", () => {
  it("keeps manual Compile diagnostics even after realtime lint has settled clean", () => {
    const manual: CompileError[] = [
      {
        file: ".workspace/runtime_config.json",
        line: null,
        field: "chapter",
        severity: "fatal",
        message: "Graph input schema requires runtime input field 'chapter'",
        error_code: "STUDIO_RUNTIME_INPUT_MISSING",
      },
    ]

    expect(fieldDiagnosticsForPanels(manual, [])).toMatchObject([
      {
        file: ".workspace/runtime_config.json",
        field_path: "chapter",
        message: "Graph input schema requires runtime input field 'chapter'",
      },
    ])
  })

  it("merges manual Compile and lint diagnostics on the same field axis", () => {
    const manual: CompileError[] = [
      {
        file: ".workspace/runtime_config.json",
        line: null,
        field: "chapter",
        severity: "fatal",
        message: "missing chapter",
        error_code: "STUDIO_RUNTIME_INPUT_MISSING",
      },
    ]
    const lint: LintError[] = [
      lintErr({
        file: "phases/review/SKILL.md",
        line: 7,
        error_code: "F-v3-schema",
        message: "review field is invalid",
        phase_name: "review",
        field_path: "review.io.inputs.properties.chapter",
      }),
    ]

    expect(fieldDiagnosticsForPanels(manual, lint).map((error) => error.message)).toEqual([
      "missing chapter",
      "review field is invalid",
    ])
  })
})

describe("lintErrorsToMarkers", () => {
  it("maps line-bearing errors to Monaco markers with severity + message", () => {
    const markers = lintErrorsToMarkers([
      lintErr({ line: 12, column: 4, severity: "error", message: "bad" }),
      lintErr({ line: 3, column: null, severity: "warning", message: "warn" }),
    ])
    expect(markers).toHaveLength(2)
    expect(markers[0]).toMatchObject({
      startLineNumber: 12,
      endLineNumber: 12,
      startColumn: 4,
      message: "bad",
      severity: "error",
    })
    // No column → mark the whole line from column 1.
    expect(markers[1]).toMatchObject({ startLineNumber: 3, startColumn: 1, severity: "warning" })
  })

  it("degrades: errors without a line are dropped (no inline marker, file-level fallback)", () => {
    const markers = lintErrorsToMarkers([
      lintErr({ line: null, message: "no line" }),
      lintErr({ line: 5, message: "has line" }),
    ])
    expect(markers).toHaveLength(1)
    expect(markers[0]).toMatchObject({ startLineNumber: 5 })
  })

  it("returns an empty array for null/empty input", () => {
    expect(lintErrorsToMarkers(null)).toEqual([])
    expect(lintErrorsToMarkers([])).toEqual([])
  })
})
