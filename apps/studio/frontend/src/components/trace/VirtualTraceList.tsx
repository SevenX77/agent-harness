import { useEffect, useMemo, useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'
import type { CallbackEvent } from '../../api/types'
import type { IndexedTraceEvent } from '../../hooks/useTraceFilter'
import { traceEventId } from '../../hooks/useTraceSelection'
import { useVirtualScroll } from '../../hooks/useVirtualScroll'
import { eventPhase, isPredictTrace } from '../../utils/trace'
import { TRACE_EVENT_ROW_HEIGHT, TraceEventRow } from './TraceEventRow'

interface VirtualTraceListProps {
  events: IndexedTraceEvent[]
  activePhase: string | null
  selectedEventId: string | null
  linkEnabled: boolean
  onSelectPrompt: (index: number) => void
  onSelectEvent?: (index: number, event: CallbackEvent) => void
}

export function VirtualTraceList({
  events,
  activePhase,
  selectedEventId,
  linkEnabled,
  onSelectPrompt,
  onSelectEvent,
}: VirtualTraceListProps) {
  const viewportRef = useRef<HTMLDivElement | null>(null)
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set())
  const virtual = useVirtualScroll(viewportRef, {
    itemCount: events.length,
    itemHeight: TRACE_EVENT_ROW_HEIGHT,
    overscan: 8,
  })
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
    if (selectedPosition < 0) {
      return
    }
    const viewport = viewportRef.current
    if (!viewport) {
      return
    }

    const top = selectedPosition * TRACE_EVENT_ROW_HEIGHT
    const bottom = top + TRACE_EVENT_ROW_HEIGHT
    if (top < viewport.scrollTop || bottom > viewport.scrollTop + viewport.clientHeight) {
      viewport.scrollTo({ top: Math.max(0, top - TRACE_EVENT_ROW_HEIGHT), behavior: 'smooth' })
    }
  }, [selectedPosition])

  const focusEventAt = (position: number) => {
    const target = events[position]
    if (!target) {
      return
    }
    viewportRef.current?.scrollTo({
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
    <div
      ref={viewportRef}
      role="listbox"
      aria-label="Trace events"
      aria-activedescendant={selectedEventId ? `trace-event-${selectedEventId}` : undefined}
      tabIndex={0}
      onKeyDown={handleKeyDown}
      data-predict-trace={predictTrace ? 'true' : undefined}
      data-virtualized-count={events.length}
      className={`min-h-0 flex-1 overflow-y-auto pr-1 outline-none focus:ring-2 focus:ring-sky-300 dark:focus:ring-sky-800 ${
        predictTrace ? 'border-l border-amber-200 pl-2 dark:border-amber-900/50' : ''
      }`}
    >
      <div className="relative ml-3 border-l-2 border-gray-200 dark:border-slate-800" style={{ height: virtual.totalHeight }}>
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
    </div>
  )
}
