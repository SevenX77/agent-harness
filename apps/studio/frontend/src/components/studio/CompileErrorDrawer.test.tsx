// @vitest-environment jsdom
import { act } from "react"
import { createRoot, type Root } from "react-dom/client"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import {
  CompileErrorDrawer,
  buildCompileErrorClipboardText,
  formatCompileErrorLine,
  isOutsideDismissExempt,
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

  it("wraps diagnostic codes in brackets when present", () => {
    expect(formatCompileErrorLine(makeError({ error_code: "F-v3-graph-io-schema-invalid" }))).toBe(
      "phases/draft/SKILL.md:12 - model - [F-v3-graph-io-schema-invalid] - Unknown model alias",
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

  it("includes diagnostic detail lines in the clipboard digest", () => {
    const text = buildCompileErrorClipboardText([
      makeError({
        file: null,
        line: null,
        field: null,
        message: "Backend unavailable",
        details: [
          "Request: POST http://127.0.0.1:8787/api/skills/writer-smoke/runs/predict",
          "Axios code: ERR_NETWORK",
          "Original error: Network Error",
        ],
      }),
    ], "predict")

    expect(text).toBe(
      [
        "1 predict error",
        "- unknown file - Backend unavailable",
        "  Request: POST http://127.0.0.1:8787/api/skills/writer-smoke/runs/predict",
        "  Axios code: ERR_NETWORK",
        "  Original error: Network Error",
      ].join("\n"),
    )
  })

  it("uses the singular form for a single error", () => {
    const text = buildCompileErrorClipboardText([makeError()])
    expect(text.startsWith("1 compile error\n")).toBe(true)
  })

  it("uses the supplied diagnostic label for predict failures", () => {
    const text = buildCompileErrorClipboardText([makeError()], "predict")
    expect(text.startsWith("1 predict error\n")).toBe(true)
    expect(text).toContain("Unknown model alias")
  })

  it("uses the supplied diagnostic label for run failures", () => {
    const text = buildCompileErrorClipboardText([makeError()], "run")
    expect(text.startsWith("1 run error\n")).toBe(true)
    expect(text).toContain("Unknown model alias")
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

  it("confines the dim overlay and the panel to the canvas's own horizontal bounds, not the full viewport", () => {
    // J-04.A (2026-08-27 real-machine measurement): the old `fixed inset-0`
    // treatment covered the Assets tree, the Copilot/Properties dock, AND the
    // center action bar — this asserts the fix, not the old defect. Both the
    // overlay and the content anchor their left/right edges to the same
    // `--studio-canvas-*-safe-area` custom properties center-action-bar.tsx
    // already clamps its own horizontal position against (published by
    // Workspace's canvas host), instead of the viewport-spanning `inset-x-0`.
    render(true)
    const overlay = document.body.querySelector('[data-slot="sheet-overlay"]') as HTMLElement | null
    const content = document.body.querySelector('[data-slot="compile-drawer-content"]') as HTMLElement | null
    expect(overlay).not.toBeNull()
    expect(content).not.toBeNull()
    for (const node of [overlay, content]) {
      expect(node?.style.position).toBe("absolute")
      expect(node?.style.left).toBe("var(--studio-canvas-left-safe-area, 0px)")
      expect(node?.style.right).toBe("var(--studio-canvas-right-safe-area, 0px)")
    }
    expect(content?.getAttribute("data-side")).toBe("bottom")
  })

  it("stops short of the true bottom edge so the center action bar band stays uncovered", () => {
    // The action bar floats at `bottom-6` inside the same canvas host; both the
    // overlay and the content reserve the same clearance above it so neither
    // dims nor overlaps the Compile/Predict/Run pill.
    render(true)
    const overlay = document.body.querySelector('[data-slot="sheet-overlay"]') as HTMLElement | null
    const content = document.body.querySelector('[data-slot="compile-drawer-content"]') as HTMLElement | null
    expect(overlay?.style.bottom).not.toBe("0px")
    expect(overlay?.style.bottom).toBe(content?.style.bottom)
    expect(overlay?.style.top).toBe("0px")
  })

  it("portals into the supplied canvas host element instead of always defaulting to document.body", () => {
    // Radix's default Portal target (document.body) sits outside the DOM
    // subtree that carries the `--studio-canvas-*-safe-area` custom
    // properties (set via inline style on Workspace's canvas host), so the
    // vars asserted above would silently resolve to nothing unless the
    // drawer is portaled INSIDE that subtree.
    const host = document.createElement("div")
    host.setAttribute("data-testid", "canvas-host")
    document.body.appendChild(host)
    act(() => {
      root.render(
        <CompileErrorDrawer errors={errors} open onOpenChange={() => {}} canvasHostElement={host} />,
      )
    })
    expect(host.querySelector('[data-slot="compile-drawer-content"]')).not.toBeNull()
    host.remove()
  })

  it("can render the same bottom-sheet treatment for predict errors", () => {
    act(() => {
      root.render(
        <CompileErrorDrawer
          errors={[
            makeError({
              file: null,
              line: null,
              field: null,
              message: "Backend unavailable",
              details: [
                "Request: POST http://127.0.0.1:8787/api/skills/writer-smoke/runs/predict",
                "Axios code: ERR_NETWORK",
                "Original error: Network Error",
              ],
            }),
          ]}
          open
          onOpenChange={() => {}}
          kind="predict"
        />,
      )
    })

    const text = document.body.textContent ?? ""
    expect(text).toContain("1 predict error")
    expect(text).toContain("Backend unavailable")
    expect(text).toContain("Request: POST http://127.0.0.1:8787/api/skills/writer-smoke/runs/predict")
    expect(text).toContain("Axios code: ERR_NETWORK")
    expect(text).toContain("Original error: Network Error")
    expect(document.body.querySelector('[aria-label="Copy all predict errors"]')).not.toBeNull()
    expect(document.body.querySelector('[data-slot="predict-drawer-content"]')).not.toBeNull()
  })

  it("can render the same bottom-sheet treatment for run errors", () => {
    act(() => {
      root.render(
        <CompileErrorDrawer
          errors={[makeError({ file: null, line: null, field: null, message: "Backend unavailable" })]}
          open
          onOpenChange={() => {}}
          kind="run"
        />,
      )
    })

    const text = document.body.textContent ?? ""
    expect(text).toContain("1 run error")
    expect(text).toContain("Backend unavailable")
    expect(document.body.querySelector('[aria-label="Copy all run errors"]')).not.toBeNull()
    expect(document.body.querySelector('[data-slot="run-drawer-content"]')).not.toBeNull()
  })
})

describe("isOutsideDismissExempt", () => {
  // Radix's dismiss-on-outside-pointerdown fires for ANY click outside the
  // drawer's own Content node, regardless of whether the (now-scoped) overlay
  // visually covers that spot. Exempting the action bar and the two side
  // panels keeps the drawer open while the user operates them — the same
  // `data-studio-*` markers those three components already carry.
  function elementWithMarker(selectorAttr: string): HTMLElement {
    const marker = document.createElement("div")
    marker.setAttribute(selectorAttr, "true")
    const button = document.createElement("button")
    marker.appendChild(button)
    document.body.appendChild(marker)
    return button
  }

  afterEach(() => {
    document.body.innerHTML = ""
  })

  it("exempts a click inside the center action bar", () => {
    expect(isOutsideDismissExempt(elementWithMarker("data-studio-center-action-bar"))).toBe(true)
  })

  it("exempts a click inside the left (Assets) overlay", () => {
    expect(isOutsideDismissExempt(elementWithMarker("data-studio-left-overlay"))).toBe(true)
  })

  it("exempts a click inside the right (Copilot/Properties) overlay", () => {
    expect(isOutsideDismissExempt(elementWithMarker("data-studio-right-overlay"))).toBe(true)
  })

  it("does not exempt a click on an unrelated canvas element", () => {
    const plain = document.createElement("div")
    document.body.appendChild(plain)
    expect(isOutsideDismissExempt(plain)).toBe(false)
  })

  it("does not exempt a non-Element target", () => {
    expect(isOutsideDismissExempt(null)).toBe(false)
    expect(isOutsideDismissExempt(document)).toBe(false)
  })
})

describe("CompileErrorDrawer keeps the center action bar operable while open", () => {
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

  it("still fires the action bar button's own click handler, and does not dismiss the drawer, when clicked while open", () => {
    const onOpenChange = vi.fn()
    const onCompileClick = vi.fn()
    const actionBar = document.createElement("div")
    actionBar.setAttribute("data-studio-center-action-bar", "true")
    const compileButton = document.createElement("button")
    compileButton.textContent = "Compile"
    compileButton.addEventListener("click", onCompileClick)
    actionBar.appendChild(compileButton)
    document.body.appendChild(actionBar)

    act(() => {
      root.render(<CompileErrorDrawer errors={errors} open onOpenChange={onOpenChange} />)
    })
    expect(document.body.querySelector('[data-slot="compile-drawer-content"]')).not.toBeNull()

    // Same dispatch idiom CommunitySharingConsentDialog.test.tsx uses for a
    // real Radix outside-pointerdown sequence — jsdom lacks PointerEvent, but
    // Radix's DismissableLayer listens by event *type*, which a plain
    // MouseEvent constructed with that type still satisfies.
    act(() => {
      compileButton.dispatchEvent(new MouseEvent("pointerdown", { bubbles: true }))
      compileButton.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }))
      compileButton.dispatchEvent(new MouseEvent("pointerup", { bubbles: true }))
      compileButton.click()
    })

    expect(onCompileClick).toHaveBeenCalledTimes(1)
    expect(onOpenChange).not.toHaveBeenCalledWith(false)

    actionBar.remove()
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
