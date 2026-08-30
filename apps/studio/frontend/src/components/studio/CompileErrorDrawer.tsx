import { useEffect, useState, type CSSProperties } from "react"
import { Check, Copy, X } from "lucide-react"
import { useTranslation } from "react-i18next"

import { Button } from "@/components/ui/button"
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetTitle,
} from "@/components/ui/sheet"
import { allowTextSelectionProps } from "@/hooks/useNativeDoubleClickGuard"
import type { CompileError } from "@/api/types"
import { formatDiagnosticCode } from "./field-compile-errors"

/**
 * Compile-error drawer (N3 · COMPILE_LINT-1, geometry fixed under J-04.A,
 * hit-testing fixed under the J-04.A real-machine retry, outside-dismissal
 * exemption fixed under a third J-04.A real-machine round — see
 * `isOutsideDismissExempt` below for that one).
 *
 * When `compile-skill` returns a 422 `CompileFailure`, its `CompileError[]` are
 * surfaced here as a bottom drawer that **auto-opens on compile failure** and
 * lists every error as `file:line - field - message`, with a "copy all" button
 * that writes a human-readable digest to the clipboard (to paste into Copilot /
 * an issue).
 *
 * Built on the shared shadcn `Sheet` (`side="bottom"`). The FROZEN design
 * (`docs/studio/mvp1/02_capabilities/compile-lint/mvp1-alignment.md` §4/§5,
 * COMPILE_LINT-1) calls for a drawer that "只盖画布不挡侧栏" (covers only the
 * canvas, never the side panels) specifically because a full-viewport
 * treatment is *less* operable, not more. A 2026-08-27 real-machine
 * measurement at 1400x900 found the drawer's `fixed inset-0` overlay + content
 * covering the Assets tree, the Copilot/Properties dock, AND the center
 * action bar — `elementFromPoint` on the Compile button's center returned the
 * drawer's own scroll region, so a failed compile made retrying impossible
 * without first closing the drawer.
 *
 * First pass confined the content horizontally to the canvas's own bounds and
 * vertically to stop above the action bar band — the vertical clearance was
 * later REMOVED by user ruling (2026-08-27): the center action bar is part of
 * the canvas, the drawer covers the canvas, so it covers the bar too; a
 * drawer floating a band's height above the true bottom edge just looks
 * broken. Retrying Compile while the drawer is open goes through closing it
 * first (Escape, X, or a click on the blank canvas). The HORIZONTAL
 * confinement stays — the side panels are not canvas.
 * But the second real-machine pass ALSO found an independent bug the first pass's jsdom
 * tests could not see: Radix's Dialog defaults to `modal={true}`, which sets
 * `document.body.style.pointerEvents = "none"` while open (see
 * `@radix-ui/react-dismissable-layer`'s `disableOutsidePointerEvents` effect).
 * That lock makes the action bar (an ordinary DOM element with no explicit
 * pointer-events override) hit-test-invisible to a REAL mouse click — the
 * browser resolves the click to whatever's underneath that DOES keep
 * `pointer-events: auto` (a ReactFlow canvas node, in the reported case),
 * which then swallowed the click **and** got selected, while the drawer
 * closed as an unrelated side effect of that same click landing "outside"
 * Content. jsdom's `dispatchEvent`/`.click()` target an element directly and
 * never perform coordinate-based hit-testing, so a jsdom test asserting "the
 * button's onClick fired" cannot fail this way regardless of the pointer-events
 * lock — the previous suite's integration test was passing for the wrong
 * reason. `modal={false}` (below) removes the lock at its source instead of
 * patching around it: VS Code's Problems panel and Radix's own docs both
 * treat a non-blocking side panel as the non-modal case, not a modal dialog
 * with a hole punched in it.
 *
 * `modal={false}` also has a side effect worth naming: Radix's `Dialog.Overlay`
 * unconditionally renders nothing when non-modal (it's an
 * `context.modal ? <Impl/> : null` branch inside `@radix-ui/react-dialog`
 * itself, not something this component's own props can override), so the dim
 * backdrop is gone. The FROZEN design text ("只盖画布…自动弹") only requires the
 * drawer PANEL to cover the canvas, not a separate scrim, and a still-rendered
 * scrim would have to re-solve the exact "block the canvas without blocking
 * the action bar" problem this fix removes — so this drops the scrim rather
 * than rebuilding it by hand. "Click the blank canvas closes the drawer" still
 * holds without one: Radix's outside-interaction detection
 * (`isOutsideDismissExempt` below) is a set of DOM-event listeners, not
 * something the overlay element implements by being clicked.
 */

