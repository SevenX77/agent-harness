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

  it("confines the panel to the canvas's own horizontal bounds, not the full viewport", () => {
    // J-04.A (2026-08-27 real-machine measurement): the old `fixed inset-0`
    // treatment covered the Assets tree, the Copilot/Properties dock, AND the
    // center action bar — this asserts the fix, not the old defect. The
    // content anchors its left/right edges to the same
    // `--studio-canvas-*-safe-area` custom properties center-action-bar.tsx
    // already clamps its own horizontal position against (published by
    // Workspace's canvas host), instead of the viewport-spanning `inset-x-0`.
    // Real-machine confirmation (1400x900, journey-m4-verify fixture): content
    // rect (456,444,548,360) sits strictly inside the canvas — left panel ends
    // at x=444, right panel starts at x=1016.
    render(true)
    const content = document.body.querySelector('[data-slot="compile-drawer-content"]') as HTMLElement | null
    expect(content).not.toBeNull()
    expect(content?.style.position).toBe("absolute")
    expect(content?.style.left).toBe("var(--studio-canvas-left-safe-area, 0px)")
    expect(content?.style.right).toBe("var(--studio-canvas-right-safe-area, 0px)")
    expect(content?.getAttribute("data-side")).toBe("bottom")
  })

  it("stops short of the true bottom edge so the center action bar band stays uncovered", () => {
    // The action bar floats at `bottom-6` inside the same canvas host; the
    // content reserves clearance above it so it never overlaps the
    // Compile/Predict/Run pill. Real-machine confirmation: content bottom
    // edge (804px) sits above the action bar's top (831px) at 1400x900.
    render(true)
    const content = document.body.querySelector('[data-slot="compile-drawer-content"]') as HTMLElement | null
    expect(content?.style.bottom).not.toBe("0px")
    expect(content?.style.bottom).toBe("6rem")
  })

  it("renders no dim overlay — modal={false} makes Radix's Dialog.Overlay a no-op by design", () => {
    // @radix-ui/react-dialog's DialogOverlay is `context.modal ? <Impl/> : null`
    // unconditionally, regardless of any className/style passed to it — so a
    // non-modal Sheet (see below) never puts a scrim in the DOM at all. This
    // pins that as an intended consequence, not a regression to chase: the
    // FROZEN design only requires the drawer PANEL to cover the canvas, and a
    // still-present scrim would have to re-solve the exact "block the canvas
    // without blocking the action bar" problem modal={false} removes.
    render(true)
    expect(document.body.querySelector('[data-slot="sheet-overlay"]')).toBeNull()
  })

  it("never locks the page: does not set document.body.style.pointerEvents to \"none\" while open", () => {
    // The real-machine regression this test stands in for: Radix's default
    // `modal={true}` Dialog disables outside pointer events via
    // `document.body.style.pointerEvents = "none"`
    // (@radix-ui/react-dismissable-layer's `disableOutsidePointerEvents`
    // effect) — a real DOM mutation jsdom faithfully reproduces. A real mouse
    // click's coordinate-based hit-testing respects that lock (the action bar
    // becomes hit-test-invisible, so the click falls through to whatever
    // canvas element underneath keeps its own `pointer-events: auto`); jsdom's
    // `dispatchEvent`/`.click()` do not do coordinate-based hit-testing at
    // all, which is exactly why the PREVIOUS suite's click-through test could
    // not catch this — it dispatched straight at the target element,
    // bypassing the one CSS property the real bug lived in. This assertion
    // checks that literal property directly instead.
    expect(document.body.style.pointerEvents).not.toBe("none")
    render(true)
    expect(document.body.style.pointerEvents).not.toBe("none")
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

  // Radix's DismissableLayer (@radix-ui/react-dismissable-layer) attaches its
  // document-level outside-pointerdown listener inside a `setTimeout(fn, 0)`
  // — deliberately, so the SAME click that opened the dialog is not
  // immediately seen as "outside". A synchronous test that renders open and
  // dispatches in the same tick never lets that macrotask run, so Radix's
  // listener is not attached yet: the dispatch reaches the button directly
  // and proves nothing about Radix's own dismiss behavior either way. Flushing
  // one real macrotask after render is what makes these tests exercise the
  // actual mechanism instead of a no-op.
  async function flushOutsidePointerDownListenerAttachment() {
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0))
    })
  }

  function dispatchRealClick(target: HTMLElement) {
    act(() => {
      target.dispatchEvent(new MouseEvent("pointerdown", { bubbles: true }))
      target.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }))
      target.dispatchEvent(new MouseEvent("pointerup", { bubbles: true }))
      target.click()
    })
  }

  it("still fires the action bar button's own click handler, and does not dismiss the drawer, when clicked while open", async () => {
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
    await flushOutsidePointerDownListenerAttachment()

    // Same dispatch idiom CommunitySharingConsentDialog.test.tsx uses for a
    // real Radix outside-pointerdown sequence — jsdom lacks PointerEvent, but
    // Radix's DismissableLayer listens by event *type*, which a plain
    // MouseEvent constructed with that type still satisfies.
    dispatchRealClick(compileButton)

    expect(onCompileClick).toHaveBeenCalledTimes(1)
    expect(onOpenChange).not.toHaveBeenCalledWith(false)

    actionBar.remove()
  })

  it("control: a click on an unrelated (non-exempt) outside element still dismisses the drawer", async () => {
    // Proves the exemption is narrow, not a side effect of the test harness
    // failing to reach Radix's real dismiss path at all — if this control
    // did not close, the "stays open" assertion above would be meaningless.
    const onOpenChange = vi.fn()
    const canvasNode = document.createElement("div")
    canvasNode.setAttribute("data-testid", "react-flow__node-globalOutput")
    document.body.appendChild(canvasNode)

    act(() => {
      root.render(<CompileErrorDrawer errors={errors} open onOpenChange={onOpenChange} />)
    })
    await flushOutsidePointerDownListenerAttachment()

    dispatchRealClick(canvasNode)

    expect(onOpenChange).toHaveBeenCalledWith(false)

    canvasNode.remove()
  })

  // Round 3 (2026-08-27 real-machine retry): clicking a FOCUSABLE row inside
  // an exempt region — an Assets tree folder/file — still closed the drawer
  // even with the pointerdown channel exempted, because Radix's
  // DismissableLayer runs a SEPARATE `useFocusOutside` path (document
  // `focusin`) that calls its own `onDismiss()` independently of the
  // pointerdown path. jsdom's `.click()` does not reliably move
  // `document.activeElement` the way a real mouse click does, so these tests
  // drive the focus shift explicitly via `.focus()` — the previous suite's
  // exemption tests never exercised this channel at all, which is exactly why
  // the real machine caught something jsdom didn't.
  function dispatchRealClickThatMovesFocus(target: HTMLElement) {
    act(() => {
      target.dispatchEvent(new MouseEvent("pointerdown", { bubbles: true }))
      target.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }))
      target.focus()
      target.dispatchEvent(new MouseEvent("pointerup", { bubbles: true }))
      target.click()
    })
  }

  it("stays open when a focusable row inside the left (Assets) overlay is clicked, and the row's own click still fires", async () => {
    const onOpenChange = vi.fn()
    const onFolderClick = vi.fn()
    const leftOverlay = document.createElement("div")
    leftOverlay.setAttribute("data-studio-left-overlay", "true")
    const folderRow = document.createElement("button")
    folderRow.textContent = "phases"
    folderRow.addEventListener("click", onFolderClick)
    leftOverlay.appendChild(folderRow)
    document.body.appendChild(leftOverlay)

    act(() => {
      root.render(<CompileErrorDrawer errors={errors} open onOpenChange={onOpenChange} />)
    })
    await flushOutsidePointerDownListenerAttachment()

    dispatchRealClickThatMovesFocus(folderRow)

    expect(onFolderClick).toHaveBeenCalledTimes(1)
    expect(onOpenChange).not.toHaveBeenCalledWith(false)

    leftOverlay.remove()
  })

  it("stays open when a focusable row inside the right (Copilot/Properties) overlay is clicked, and the row's own click still fires", async () => {
    const onOpenChange = vi.fn()
    const onModelCardClick = vi.fn()
    const rightOverlay = document.createElement("div")
    rightOverlay.setAttribute("data-studio-right-overlay", "true")
    const modelCard = document.createElement("button")
    modelCard.textContent = "gpt-5"
    modelCard.addEventListener("click", onModelCardClick)
    rightOverlay.appendChild(modelCard)
    document.body.appendChild(rightOverlay)

    act(() => {
      root.render(<CompileErrorDrawer errors={errors} open onOpenChange={onOpenChange} />)
    })
    await flushOutsidePointerDownListenerAttachment()

    dispatchRealClickThatMovesFocus(modelCard)

    expect(onModelCardClick).toHaveBeenCalledTimes(1)
    expect(onOpenChange).not.toHaveBeenCalledWith(false)

    rightOverlay.remove()
  })

  it("control: focusing an unrelated (non-exempt) element still dismisses the drawer via the focus channel", async () => {
    // Proves the focus-channel exemption is narrow and the test harness
    // genuinely reaches Radix's real onFocusOutside path — mirrors the
    // pointerdown control test above for the separate channel round 3 found.
    const onOpenChange = vi.fn()
    const editorSurface = document.createElement("button")
    editorSurface.textContent = "GRAPH.md editor"
    document.body.appendChild(editorSurface)

    act(() => {
      root.render(<CompileErrorDrawer errors={errors} open onOpenChange={onOpenChange} />)
    })
    await flushOutsidePointerDownListenerAttachment()

    act(() => {
      editorSurface.focus()
    })

    expect(onOpenChange).toHaveBeenCalledWith(false)

    editorSurface.remove()
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
