import type { ComponentProps } from 'react'
import { useCallback, useEffect, useMemo, useRef } from 'react'
import Editor from '@monaco-editor/react'
import { FileText } from 'lucide-react'
import type { CallbackEvent } from '../api/types'
import { buildTraceDocument } from '../utils/trace-document'

export type EditorOnMount = NonNullable<ComponentProps<typeof Editor>['onMount']>
export type MonacoEditor = Parameters<EditorOnMount>[0]
export type MonacoApi = Parameters<EditorOnMount>[1]

// NOTE: there is deliberately NO realtime-lint banner/strip component here.
// The realtime lint surface is inline Monaco markers scoped to the OPEN file
// (`applyLintMarkers(filePath)` in LazyMonacoPanel), plus the canvas node badge
// and Properties field tooltip; the full aggregated list lives in the manual
// Compile drawer (CompileErrorDrawer). A large in-editor banner was removed in
// PR #234 ("real-time lint marks context only, not a global panel mid-edit",
// compile-lint F1) and must not be reintroduced — see the LazyMonacoPanel test
// that locks its absence.

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
