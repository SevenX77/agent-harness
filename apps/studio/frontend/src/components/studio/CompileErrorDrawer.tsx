import { useEffect, useState } from "react"
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

/**
 * Compile-error drawer (N3 · COMPILE_LINT-1).
 *
 * When `compile-skill` returns a 422 `CompileFailure`, its `CompileError[]` are
 * surfaced here as a bottom drawer that **auto-opens on compile failure** and
 * lists every error as `file:line - field - message`, with a "copy all" button
 * that writes a human-readable digest to the clipboard (to paste into Copilot /
 * an issue).
 *
 * Built on the shared shadcn `Sheet` (`side="bottom"`): the modal overlay dims
 * and blurs the whole UI, the center action bar (Compile/Predict/Run) stays put
 * underneath and is covered rather than nudged, and clicking the blank area above
 * — or pressing Escape — dismisses the drawer. A fixed `min-h` keeps the panel a
 * comfortable height even for a single error.
 */

export function formatCompileErrorLine(error: CompileError): string {
  const location = error.file
    ? `${error.file}${error.line ? `:${error.line}` : ""}`
    : "unknown file"
  const parts = [location]
  if (error.field) {
    parts.push(error.field)
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
  const lines = errors.map((error) => `- ${formatCompileErrorLine(error)}`)
  return [heading, ...lines].join("\n")
}

type CompileErrorDrawerProps = {
  errors: CompileError[]
  open: boolean
  onOpenChange: (open: boolean) => void
  kind?: DiagnosticKind
}

export function CompileErrorDrawer({ errors, open, onOpenChange, kind = "compile" }: CompileErrorDrawerProps) {
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
          {errors.map((error, index) => (
            <div
              key={`${error.file ?? "compile"}-${error.line ?? "x"}-${index}`}
              className="text-xs text-muted-foreground"
            >
              <span className="font-medium text-foreground">
                {error.file ?? "unknown file"}
                {error.line ? `:${error.line}` : ""}
              </span>
              {error.field ? <span> - {error.field}</span> : null}
              <span> - {error.message}</span>
            </div>
          ))}
        </div>
      </SheetContent>
    </Sheet>
  )
}
