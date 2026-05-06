import { useRef } from 'react'
import type { CallbackEvent } from '../../api/types'
import type { IndexedTraceEvent } from '../../hooks/useTraceFilter'
import { traceEventId } from '../../hooks/useTraceSelection'
import { useVirtualScroll } from '../../hooks/useVirtualScroll'
import { eventPhase } from '../../utils/trace'
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
  const virtual = useVirtualScroll(viewportRef, {
    itemCount: events.length,
    itemHeight: TRACE_EVENT_ROW_HEIGHT,
    overscan: 8,
  })
  const visibleEvents = events.slice(virtual.startIdx, virtual.endIdx)

  return (
    <div ref={viewportRef} className="min-h-0 flex-1 overflow-y-auto pr-1">
      <div className="relative ml-3 border-l-2 border-gray-200 dark:border-slate-800" style={{ height: virtual.totalHeight }}>
        <div
          className="absolute left-0 right-0 top-0 space-y-5"
          style={{ transform: `translateY(${virtual.offsetTop}px)` }}
        >
          {visibleEvents.map(({ event, index }) => (
            <div key={`${event.timestamp}-${index}`} style={{ minHeight: TRACE_EVENT_ROW_HEIGHT }}>
              <TraceEventRow
                event={event}
                index={index}
                selected={selectedEventId === traceEventId(event, index)}
                highlighted={Boolean(linkEnabled && activePhase && activePhase === eventPhase(event))}
                onSelectPrompt={onSelectPrompt}
                onSelectEvent={onSelectEvent}
              />
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
