import { useEffect, useState, type CSSProperties } from "react"
import { Check, Copy, X } from "lucide-react"

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
 * Compile-error drawer (N3 · COMPILE_LINT-1, geometry fixed under J-04.A).
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
 * Fixed by confining both the overlay and the content horizontally to the
 * canvas's own bounds and vertically to stop above the action bar band,
 * rather than teaching the canvas to shrink around an open drawer (VS Code's
 * Problems panel does the latter — compresses the editor's content area — but
 * that would mean threading a new "drawer open" safe-area into GraphCanvas's
 * fit-view math for a purely cosmetic z-order fix, a much larger blast radius
 * for what is really a two-element positioning conflict). See
 * `canvasScopedContentStyle` / `canvasScopedOverlayStyle` below for the exact
 * geometry, and `isOutsideDismissExempt` for why the action bar and side
 * panels also need to opt out of Radix's default outside-click dismissal.
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

/**
 * Vertical clearance above the true canvas bottom, reserved so neither the
 * dim overlay nor the content panel ever reaches the center action bar.
 *
 * This is a static value, not a measured one — unlike the action bar's WIDTH
 * (genuinely variable per stage's button labels, and measured at runtime in
 * center-action-bar.tsx), its HEIGHT is fixed by its own Tailwind classes
 * (one row of `h-10` buttons in a `p-1 border rounded-full` pill, never more
 * than one line) and does not change at runtime, so measuring it would just
 * be a slower way of writing the same constant. The bar sits `bottom-6`
 * (24px) off the canvas floor with a ~50px pill height (40px buttons + 8px
 * padding + ~2px border); 6rem (96px) clears that with margin to spare.
 */
const ACTION_BAR_CLEARANCE = "6rem"

const canvasScopedContentStyle: CSSProperties = {
  position: "absolute",
  left: CANVAS_LEFT_SAFE_AREA,
  right: CANVAS_RIGHT_SAFE_AREA,
  top: "auto",
  bottom: ACTION_BAR_CLEARANCE,
}

const canvasScopedOverlayStyle: CSSProperties = {
  position: "absolute",
  left: CANVAS_LEFT_SAFE_AREA,
  right: CANVAS_RIGHT_SAFE_AREA,
  top: 0,
  bottom: ACTION_BAR_CLEARANCE,
}

const OUTSIDE_DISMISS_EXEMPT_SELECTORS = [
  '[data-studio-center-action-bar="true"]',
  '[data-studio-left-overlay="true"]',
  '[data-studio-right-overlay="true"]',
]

/**
 * Radix's dismiss-on-outside-pointerdown fires for ANY pointerdown outside
 * the drawer's own Content node — including the center action bar and the
 * two side panels, which sit outside Content regardless of how tightly the
 * drawer's own box is scoped. Left alone, clicking Compile while the drawer
 * is open would close the drawer as a side effect of every retry. Exempting
 * these three regions (the same `data-studio-*` markers center-action-bar.tsx
 * / WorkspaceLeftPanelOverlay / WorkspaceRightPanelOverlay already carry)
 * keeps the drawer open while the user operates them — dismissal is still one
 * click away, on the dimmed canvas backdrop, or Escape.
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
   * -safe-area` custom properties `canvasScopedContentStyle` /
   * `canvasScopedOverlayStyle` reference actually inherit down to the
   * portaled node — they're set via inline style on that host, which
   * `document.body` is not a descendant of. Undefined/null falls back to
   * `document.body` (matches this component's own pre-J-04.A behavior),
   * which only matters for the first paint before Workspace's canvas-host
   * ref is attached — no drawer is ever open that early.
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
  const errorLabel = `${kind} error${errorCount === 1 ? "" : "s"}`

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="bottom"
        showCloseButton={false}
        aria-describedby={undefined}
        data-slot={`${kind}-drawer-content`}
        container={canvasHostElement}
        overlayStyle={canvasScopedOverlayStyle}
        style={canvasScopedContentStyle}
        onPointerDownOutside={(event) => {
          if (isOutsideDismissExempt(event.target)) {
            event.preventDefault()
          }
        }}
        className="max-h-[80vh] min-h-[360px] gap-0 border-t-destructive/40 p-0"
      >
        <div className="flex shrink-0 items-center justify-between gap-2 border-b border-border px-4 py-2">
          <SheetTitle className="text-sm font-medium text-destructive">
            {errorCount} {errorLabel}
          </SheetTitle>
          <div className="flex items-center gap-1">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handleCopyAll}
              aria-label={`Copy all ${kind} errors`}
            >
              {copied ? <Check /> : <Copy />}
              {copied ? "Copied" : "Copy all errors"}
            </Button>
            <SheetClose asChild>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label={`Close ${kind} errors`}
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
