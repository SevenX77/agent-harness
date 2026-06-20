import type { ComponentProps } from 'react'
import { useCallback, useEffect, useMemo, useRef } from 'react'
import Editor from '@monaco-editor/react'
import { AlertCircle, AlertTriangle, Copy, FileText } from 'lucide-react'
import type { CallbackEvent, LintResult } from '../api/types'
import { deriveLintDiagnostics, formatLintDiagnostic } from '../hooks/useDebouncedLint'
import { buildTraceDocument } from '../utils/trace-document'

export type EditorOnMount = NonNullable<ComponentProps<typeof Editor>['onMount']>
export type MonacoEditor = Parameters<EditorOnMount>[0]
export type MonacoApi = Parameters<EditorOnMount>[1]

interface LintDiagnosticsPanelProps {
  /** Backend lint payload (single source of truth). Renders only what the engine returned. */
  lintResult: LintResult | null
  onJumpToLine: (line: number | null) => void
  onCopyErrors: (message: string) => void
}

/**
 * Realtime-lint diagnostics strip (workflow 03_compile F1 skeleton).
 *
 * Pure projection of the engine lint payload via `deriveLintDiagnostics` — no second
 * source of truth, no Studio-invented rules. Realtime lint "marks context only", so
 * this is a quiet inline strip above the editor, not a global toast/floating card.
 * Each row jumps to its source line; copy emits the shared `file:line - code - message`
 * digest for pasting to Copilot. Field-level Monaco markers (near-projection) are Wave 2
 * and intentionally absent — this skeleton only surfaces the flat diagnostics list.
 */
export function LintDiagnosticsPanel({
  lintResult,
  onJumpToLine,
  onCopyErrors,
}: LintDiagnosticsPanelProps) {
  const diagnostics = deriveLintDiagnostics(lintResult)
  if (diagnostics.length === 0) {
    return null
  }

  const hasFatal = diagnostics.some((diagnostic) => diagnostic.severity === 'error')

  return (
    <div
      className={
        hasFatal
          ? 'shrink-0 border-b border-destructive-border bg-destructive-background p-3 text-sm text-destructive-label'
          : 'shrink-0 border-b border-warning-border bg-warning-background p-3 text-sm text-warning-foreground'
      }
      role="status"
      aria-label="Lint diagnostics"
    >
      <div className="mb-2 flex items-start gap-2 font-semibold">
        {hasFatal ? (
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
        ) : (
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
        )}
        {hasFatal ? 'Lint found errors' : 'Lint found warnings'}
      </div>
      <div className="max-h-36 space-y-2 overflow-y-auto">
        {diagnostics.map((diagnostic, index) => (
          <button
            key={`${diagnostic.error_code}-${diagnostic.line ?? 'none'}-${index}`}
            type="button"
            onClick={() => onJumpToLine(diagnostic.line)}
            className="block w-full rounded border border-border bg-card px-2 py-1 text-start hover:bg-muted"
          >
            <span className="font-mono text-xs text-muted-foreground">
              {diagnostic.line ? `Line ${diagnostic.line}` : 'No line'} / {diagnostic.error_code}
            </span>
            <span className="ms-2 text-foreground">{diagnostic.message}</span>
          </button>
        ))}
      </div>
      <button
        type="button"
        aria-label="Copy lint diagnostics"
        onClick={() => onCopyErrors(diagnostics.map(formatLintDiagnostic).join('\n'))}
        className="mt-2 flex items-center gap-1 rounded border border-border bg-card px-2 py-1 text-xs text-muted-foreground hover:bg-muted"
      >
        <Copy className="h-3 w-3" />
        Copy
      </button>
    </div>
  )
}

interface MonacoPanelProps {
  isDarkMode: boolean
  skillCode: string
  lintResult: LintResult | null
  onEditorMount: EditorOnMount
  onDraftChange: (code: string) => void
  onJumpToLine: (line: number | null) => void
  onCopyErrors: (message: string) => void
}

export function MonacoPanel({
  isDarkMode,
  skillCode,
  lintResult,
  onEditorMount,
  onDraftChange,
  onJumpToLine,
  onCopyErrors,
}: MonacoPanelProps) {
  return (
    <div className="flex h-full flex-col">
      <LintDiagnosticsPanel
        lintResult={lintResult}
        onJumpToLine={onJumpToLine}
        onCopyErrors={onCopyErrors}
      />

      <div className="flex-1">
        <Editor
          height="100%"
          defaultLanguage="markdown"
          theme={isDarkMode ? 'vs-dark' : 'light'}
          value={skillCode}
          onMount={onEditorMount}
          onChange={(value) => onDraftChange(value ?? '')}
          options={{
            minimap: { enabled: false },
            fontSize: 13,
            wordWrap: 'on',
            scrollBeyondLastLine: false,
          }}
        />
      </div>
    </div>
  )
}

interface TraceDocumentPanelProps {
  /** Ordered run events (live or replayed) projected into the read-only document. */
  events: CallbackEvent[]
  isDarkMode: boolean
  /**
   * The node/phase the user has focused on the canvas (atom #17). When set, the
   * read-only editor reveals that node's block so "看完整 trace" and node focus
   * stay in lockstep. Matches `eventPhase` keying (phase_name → id).
   */
  focusNodeId?: string | null
}

/**
 * Read-only full-trace document (n4-trace #18, spec 04 D4/D7).
 *
 * Renders the whole run as a lightly-formatted, human-readable document in a
 * read-only Monaco editor — NOT raw jsonl. Reuses the same editor as the skill
 * authoring surface (read-only mode), so users read the trace like a document,
 * with each state's full blackboard detail nested beneath it. When a node is
 * focused on the canvas the editor jumps to that node's line range.
 */
export function TraceDocumentPanel({ events, isDarkMode, focusNodeId = null }: TraceDocumentPanelProps) {
  const document = useMemo(() => buildTraceDocument(events), [events])
  const editorRef = useRef<MonacoEditor | null>(null)

  const revealFocusedNode = useCallback(() => {
    const editor = editorRef.current
    if (!editor || !focusNodeId) {
      return
    }
    const range = document.nodeRanges.find((entry) => entry.nodeId === focusNodeId)
    if (!range) {
      return
    }
    editor.revealLineInCenter(range.startLine)
    editor.setPosition({ lineNumber: range.startLine, column: 1 })
  }, [document, focusNodeId])

  const handleMount = useCallback<EditorOnMount>((editor) => {
    editorRef.current = editor
    revealFocusedNode()
  }, [revealFocusedNode])

  // Re-reveal whenever the focused node (or the document) changes after mount.
  useEffect(() => {
    revealFocusedNode()
  }, [revealFocusedNode])

  return (
    <section className="flex h-full min-h-0 flex-col bg-card" aria-label="Full trace document">
      <div className="flex h-10 shrink-0 items-center gap-2 border-b border-border px-3">
        <FileText className="size-3.5 text-muted-foreground" />
        <h2 className="text-sm font-semibold text-foreground">Full Trace</h2>
        <span className="text-xs text-muted-foreground">{events.length} events</span>
      </div>
      <div className="min-h-0 flex-1">
        <Editor
          height="100%"
          defaultLanguage="markdown"
          theme={isDarkMode ? 'vs-dark' : 'light'}
          value={document.text}
          onMount={handleMount}
          options={{
            readOnly: true,
            minimap: { enabled: false },
            fontSize: 13,
            wordWrap: 'on',
            scrollBeyondLastLine: false,
            automaticLayout: true,
          }}
        />
      </div>
    </section>
  )
}
