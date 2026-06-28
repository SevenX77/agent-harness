import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it, vi } from "vitest"
import type { LintError, LintResult } from "../api/types"

// MonacoPanel imports the heavy Monaco editor at module scope; the lint diagnostics
// strip under test does not render it, so stub the editor to keep this a pure SSR test.
vi.mock("@monaco-editor/react", () => ({ default: () => null }))

const { LintDiagnosticsPanel } = await import("./MonacoPanel")

function makeError(overrides: Partial<LintError> = {}): LintError {
  return {
    file: "phases/draft/SKILL.md",
    line: 12,
    column: null,
    error_code: "F-v3-001",
    severity: "error",
    message: "Unknown model alias",
    phase_name: "draft",
    ...overrides,
  }
}

function result(errors: LintError[], status: LintResult["status"] = "failed"): LintResult {
  return { status, errors, phases_summary: null }
}

describe("LintDiagnosticsPanel", () => {
  it("renders nothing when the lint payload is null or has no diagnostics (collapses while clean)", () => {
    expect(renderToStaticMarkup(
      <LintDiagnosticsPanel lintResult={null} onJumpToLine={() => {}} onCopyErrors={() => {}} />,
    )).toBe("")
    expect(renderToStaticMarkup(
      <LintDiagnosticsPanel lintResult={result([], "passed")} onJumpToLine={() => {}} onCopyErrors={() => {}} />,
    )).toBe("")
  })

  it("projects each backend diagnostic as a jump-to-line row with its line and code", () => {
    const html = renderToStaticMarkup(
      <LintDiagnosticsPanel
        lintResult={result([makeError(), makeError({ error_code: "F-v3-002", line: 30, message: "Dangling edge" })])}
        onJumpToLine={() => {}}
        onCopyErrors={() => {}}
      />,
    )
    expect(html).toContain("Line 12")
    expect(html).toContain("F-v3-001")
    expect(html).toContain("Unknown model alias")
    expect(html).toContain("Line 30")
    expect(html).toContain("Dangling edge")
  })

  it("is a quiet inline strip, not a global toast/floating card (no fixed/inset positioning)", () => {
    const html = renderToStaticMarkup(
      <LintDiagnosticsPanel lintResult={result([makeError()])} onJumpToLine={() => {}} onCopyErrors={() => {}} />,
    )
    expect(html).toContain('role="status"')
    expect(html).toContain('aria-label="Lint diagnostics"')
    expect(html).not.toContain("fixed")
    expect(html).not.toContain("inset-0")
  })

  it("uses semantic destructive tokens for errors — never hardcoded palette colors", () => {
    const html = renderToStaticMarkup(
      <LintDiagnosticsPanel lintResult={result([makeError({ severity: "error" })])} onJumpToLine={() => {}} onCopyErrors={() => {}} />,
    )
    expect(html).toContain("destructive")
    expect(html).not.toMatch(/red-\d/)
    expect(html).not.toMatch(/slate-\d/)
  })

  it("uses semantic warning tokens when every diagnostic is a warning (warnings do not read as errors)", () => {
    const html = renderToStaticMarkup(
      <LintDiagnosticsPanel
        lintResult={result([makeError({ severity: "warning" })])}
        onJumpToLine={() => {}}
        onCopyErrors={() => {}}
      />,
    )
    expect(html).toContain("warning")
    expect(html).toContain("Lint found warnings")
    expect(html).not.toContain("destructive")
  })

  it("exposes a labelled copy-diagnostics affordance", () => {
    const html = renderToStaticMarkup(
      <LintDiagnosticsPanel lintResult={result([makeError()])} onJumpToLine={() => {}} onCopyErrors={() => {}} />,
    )
    expect(html).toContain('aria-label="Copy lint diagnostics"')
  })
})
