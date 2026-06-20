import { describe, expect, it } from "vitest"
import type { LintError } from "@/api/types"
import { fieldErrorsByKey, lintErrorsToMarkers } from "./field-compile-errors"

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
