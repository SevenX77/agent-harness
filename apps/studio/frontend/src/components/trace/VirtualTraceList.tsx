import { useEffect, useMemo, useRef, useState } from 'react'
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
import { TRACE_EVENT_ROW_HEIGHT, TraceEventRow } from './TraceEventRow'

interface VirtualTraceListProps {
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

export function VirtualTraceList({
  events,
  activePhase,
  selectedEventId,
  linkEnabled,
  followStream = false,
  streamKey = null,
  onSelectPrompt,
  onSelectEvent,
}: VirtualTraceListProps) {
  // The scroll container is the message-scroller primitive's viewport; the
  // virtualization window reads its scroll box through this lookup (the
  // primitive owns follow-bottom, we own which rows exist).
  const containerRef = useRef<HTMLDivElement | null>(null)
  const [viewport, setViewport] = useState<HTMLElement | null>(null)
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set())
  const [viewportHeight, setViewportHeight] = useState(0)
  const [scrollTop, setScrollTop] = useState(0)

  useEffect(() => {
    const found = containerRef.current?.querySelector<HTMLElement>('[data-slot="message-scroller-viewport"]') ?? null
    setViewport(found)
  }, [])

  useEffect(() => {
    if (!viewport) {
      return undefined
    }
    const updateViewport = () => {
      setViewportHeight(viewport.clientHeight)
      setScrollTop(viewport.scrollTop)
    }
    updateViewport()
    viewport.addEventListener('scroll', updateViewport, { passive: true })
    window.addEventListener('resize', updateViewport)
    return () => {
      viewport.removeEventListener('scroll', updateViewport)
      window.removeEventListener('resize', updateViewport)
    }
  }, [viewport])

  // Park the list where this mode should start reading. The scroll primitive's
  // own default is the bottom (it is built for chat), which would open a
  // finished run at its LAST event; a replay starts at the first one.
  useEffect(() => {
    if (!viewport || initialTracePosition({ followStream }) !== 'start') {
      return
    }
    viewport.scrollTop = 0
    setScrollTop(0)
  }, [viewport, followStream, streamKey])

  const virtual = useMemo(() => {
    const visibleCount = Math.ceil(viewportHeight / TRACE_EVENT_ROW_HEIGHT)
    const firstVisible = Math.floor(scrollTop / TRACE_EVENT_ROW_HEIGHT)
    const startIdx = Math.max(0, firstVisible - 8)
    const endIdx = Math.min(events.length, firstVisible + visibleCount + 9)
    return {
      startIdx,
      endIdx,
      totalHeight: events.length * TRACE_EVENT_ROW_HEIGHT,
      offsetTop: startIdx * TRACE_EVENT_ROW_HEIGHT,
    }
  }, [events.length, scrollTop, viewportHeight])
  const visibleEvents = events.slice(virtual.startIdx, virtual.endIdx)
  const predictTrace = useMemo(
    () => isPredictTrace(events.map(({ event }) => event)),
    [events],
  )
  const selectedPosition = useMemo(
    () => selectedEventId ? events.findIndex(({ event, index }) => traceEventId(event, index) === selectedEventId) : -1,
    [events, selectedEventId],
  )

  useEffect(() => {
    if (selectedPosition < 0 || !viewport) {
      return
    }

    const top = selectedPosition * TRACE_EVENT_ROW_HEIGHT
    const bottom = top + TRACE_EVENT_ROW_HEIGHT
    if (top < viewport.scrollTop || bottom > viewport.scrollTop + viewport.clientHeight) {
      viewport.scrollTo({ top: Math.max(0, top - TRACE_EVENT_ROW_HEIGHT), behavior: 'smooth' })
    }
  }, [selectedPosition, viewport])

  const focusEventAt = (position: number) => {
    const target = events[position]
    if (!target) {
      return
    }
    viewport?.scrollTo({
      top: Math.max(0, position * TRACE_EVENT_ROW_HEIGHT),
      behavior: 'smooth',
    })
    onSelectEvent?.(target.index, target.event)
  }

  const toggleExpandedAt = (position: number) => {
    const target = events[position]
    if (!target) {
      return
    }
    const eventId = traceEventId(target.event, target.index)
    setExpandedIds((current) => {
      const next = new Set(current)
      if (next.has(eventId)) {
        next.delete(eventId)
      } else {
        next.add(eventId)
      }
      return next
    })
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
            data-virtualized-count={events.length}
            className={`pr-1 outline-none focus:ring-2 focus:ring-ring/50 ${
              predictTrace ? 'border-l border-warning-border/50 pl-2' : ''
            }`}
          >
            <MessageScrollerContent className="block h-max min-h-0 gap-0">
              <div className="relative ml-3 border-l-2 border-border" style={{ height: virtual.totalHeight }}>
                <div
                  className="absolute left-0 right-0 top-0 space-y-5"
                  style={{ transform: `translateY(${virtual.offsetTop}px)` }}
                >
                  {visibleEvents.map(({ event, index }) => {
                    const eventId = traceEventId(event, index)
                    const absolutePosition = events.findIndex((item) => item.index === index)
                    return (
                    <div
                      key={`${event.timestamp}-${index}`}
                      id={`trace-event-${eventId}`}
                      role="option"
                      aria-selected={selectedEventId === eventId}
                      data-virtual-index={absolutePosition}
                      style={{ minHeight: TRACE_EVENT_ROW_HEIGHT }}
                    >
                      <TraceEventRow
                        event={event}
                        index={index}
                        eventId={eventId}
                        selected={selectedEventId === eventId}
                        highlighted={Boolean(linkEnabled && activePhase && activePhase === eventPhase(event))}
                        expanded={expandedIds.has(eventId)}
                        onToggleExpanded={() => setExpandedIds((current) => {
                          const next = new Set(current)
                          if (next.has(eventId)) {
                            next.delete(eventId)
                          } else {
                            next.add(eventId)
                          }
                          return next
                        })}
                        onSelectPrompt={onSelectPrompt}
                        onSelectEvent={onSelectEvent}
                      />
                    </div>
                    )
                  })}
                </div>
              </div>
            </MessageScrollerContent>
          </MessageScrollerViewport>
          <MessageScrollerButton />
        </MessageScroller>
      </MessageScrollerProvider>
    </div>
  )
}
