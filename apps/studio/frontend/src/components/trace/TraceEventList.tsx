import { useEffect, useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'
import type { CallbackEvent } from '../../api/types'
import type { IndexedTraceEvent } from '../../hooks/useTraceFilter'
import { traceEventId } from '../../hooks/useTraceSelection'
import { eventPhase, isPredictTrace } from '../../utils/trace'
import {
  MessageScroller,
  MessageScrollerButton,
  MessageScrollerContent,
  MessageScrollerProvider,
  MessageScrollerViewport,
} from '../ui/message-scroller'
import { initialTracePosition } from './trace-initial-scroll'
import { TraceEventRow } from './TraceEventRow'

interface TraceEventListProps {
  events: IndexedTraceEvent[]
  activePhase: string | null
  selectedEventId: string | null
  linkEnabled: boolean
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
  onSelectPrompt: (index: number) => void
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
  activePhase,
  selectedEventId,
  linkEnabled,
  followStream = false,
  streamKey = null,
  onSelectPrompt,
  onSelectEvent,
}: TraceEventListProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const [viewport, setViewport] = useState<HTMLElement | null>(null)
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set())

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

  const predictTrace = isPredictTrace(events.map(({ event }) => event))
  const selectedPosition = selectedEventId
    ? events.findIndex(({ event, index }) => traceEventId(event, index) === selectedEventId)
    : -1

  const rowElement = (position: number): HTMLElement | null => {
    const target = events[position]
    if (!target || !containerRef.current) {
      return null
    }
    return containerRef.current.querySelector<HTMLElement>(
      `#trace-event-${CSS.escape(traceEventId(target.event, target.index))}`,
    )
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
    const target = events[position]
    if (!target) {
      return
    }
    rowElement(position)?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
    onSelectEvent?.(target.index, target.event)
  }

  const toggleExpanded = (eventId: string) => {
    setExpandedIds((current) => {
      const next = new Set(current)
      if (next.has(eventId)) {
        next.delete(eventId)
      } else {
        next.add(eventId)
      }
      return next
    })
  }

  const toggleExpandedAt = (position: number) => {
    const target = events[position]
    if (!target) {
      return
    }
    toggleExpanded(traceEventId(target.event, target.index))
    onSelectEvent?.(target.index, target.event)
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (events.length === 0) {
      return
    }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      const direction = event.key === 'ArrowDown' ? 1 : -1
      const fallback = direction > 0 ? 0 : events.length - 1
      const nextPosition = selectedPosition < 0
        ? fallback
        : Math.min(events.length - 1, Math.max(0, selectedPosition + direction))
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
            data-trace-event-count={events.length}
            className={`pr-1 outline-none focus:ring-2 focus:ring-ring/50 ${
              predictTrace ? 'border-l border-warning-border/50 pl-2' : ''
            }`}
          >
            <MessageScrollerContent className="block h-max min-h-0 gap-0">
              <div className="ml-3 space-y-1.5 border-l-2 border-border py-1">
                {events.map(({ event, index }) => {
                  const eventId = traceEventId(event, index)
                  return (
                    <div
                      key={`${event.timestamp}-${index}`}
                      id={`trace-event-${eventId}`}
                      role="option"
                      aria-selected={selectedEventId === eventId}
                    >
                      <TraceEventRow
                        event={event}
                        index={index}
                        eventId={eventId}
                        selected={selectedEventId === eventId}
                        highlighted={Boolean(linkEnabled && activePhase && activePhase === eventPhase(event))}
                        expanded={expandedIds.has(eventId)}
                        onToggleExpanded={() => toggleExpanded(eventId)}
                        onSelectPrompt={onSelectPrompt}
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
