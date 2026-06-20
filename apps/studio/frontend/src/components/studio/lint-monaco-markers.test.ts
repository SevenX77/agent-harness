import { describe, expect, it, vi } from "vitest"
import type { LintError, LintResult } from "@/api/types"
import { applyLintMarkers, LINT_MARKER_OWNER } from "./lint-monaco-markers"

const SEVERITY = { Error: 8, Warning: 4 } as const

function fakeMonaco() {
  const setModelMarkers = vi.fn()
  return {
    monaco: { editor: { setModelMarkers }, MarkerSeverity: SEVERITY } as never,
    setModelMarkers,
  }
}

function lintErr(overrides: Partial<LintError>): LintError {
  return {
    file: "phases/setup/LOGIC.md",
    line: null,
    column: null,
    error_code: "F-v3-001",
    severity: "error",
    message: "boom",
    phase_name: "setup",
    field_path: null,
    source_path: null,
    ...overrides,
  }
}

function result(errors: LintError[]): LintResult {
  return { status: "failed", errors, phases_summary: null }
}

describe("applyLintMarkers", () => {
  it("pushes line-bearing markers under the lint owner with mapped severity", () => {
    const { monaco, setModelMarkers } = fakeMonaco()
    const model = {} as never

    applyLintMarkers(
      monaco,
      model,
      result([
        lintErr({ line: 7, column: 3, severity: "error", message: "bad" }),
        lintErr({ line: 2, severity: "warning", message: "warn" }),
      ]),
    )

    expect(setModelMarkers).toHaveBeenCalledTimes(1)
    const [, owner, markers] = setModelMarkers.mock.calls[0]
    expect(owner).toBe(LINT_MARKER_OWNER)
    expect(markers).toHaveLength(2)
    expect(markers[0]).toMatchObject({ startLineNumber: 7, startColumn: 3, severity: SEVERITY.Error })
    expect(markers[1]).toMatchObject({ startLineNumber: 2, severity: SEVERITY.Warning })
  })

  it("clears markers (empty array) when the result has no line-bearing errors", () => {
    const { monaco, setModelMarkers } = fakeMonaco()
    applyLintMarkers(monaco, {} as never, result([lintErr({ line: null })]))
    expect(setModelMarkers).toHaveBeenCalledWith(expect.anything(), LINT_MARKER_OWNER, [])
  })

  it("clears markers when lintResult is null (passed / idle)", () => {
    const { monaco, setModelMarkers } = fakeMonaco()
    applyLintMarkers(monaco, {} as never, null)
    expect(setModelMarkers).toHaveBeenCalledWith(expect.anything(), LINT_MARKER_OWNER, [])
  })

  it("no-ops when monaco or model is unavailable (editor not mounted)", () => {
    const { monaco, setModelMarkers } = fakeMonaco()
    applyLintMarkers(null, {} as never, result([lintErr({ line: 1 })]))
    applyLintMarkers(monaco, null, result([lintErr({ line: 1 })]))
    expect(setModelMarkers).not.toHaveBeenCalled()
  })
})