/**
 * Horizontal bounds: the same `--studio-canvas-left-safe-area` /
 * `-right-safe-area` custom properties `center-action-bar.tsx` already
 * clamps its own centering against — published as inline style on
 * Workspace's canvas host (`workspaceOverlayStyle`), so they track the
 * Assets tree / Copilot dock's actual widths without this component needing
 * to know about either.
 */
const CANVAS_LEFT_SAFE_AREA = "var(--studio-canvas-left-safe-area, 0px)"
const CANVAS_RIGHT_SAFE_AREA = "var(--studio-canvas-right-safe-area, 0px)"

const canvasScopedContentStyle: CSSProperties = {
  position: "absolute",
  left: CANVAS_LEFT_SAFE_AREA,
  right: CANVAS_RIGHT_SAFE_AREA,
  top: "auto",
  // The true canvas bottom (user ruling 2026-08-27): the center action bar
  // belongs to the canvas and gets covered along with it — no reserved
  // clearance band peeking out underneath the sheet.
  bottom: 0,
}

const OUTSIDE_DISMISS_EXEMPT_SELECTORS = [
  '[data-studio-left-overlay="true"]',
  '[data-studio-right-overlay="true"]',
  // The rail is the side panels' own switch (R3-15, 批示轮三): opening or
  // swapping a panel through it is operating the panels, so it inherits the
  // same exemption — otherwise every panel switch while triaging errors
  // closes the drawer as a side effect.
  '[data-studio-rail="true"]',
]

/**
 * Radix's dismiss-on-outside-interaction fires for ANY interaction outside
 * the drawer's own Content node — including the two side panels, which sit
 * outside Content regardless of how tightly the drawer's own box is scoped.
 * Left alone, operating them while the drawer is open would close it as a
 * side effect of every fix. Exempting the two panel regions (the same
 * `data-studio-*` markers WorkspaceLeftPanelOverlay /
 * WorkspaceRightPanelOverlay already carry) plus the rail that switches
 * them (Toolbar's `data-studio-rail`, R3-15) keeps the drawer open while
 * the user operates them — dismissal is still one click away, on the blank
 * canvas, or Escape. (The center action bar used to be a third exempt region;
 * since the 2026-08-27 ruling the drawer covers it outright, so a click can
 * never land there while the drawer is open.)
 *
 * "ANY interaction" is not just pointerdown. A 2026-08-27 real-machine retry
 * (round 3) found clicking a FOCUSABLE element inside the exempt regions —
 * an Assets tree row, opening GRAPH.md into the editor — still closed the
 * drawer, even with the pointerdown channel exempted. Reading
 * @radix-ui/react-dismissable-layer's source (installed at
 * node_modules/@radix-ui/react-dialog's dependency) explains why:
 * `DismissableLayer` runs TWO independent outside-detection paths —
 * `usePointerDownOutside` (document `pointerdown`) and `useFocusOutside`
 * (document `focusin`, for focus moved via keyboard OR by a mouse click
 * landing on a focusable element) — and EITHER one calls `onDismiss()` on its
 * own if not prevented. `onPointerDownOutside` only intercepts the first
 * path; clicking a tree row moves DOM focus there, which the second path
 * treats as an independent dismiss trigger jsdom's `.click()` never exercised
 * (it does not reliably move `document.activeElement` the way a real pointer
 * click does). Both paths funnel through `onInteractOutside` before checking
 * `event.defaultPrevented` — `pointerDownOutside`'s handler runs
 * `onPointerDownOutside?.(event); onInteractOutside?.(event); if
 * (!event.defaultPrevented) onDismiss?.()`, and `focusOutside`'s handler runs
 * the same shape with `onFocusOutside` in place of `onPointerDownOutside` —
 * so intercepting on `onInteractOutside` alone (instead of duplicating this
 * check across `onPointerDownOutside` AND `onFocusOutside`) covers both.
 */
export function isOutsideDismissExempt(target: EventTarget | null): boolean {
  if (!(target instanceof Element)) {
    return false
  }
  return OUTSIDE_DISMISS_EXEMPT_SELECTORS.some((selector) => target.closest(selector) !== null)
}

export function formatCompileErrorLine(error: CompileError): string {
  const location = error.file
    ? `${error.file}${error.line ? `:${error.line}` : ""}`
    : "unknown file"
  const parts = [location]
  if (error.field) {
    parts.push(error.field)
  }
  const code = formatDiagnosticCode(error.error_code)
  if (code) {
    parts.push(code)
  }
  parts.push(error.message)
  return parts.join(" - ")
}

type DiagnosticKind = "compile" | "predict" | "run"

export function buildCompileErrorClipboardText(
  errors: readonly CompileError[],
  kind: DiagnosticKind = "compile",
): string {
  const count = errors.length
  const heading = `${count} ${kind} error${count === 1 ? "" : "s"}`
  const lines = errors.flatMap((error) => [
    `- ${formatCompileErrorLine(error)}`,
    ...(error.details ?? []).map((detail) => `  ${detail}`),
  ])
  return [heading, ...lines].join("\n")
}

