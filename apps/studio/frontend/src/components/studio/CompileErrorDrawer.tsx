import { useEffect, useState } from "react"
import * as DialogPrimitive from "@radix-ui/react-dialog"
import { Check, Copy, X } from "lucide-react"

import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import type { CompileError } from "@/api/types"

/**
 * Canvas-scoped Compile error drawer (N3 · COMPILE_LINT-1).
 *
 * When `compile-skill` returns a 422 `CompileFailure`, its `CompileError[]` are
 * surfaced here as a bottom drawer that **auto-opens on compile failure** and
 * lists every error as `file:line - field - message`, with a top "copy all"
 * button that writes a human-readable digest to the clipboard (to paste into
 * Copilot / an issue).
 *
 * IMPORTANT — canvas-scoped, NOT viewport-scoped. The local `ui/sheet.tsx`
 * (and the bare Radix `Dialog.Portal` + `fixed inset-0` pattern) cover the whole
 * viewport, which would blanket the left file-tree and right Copilot sidebars and
 * violate the "only cover the canvas" requirement. This variant therefore:
 *   - renders WITHOUT a Portal, so the content stays inside the canvas DOM
 *     subtree (the parent `<div className="relative size-full">`);
 *   - is `modal={false}`, so it does NOT trap interaction or dim the page — the
 *     user can keep operating the file tree / canvas while reading the errors;
 *   - pins the content with `absolute inset-x-0 bottom-0`, so it is clipped to
 *     the canvas container and pinned to its bottom edge, never the viewport.
 * Radix Dialog still provides Escape-to-close and focus management.
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

export function buildCompileErrorClipboardText(errors: readonly CompileError[]): string {
  const count = errors.length
  const heading = `${count} compile error${count === 1 ? "" : "s"}`
  const lines = errors.map((error) => `- ${formatCompileErrorLine(error)}`)
  return [heading, ...lines].join("\n")
}

type CompileErrorDrawerProps = {
  errors: CompileError[]
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function CompileErrorDrawer({ errors, open, onOpenChange }: CompileErrorDrawerProps) {
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (!copied) {
      return
    }
    const timer = setTimeout(() => setCopied(false), 2000)
    return () => clearTimeout(timer)
  }, [copied])

  async function handleCopyAll() {
    const text = buildCompileErrorClipboardText(errors)
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
    } catch (error) {
      // Surface, never swallow: copy is the drawer's headline affordance, so a
      // failure must be observable rather than a silent no-op.
      console.error("Failed to copy compile errors to clipboard", error)
    }
  }

  const errorCount = errors.length

  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange} modal={false}>
      <DialogPrimitive.Content
        data-slot="compile-drawer-content"
        aria-describedby={undefined}
        onInteractOutside={(event) => event.preventDefault()}
        className={cn(
          "absolute inset-x-0 bottom-0 z-40 flex max-h-[60%] flex-col",
          "border-t border-destructive/40 bg-popover text-popover-foreground shadow-lg",
          "data-open:animate-in data-open:slide-in-from-bottom-10 data-closed:animate-out data-closed:slide-out-to-bottom-10",
        )}
      >
        <div className="flex shrink-0 items-center justify-between gap-2 border-b border-border px-4 py-2">
          <DialogPrimitive.Title className="text-sm font-medium text-destructive">
            {errorCount} compile error{errorCount === 1 ? "" : "s"}
          </DialogPrimitive.Title>
          <div className="flex items-center gap-1">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handleCopyAll}
              aria-label="Copy all compile errors"
            >
              {copied ? <Check /> : <Copy />}
              {copied ? "Copied" : "Copy all errors"}
            </Button>
            <DialogPrimitive.Close asChild>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label="Close compile errors"
              >
                <X />
              </Button>
            </DialogPrimitive.Close>
          </div>
        </div>
        <div className="min-h-0 flex-1 space-y-2 overflow-auto px-4 py-3">
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
      </DialogPrimitive.Content>
    </DialogPrimitive.Root>
  )
}
