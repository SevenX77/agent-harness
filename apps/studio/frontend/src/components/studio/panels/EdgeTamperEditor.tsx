import { useMemo } from "react"
import Editor from "@monaco-editor/react"
import { Button } from "@/components/ui/button"
import { validateTamperJson } from "./edge-tamper"

/**
 * Writable Monaco editor for edge-dot context tampering (debug workflow F6 / Q3).
 *
 * Q3 decision: the tamper surface IS the read-only trace editor switched writable —
 * not a second editor. So this component mounts the SAME `@monaco-editor/react`
 * Monaco the skill/trace editors use, and flips `readOnly` on `writable`. Language is
 * `json` so the user gets JSON syntax affordances while editing the blackboard the
 * downstream node will resume from. A live validity strip projects the SHARED
 * `validateTamperJson` rule (same accept/reject as the resume request) on every
 * keystroke; resume stays blocked while the draft is invalid. This is the canvas-side
 * editor only — it does not own the resume request itself (that is wired in the panel).
 */

// Imports the Monaco editor directly (like MonacoPanel) — vite's manualChunks already
// splits @monaco-editor into its own bundle, so no eager-load cost for the app shell.

// SSR-safe theme probe: `document` is absent under server rendering, so fall back to
// the light theme rather than throwing. Matches the dark-class convention the other
// editors use.
function monacoTheme(): "vs-dark" | "light" {
  if (typeof document === "undefined") {
    return "light"
  }
  return document.documentElement.classList.contains("dark") ? "vs-dark" : "light"
}

interface EdgeTamperEditorProps {
  value: string
  writable: boolean
  onChange: (next: string) => void
  onStartTamper: () => void
  onCancel: () => void
  onResume: () => void
  /** Checkpoint the downstream resume is anchored at (shown for auditability). */
  checkpointId?: string | null
  /** Engine-reported reason downstream resume is blocked (dirty upstream checkpoint). */
  disabledReason?: string | null
  resumeLoading?: boolean
  resumeDisabled?: boolean
}

export function EdgeTamperEditor({
  value,
  writable,
  onChange,
  onStartTamper,
  onCancel,
  onResume,
  checkpointId = null,
  disabledReason = null,
  resumeLoading = false,
  resumeDisabled = false,
}: EdgeTamperEditorProps) {
  // Only a writable draft can be invalid; the read-only trace frame is trusted.
  const validation = useMemo(
    () => (writable ? validateTamperJson(value) : { ok: true as const }),
    [value, writable],
  )
  const validationError = validation.ok ? null : validation.error
  const resumeBlocked = Boolean(disabledReason) || resumeDisabled || resumeLoading || (writable && !validation.ok)

  let resumeLabel = "Resume downstream"
  if (disabledReason) {
    resumeLabel = "Resume disabled"
  } else if (resumeLoading) {
    resumeLabel = "Resuming"
  }

  return (
    <div className="space-y-3 rounded-md border border-border bg-card p-3">
      <div className="flex items-center justify-between gap-3">
        <div className="space-y-1">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Tamper downstream resume context
          </div>
          <div className="text-xs text-muted-foreground">
            Edit resume input only; the historical trace above stays read-only.
          </div>
          {checkpointId ? (
            <div className="font-mono text-[10px] text-muted-foreground">{checkpointId}</div>
          ) : null}
        </div>
        <div className="flex items-center gap-2">
          <Button type="button" variant="outline" size="xs" onClick={onStartTamper}>
            Tamper
          </Button>
          {writable ? (
            <Button type="button" variant="ghost" size="xs" onClick={onCancel}>
              Cancel
            </Button>
          ) : null}
        </div>
      </div>

      {disabledReason ? (
        <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
          <span className="inline-flex items-center rounded-md border border-destructive-border bg-destructive-background px-2 py-0.5 text-destructive-label">
            {disabledReason}
          </span>
          <span>Checkpoint validity blocks downstream resume.</span>
        </div>
      ) : null}

      <div
        className="overflow-hidden rounded-md border border-border"
        aria-label="Tampered edge context JSON"
        data-writable={writable ? "true" : "false"}
      >
        <Editor
          height="12rem"
          defaultLanguage="json"
          theme={monacoTheme()}
          value={value}
          loading={
            <div className="grid h-32 w-full place-items-center bg-muted/30 text-xs text-muted-foreground">
              Loading editor...
            </div>
          }
          options={{
            minimap: { enabled: false },
            fontSize: 12,
            wordWrap: "on",
            scrollBeyondLastLine: false,
            automaticLayout: true,
            lineNumbers: "off",
            folding: false,
            readOnly: !writable,
          }}
          onChange={(next) => onChange(next ?? "")}
        />
      </div>

      {validationError ? (
        <div
          role="alert"
          className="rounded-md border border-destructive-border bg-destructive-background px-2 py-1 text-xs text-destructive-label"
        >
          {validationError}
        </div>
      ) : null}

      <div className="flex justify-end">
        <Button type="button" size="sm" disabled={resumeBlocked || !writable} onClick={onResume}>
          {resumeLabel}
        </Button>
      </div>
    </div>
  )
}
