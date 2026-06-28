import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it, vi } from "vitest"
import {
  CompileErrorDrawer,
  buildCompileErrorClipboardText,
  formatCompileErrorLine,
} from "./CompileErrorDrawer"
import type { CompileError } from "@/api/types"

function makeError(overrides: Partial<CompileError> = {}): CompileError {
  return {
    file: "phases/draft/SKILL.md",
    line: 12,
    field: "model",
    severity: "fatal",
    message: "Unknown model alias",
    ...overrides,
  }
}

const errors: CompileError[] = [
  makeError(),
  makeError({ file: "GRAPH.md", line: 3, field: null, message: "Dangling edge" }),
  makeError({ file: null, line: null, field: null, message: "Compile request failed" }),
]

describe("formatCompileErrorLine", () => {
  it("renders file:line - field - message when all parts present", () => {
    expect(formatCompileErrorLine(makeError())).toBe(
      "phases/draft/SKILL.md:12 - model - Unknown model alias",
    )
  })

  it("omits the field segment when there is no field", () => {
    expect(formatCompileErrorLine(makeError({ field: null }))).toBe(
      "phases/draft/SKILL.md:12 - Unknown model alias",
    )
  })

  it("falls back to 'unknown file' and drops the line when file is null", () => {
    expect(
      formatCompileErrorLine(makeError({ file: null, line: null, field: null, message: "boom" })),
    ).toBe("unknown file - boom")
  })
})

describe("buildCompileErrorClipboardText", () => {
  it("builds a readable digest with a count heading and one bullet per error", () => {
    const text = buildCompileErrorClipboardText(errors)
    expect(text).toBe(
      [
        "3 compile errors",
        "- phases/draft/SKILL.md:12 - model - Unknown model alias",
        "- GRAPH.md:3 - Dangling edge",
        "- unknown file - Compile request failed",
      ].join("\n"),
    )
  })

  it("uses the singular form for a single error", () => {
    const text = buildCompileErrorClipboardText([makeError()])
    expect(text.startsWith("1 compile error\n")).toBe(true)
  })
})

describe("CompileErrorDrawer rendering", () => {
  it("lists every error as file:line - field - message when open", () => {
    const html = renderToStaticMarkup(
      <CompileErrorDrawer errors={errors} open onOpenChange={() => {}} />,
    )
    expect(html).toContain("phases/draft/SKILL.md")
    expect(html).toContain(":12")
    expect(html).toContain("model")
    expect(html).toContain("Unknown model alias")
    expect(html).toContain("Dangling edge")
    expect(html).toContain("Compile request failed")
    expect(html).toContain("3 compile errors")
  })

  it("exposes a copy-all-errors button", () => {
    const html = renderToStaticMarkup(
      <CompileErrorDrawer errors={errors} open onOpenChange={() => {}} />,
    )
    expect(html).toContain("Copy all errors")
    expect(html).toContain('aria-label="Copy all compile errors"')
  })

  it("renders nothing when closed", () => {
    const html = renderToStaticMarkup(
      <CompileErrorDrawer errors={errors} open={false} onOpenChange={() => {}} />,
    )
    expect(html).toBe("")
  })

  it("is canvas-scoped: uses absolute positioning, never fixed inset-0", () => {
    const html = renderToStaticMarkup(
      <CompileErrorDrawer errors={errors} open onOpenChange={() => {}} />,
    )
    // The canvas-scoped content must stay inside the canvas container, so the
    // drawer must NOT use the viewport-blanketing `fixed inset-0` that the local
    // ui/sheet.tsx (and bare Radix Portal dialog) would apply.
    expect(html).not.toContain("fixed inset-0")
    expect(html).not.toContain("fixed")
    // Content is clipped to the (relative) canvas container and pinned to its
    // bottom edge via absolute inset-x-0 bottom-0 — never to the viewport.
    expect(html).toContain("absolute inset-x-0 bottom-0")
  })

})

describe("CompileErrorDrawer copy behavior", () => {
  it("writes the full error digest to the clipboard via the pure builder", () => {
    // The copy button delegates to buildCompileErrorClipboardText; assert the
    // exact text contract a clipboard.writeText call would receive.
    const writeText = vi.fn().mockResolvedValue(undefined)
    const text = buildCompileErrorClipboardText(errors)
    writeText(text)
    expect(writeText).toHaveBeenCalledWith(
      [
        "3 compile errors",
        "- phases/draft/SKILL.md:12 - model - Unknown model alias",
        "- GRAPH.md:3 - Dangling edge",
        "- unknown file - Compile request failed",
      ].join("\n"),
    )
  })
})
