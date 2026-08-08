import { useEffect, useMemo, useRef, useState } from 'react'
import { AlertOctagon, ChevronDown, ChevronRight, FileText, Hash } from 'lucide-react'
import type { CallbackEvent } from '../../api/types'
import { buildTraceDocument, type TraceDocumentDetail, type TraceDocumentEntry } from '../../utils/trace-document'
import { RUN_SCOPE } from '../../utils/trace'
import { Badge } from '../ui/badge'
import { Button } from '../ui/button'
import { ScrollArea } from '../ui/scroll-area'
import { EventTypeBadge } from './EventTypeBadge'

interface TraceDocumentPanelProps {
  /** Ordered run events (live or replayed) projected into the document. */
  events: CallbackEvent[]
  /**
   * The node/phase the user has focused on the canvas (atom #17). When set, the
   * document scrolls to that node's block so "看完整 trace" and node focus stay
   * in lockstep. Matches `eventPhase` keying (phase_name → id).
   */
  focusNodeId?: string | null
}

/** How much of a long value is shown before the reader asks for the rest. */
const DETAIL_COLLAPSED_MAX_HEIGHT = 'max-h-56'

/**
 * The full-trace document: the whole run, node by node, read top to bottom.
 *
 * This is the reading surface — no filter, no search, nothing windowed away —
 * as opposed to the Trace view, which is the interactive stream you search to
 * find one state. It is rendered as a document in the panel's own visual
 * language; it used to be a read-only Monaco editor, which put line numbers and
 * editor chrome in a panel nobody can edit (decision 2026-08-08 D4).
 */
export function TraceDocumentPanel({ events, focusNodeId = null }: TraceDocumentPanelProps) {
  const document = useMemo(() => buildTraceDocument(events), [events])
  const containerRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!focusNodeId || !containerRef.current) {
      return
    }
    const section = containerRef.current.querySelector<HTMLElement>(
      `[data-trace-doc-node="${CSS.escape(focusNodeId)}"]`,
    )
    section?.scrollIntoView({ block: 'start', behavior: 'smooth' })
  }, [focusNodeId, document])

  return (
    <section className="flex h-full min-h-0 flex-col bg-card" aria-label="Full trace document">
      <div className="flex h-10 shrink-0 items-center gap-2 border-b border-border py-2 pl-3 pr-10">
        <FileText className="size-3.5 text-muted-foreground" />
        <h2 className="text-sm font-semibold text-foreground">Full Trace</h2>
        <span className="text-xs text-muted-foreground">{document.eventCount} events</span>
        <span className="ml-auto truncate text-xs text-muted-foreground/80" title="The whole run, top to bottom">
          Whole run · unfiltered
        </span>
      </div>
      <ScrollArea className="min-h-0 flex-1">
        <div ref={containerRef} className="space-y-4 px-3 py-3">
          {document.sections.length === 0 ? (
            <p className="text-sm text-muted-foreground">No trace events captured yet.</p>
          ) : (
            document.sections.map((section, sectionIndex) => (
              <section key={`${section.nodeId}-${sectionIndex}`} data-trace-doc-node={section.nodeId}>
                <header className="sticky top-0 z-10 -mx-1 mb-2 flex items-center gap-2 bg-card/95 px-1 py-1 backdrop-blur">
                  <h3 className="font-mono text-sm font-semibold text-foreground">
                    {section.nodeId === RUN_SCOPE ? 'Run' : section.nodeId}
                  </h3>
                  <Badge variant="secondary" className="text-[10px]">
                    {section.entries.length} states
                  </Badge>
                </header>
                <ol className="space-y-2">
                  {section.entries.map((entry) => (
                    <li key={`${entry.position}-${entry.eventType}`}>
                      <TraceDocumentState entry={entry} />
                    </li>
                  ))}
                </ol>
              </section>
            ))
          )}
        </div>
      </ScrollArea>
    </section>
  )
}

function TraceDocumentState({ entry }: { entry: TraceDocumentEntry }) {
  return (
    <article className="rounded-md border border-border bg-background px-2.5 py-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-[10px] text-muted-foreground/70">{entry.position}</span>
        <EventTypeBadge eventType={entry.eventType} />
        {entry.timeLabel ? (
          <span className="font-mono text-[10px] text-muted-foreground/80">{entry.timeLabel}</span>
        ) : null}
        {entry.tokens ? (
          <span className="flex items-center gap-1 rounded-full bg-primary/15 px-2 py-0.5 text-xs font-medium text-primary">
            <Hash className="size-3" />
            {entry.tokens}
          </span>
        ) : null}
      </div>
      <p className="mt-1 text-sm leading-snug text-foreground">{entry.headline}</p>
      {entry.errorMessage ? (
        <p className="mt-2 flex items-start gap-1.5 rounded border border-destructive-border/60 bg-destructive/10 px-2 py-1 text-xs text-destructive">
          <AlertOctagon className="mt-0.5 size-3.5 shrink-0" />
          {entry.errorMessage}
        </p>
      ) : null}
      {entry.details.map((item) => (
        <TraceDocumentDetailBlock key={item.label} detail={item} />
      ))}
    </article>
  )
}

function TraceDocumentDetailBlock({ detail }: { detail: TraceDocumentDetail }) {
  const [expanded, setExpanded] = useState(false)
  const lineCount = detail.content.split('\n').length
  // Short values are already fully visible; only long ones need the control.
  const needsControl = lineCount > 12 || detail.content.length > 800

  return (
    <div className="mt-2">
      <div className="flex items-center gap-2">
        <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
          {detail.label}
        </span>
        {needsControl ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-5 px-1.5 text-[10px]"
            onClick={() => setExpanded((open) => !open)}
          >
            {expanded ? <ChevronDown className="size-3" /> : <ChevronRight className="size-3" />}
            {expanded ? 'Collapse' : `Expand (${lineCount} lines)`}
          </Button>
        ) : null}
      </div>
      <pre
        className={`mt-1 overflow-auto whitespace-pre-wrap break-words rounded border border-border bg-muted/30 p-2 font-mono text-[11px] leading-relaxed text-foreground ${
          expanded ? '' : DETAIL_COLLAPSED_MAX_HEIGHT
        }`}
      >
        {detail.content}
      </pre>
    </div>
  )
}
