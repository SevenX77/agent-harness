import { useEffect, useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'
import type { CallbackEvent } from '../../api/types'
import type { IndexedTraceEvent } from '../../hooks/useTraceFilter'
import { RUN_SCOPE, isPredictTrace } from '../../utils/trace'
import {
  MessageScroller,
  MessageScrollerButton,
  MessageScrollerContent,
  MessageScrollerProvider,
  MessageScrollerViewport,
} from '../ui/message-scroller'
import { buildTraceSteps, type TraceStepStatus } from '../../utils/trace-steps'
import { initialTracePosition } from './trace-initial-scroll'
import { TraceStepRow } from './TraceStepRow'

interface TraceEventListProps {
  events: IndexedTraceEvent[]
  selectedEventId: string | null
  /**
   * True while the list renders a LIVE stream: the message-scroller sticks to
   * the bottom as events append (release-on-scroll + back-to-bottom button come
   * from the primitive, per FRONTEND_UI_SPEC §2.6 — no hand-rolled follow).
   */
  followStream?: boolean
  /**
   * Identity of the run being read. Changing it re-parks the list at this
   * mode's initial position (see `initialTracePosition`) — switching runs must
   * not inherit the previous run's scroll offset.
   */
  streamKey?: string | null
  /**
   * The node the reader is focused on. It SCROLLS this list to that node's
   * group and marks the group header; it never removes an event (decision
   * 2026-08-09 D2).
   */
  focusPhase?: string | null
  onSelectEvent?: (index: number, event: CallbackEvent) => void
}

/**
 * The trace as a plain scrolling list.
 *
 * Rows take the height of what they contain and their spacing is declared once,
 * on the list. The previous windowed version sized rows to a fixed 128px slot
 * AND spaced them a further 20px apart, which both padded every short row with
 * dead space and made the scroll container shorter than its own contents, so a
 * run's last events were unreachable (decision 2026-08-08 D3).
 */
export function TraceEventList({
  events,
  selectedEventId,
  followStream = false,
  streamKey = null,
  focusPhase = null,
  onSelectEvent,
}: TraceEventListProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const [viewport, setViewport] = useState<HTMLElement | null>(null)
  // Only DELIBERATE toggles are stored. Everything else follows the step's own
  // status, so a running step opens itself and folds when it finishes without
  // ever overruling a reader who said otherwise (decision 2026-08-09 D4).
  const [overriddenExpansion, setOverriddenExpansion] = useState<Map<string, boolean>>(new Map())

  useEffect(() => {
    const found = containerRef.current?.querySelector<HTMLElement>('[data-slot="message-scroller-viewport"]') ?? null
    setViewport(found)
  }, [])

  // Park the list where this mode should start reading. The scroll primitive's
  // own default is the bottom (it is built for chat), which would open a
  // finished run at its LAST event; a replay starts at the first one.
  useEffect(() => {
    if (!viewport || initialTracePosition({ followStream }) !== 'start') {
      return
    }
    viewport.scrollTop = 0
  }, [viewport, followStream, streamKey])

  // Canvas focus locates instead of filtering, so the list has to take the
  // reader there itself — otherwise focusing a node deep in a long run changes
  // nothing the reader can see.
  useEffect(() => {
    if (!focusPhase || !containerRef.current) {
      return
    }
    const header = containerRef.current.querySelector<HTMLElement>(
      `[data-trace-group-header="${CSS.escape(focusPhase)}"]`,
    )
    header?.scrollIntoView({ block: 'start', behavior: 'smooth' })
  }, [focusPhase, events.length])

  const predictTrace = isPredictTrace(events.map(({ event }) => event))
  const steps = buildTraceSteps(events)
  const selectedPosition = selectedEventId
    ? steps.findIndex((step) => step.key === selectedEventId)
    : -1

  const isExpanded = (key: string, status: TraceStepStatus): boolean =>
    overriddenExpansion.get(key) ?? status === 'running'

  const rowElement = (position: number): HTMLElement | null => {
    const target = steps[position]
    if (!target || !containerRef.current) {
      return null
    }
    return containerRef.current.querySelector<HTMLElement>(`#trace-event-${CSS.escape(target.key)}`)
  }

  useEffect(() => {
    if (selectedPosition < 0) {
      return
    }
    rowElement(selectedPosition)?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
    // Row lookup depends on the rendered list; re-running on selection is enough.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedPosition])

  const focusEventAt = (position: number) => {
    const target = steps[position]
    if (!target) {
      return
    }
    rowElement(position)?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
    onSelectEvent?.(target.start.index, target.start.event)
  }

  const toggleExpanded = (key: string, status: TraceStepStatus) => {
    setOverriddenExpansion((current) => {
      const next = new Map(current)
      next.set(key, !isExpanded(key, status))
      return next
    })
  }

  const toggleExpandedAt = (position: number) => {
    const target = steps[position]
    if (!target) {
      return
    }
    toggleExpanded(target.key, target.status)
    onSelectEvent?.(target.start.index, target.start.event)
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (steps.length === 0) {
      return
    }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      const direction = event.key === 'ArrowDown' ? 1 : -1
      const fallback = direction > 0 ? 0 : steps.length - 1
      const nextPosition = selectedPosition < 0
        ? fallback
        : Math.min(steps.length - 1, Math.max(0, selectedPosition + direction))
      focusEventAt(nextPosition)
    }
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      toggleExpandedAt(selectedPosition >= 0 ? selectedPosition : 0)
    }
  }

  return (
    <div ref={containerRef} className="h-full min-h-0">
      <MessageScrollerProvider autoScroll={followStream}>
        <MessageScroller className="h-full">
          <MessageScrollerViewport
            role="listbox"
            aria-label="Trace events"
            aria-activedescendant={selectedEventId ? `trace-event-${selectedEventId}` : undefined}
            tabIndex={0}
            onKeyDown={handleKeyDown}
            data-predict-trace={predictTrace ? 'true' : undefined}
            data-trace-step-count={steps.length}
            className={`pr-1 outline-none focus:ring-2 focus:ring-ring/50 ${
              predictTrace ? 'border-l border-warning-border/50 pl-2' : ''
            }`}
          >
            <MessageScrollerContent className="block h-max min-h-0 gap-0">
              <div className="ml-3 space-y-0.5 border-l border-border py-1">
                {steps.map((step, position) => {
                  const phase = step.phase
                  // A node's name belongs to the RUN of steps it owns, not to
                  // each row: eight consecutive `segment` events used to print
                  // `SEGMENT` eight times (decision 2026-08-08 D3).
                  const opensGroup = position === 0 || steps[position - 1].phase !== phase
                  return (
                    <div
                      key={step.key}
                      id={`trace-event-${step.key}`}
                      role="option"
                      aria-selected={selectedEventId === step.key}
                    >
                      {opensGroup ? (
                        <div
                          data-trace-group-header={phase}
                          data-trace-focus-group={phase === focusPhase ? 'true' : undefined}
                          className={`mt-2 mb-1 pl-5 font-mono text-[10px] font-semibold uppercase tracking-wider first:mt-0 ${
                            phase === focusPhase ? 'text-foreground' : 'text-muted-foreground/70'
                          }`}
                        >
                          {phase === RUN_SCOPE ? 'Run' : phase}
                        </div>
                      ) : null}
                      <TraceStepRow
                        step={step}
                        eventId={step.key}
                        selected={selectedEventId === step.key}
                        expanded={isExpanded(step.key, step.status)}
                        onToggleExpanded={() => toggleExpanded(step.key, step.status)}
                        onSelectEvent={onSelectEvent}
                      />
                    </div>
                  )
                })}
              </div>
            </MessageScrollerContent>
          </MessageScrollerViewport>
          <MessageScrollerButton />
        </MessageScroller>
      </MessageScrollerProvider>
    </div>
  )
}
