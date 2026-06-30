// @vitest-environment jsdom
import { act } from "react"
import { createRoot, type Root } from "react-dom/client"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
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

// The drawer is built on the shared shadcn Sheet, which portals its overlay +
// content into document.body — so these mount into a real (jsdom) DOM and assert
// against the portaled markup rather than SSR output.
describe("CompileErrorDrawer rendering", () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    container = document.createElement("div")
    document.body.appendChild(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
    document.body.innerHTML = ""
  })

  function render(open: boolean) {
    act(() => {
      root.render(<CompileErrorDrawer errors={errors} open={open} onOpenChange={() => {}} />)
    })
  }

  it("lists every error as file:line - field - message when open", () => {
    render(true)
    const text = document.body.textContent ?? ""
    expect(text).toContain("phases/draft/SKILL.md")
    expect(text).toContain(":12")
    expect(text).toContain("model")
    expect(text).toContain("Unknown model alias")
    expect(text).toContain("Dangling edge")
    expect(text).toContain("Compile request failed")
    expect(text).toContain("3 compile errors")
  })

  it("exposes a copy-all-errors button", () => {
    render(true)
    expect(
      document.body.querySelector('[aria-label="Copy all compile errors"]'),
    ).not.toBeNull()
  })

  it("renders nothing when closed", () => {
    render(false)
    expect(document.body.querySelector('[data-slot="compile-drawer-content"]')).toBeNull()
  })

  it("marks the error list as natively selectable so messages can be copied by hand", () => {
    // The app-wide text-selection guard disables user-select / selectstart / copy
    // on the body; the error content opts back in via the data-allow-text-selection
    // allow-list entry (see useNativeDoubleClickGuard / TEXT_SELECTION_ALLOWLIST).
    render(true)
    const content = document.body.querySelector('[data-slot="compile-drawer-content"]')
    const selectable = content?.querySelector("[data-allow-text-selection]")
    expect(selectable).not.toBeNull()
    expect(selectable?.textContent).toContain("Unknown model alias")
  })

  it("covers the whole UI: a viewport overlay dims the page behind the bottom sheet", () => {
    // The drawer deliberately covers the canvas + the center action bar beneath it:
    // a full-viewport modal overlay, and a bottom-anchored content panel. Clicking
    // the overlay (the blank area above) dismisses it via Radix's modal behavior.
    render(true)
    const overlay = document.body.querySelector('[data-slot="sheet-overlay"]')
    expect(overlay).not.toBeNull()
    expect(overlay?.className).toContain("fixed")
    expect(overlay?.className).toContain("inset-0")
    const content = document.body.querySelector('[data-slot="compile-drawer-content"]')
    expect(content?.getAttribute("data-side")).toBe("bottom")
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