type CompileErrorDrawerProps = {
  errors: CompileError[]
  open: boolean
  onOpenChange: (open: boolean) => void
  kind?: DiagnosticKind
  /**
   * The canvas host element to portal into instead of `document.body` (see
   * `SheetContent`'s `container` prop). Needed so the `--studio-canvas-*
   * -safe-area` custom properties `canvasScopedContentStyle` references
   * actually inherit down to the portaled node — they're set via inline
   * style on that host, which `document.body` is not a descendant of.
   * Undefined/null falls back to `document.body` (matches this component's
   * own pre-J-04.A behavior), which only matters for the first paint before
   * Workspace's canvas-host ref is attached — no drawer is ever open that
   * early.
   */
  canvasHostElement?: HTMLElement | null
}

export function CompileErrorDrawer({
  errors,
  open,
  onOpenChange,
  kind = "compile",
  canvasHostElement,
}: CompileErrorDrawerProps) {
  const { t } = useTranslation("studioShell")
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (!copied) {
      return
    }
    const timer = setTimeout(() => setCopied(false), 2000)
    return () => clearTimeout(timer)
  }, [copied])

  async function handleCopyAll() {
    const text = buildCompileErrorClipboardText(errors, kind)
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
    } catch (error) {
      // Surface, never swallow: copy is the drawer's headline affordance, so a
      // failure must be observable rather than a silent no-op.
      console.error(`Failed to copy ${kind} errors to clipboard`, error)
    }
  }

  const errorCount = errors.length

  return (
    // modal={false}: see the module docstring above — the default modal Dialog
    // locks `document.body.style.pointerEvents = "none"` while open, which a
    // real mouse click's hit-testing respects but jsdom's direct-dispatch
    // tests cannot see. Non-modal removes that lock at its source (Radix's own
    // distinction for a panel meant to stay usable alongside the page, not a
    // blocking dialog) rather than trying to carve a hole in it.
    <Sheet open={open} onOpenChange={onOpenChange} modal={false}>
      <SheetContent
        side="bottom"
        showCloseButton={false}
        aria-describedby={undefined}
        data-slot={`${kind}-drawer-content`}
        container={canvasHostElement}
        style={canvasScopedContentStyle}
        onInteractOutside={(event) => {
          if (isOutsideDismissExempt(event.target)) {
            event.preventDefault()
          }
        }}
        className="max-h-[80vh] min-h-[360px] gap-0 border-t-destructive/40 p-0"
      >
        <div className="flex shrink-0 items-center justify-between gap-2 border-b border-border px-4 py-2">
          <SheetTitle className="text-sm font-medium text-destructive">
            {t("compileDrawer.title", { count: errorCount, kind })}
          </SheetTitle>
          <div className="flex items-center gap-1">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handleCopyAll}
              aria-label={t("compileDrawer.copyAllAriaLabel", { kind })}
            >
              {copied ? <Check /> : <Copy />}
              {copied ? t("compileDrawer.copied") : t("compileDrawer.copyAll")}
            </Button>
            <SheetClose asChild>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label={t("compileDrawer.closeAriaLabel", { kind })}
              >
                <X />
              </Button>
            </SheetClose>
          </div>
        </div>
        {/*
          The app-wide text-selection guard disables user-select/selectstart/copy
          everywhere; opt this read-only error list back in (via the allow-list
          helper) so users can select & copy individual messages natively,
          alongside the "copy all" button. See useNativeDoubleClickGuard.
        */}
        <div
          {...allowTextSelectionProps()}
          className="min-h-0 flex-1 space-y-2 overflow-auto px-4 py-3 select-text"
        >
          {errors.map((error, index) => {
            const code = formatDiagnosticCode(error.error_code)
            return (
              <div
                key={`${error.file ?? "compile"}-${error.line ?? "x"}-${index}`}
                className="text-xs text-muted-foreground"
              >
                <span className="font-medium text-foreground">
                  {error.file ?? "unknown file"}
                  {error.line ? `:${error.line}` : ""}
                </span>
                {error.field ? <span> - {error.field}</span> : null}
                {code ? <span> - {code}</span> : null}
                <span> - {error.message}</span>
                {error.details?.length ? (
                  <div className="mt-1 space-y-1 pl-3 font-mono text-[11px] leading-relaxed text-muted-foreground">
                    {error.details.map((detail, detailIndex) => (
                      <div key={`${detailIndex}-${detail}`}>{detail}</div>
                    ))}
                  </div>
                ) : null}
              </div>
            )
          })}
        </div>
      </SheetContent>
    </Sheet>
  )
}
