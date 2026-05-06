import type { CallbackEvent } from '../api/types'
import { useTraceFilter } from '../hooks/useTraceFilter'
import { traceEventId } from '../hooks/useTraceSelection'
import { eventPhase } from '../utils/trace'
import { TraceFilter } from './trace/TraceFilter'
import { TraceEventRow } from './trace/TraceEventRow'
import { TraceSearchBar } from './trace/TraceSearchBar'

interface TracePanelProps {
  traceLogs: CallbackEvent[]
  activePhase?: string | null
  selectedEventId?: string | null
  linkEnabled?: boolean
  onToggleLink?: (enabled: boolean) => void
  onSelectPrompt: (index: number) => void
  onSelectEvent?: (index: number, event: CallbackEvent) => void
}

export function TracePanel({
  traceLogs,
  activePhase = null,
  selectedEventId = null,
  linkEnabled = true,
  onToggleLink,
  onSelectPrompt,
  onSelectEvent,
}: TracePanelProps) {
  const filter = useTraceFilter(traceLogs, linkEnabled ? activePhase : null)

  if (traceLogs.length === 0) {
    return (
      <div className="flex h-full items-center justify-center text-sm font-medium text-slate-400 dark:text-slate-500">
        Waiting for run events
      </div>
    )
  }

  return (
    <div>
      <div className="mb-4 space-y-3 border-b border-gray-200 pb-4 dark:border-slate-800">
        <div className="flex items-center justify-between gap-3">
          <h3 className="font-bold text-gray-700 dark:text-gray-300">Trace Timeline</h3>
          <label className="flex items-center gap-2 text-xs font-medium text-gray-500 dark:text-gray-400">
            <input
              type="checkbox"
              checked={linkEnabled}
              onChange={(event) => onToggleLink?.(event.target.checked)}
              className="h-3.5 w-3.5 rounded border-gray-300 text-sky-600 focus:ring-sky-500"
            />
            Link views
          </label>
        </div>
        <TraceSearchBar value={filter.searchTerm} onChange={filter.setSearchTerm} />
        <TraceFilter
          eventTypes={filter.eventTypes}
          phases={filter.phases}
          selectedTypes={filter.selectedTypes}
          selectedPhases={filter.selectedPhases}
          activePhase={activePhase}
          onToggleType={filter.toggleType}
          onTogglePhase={filter.togglePhase}
          onClear={filter.clearFilters}
        />
        <div className="text-xs font-medium text-gray-400 dark:text-gray-500">
          Showing {filter.filteredEvents.length} of {traceLogs.length} events
        </div>
      </div>
      <div className="relative ml-3 space-y-5 border-l-2 border-gray-200 dark:border-slate-800">
        {filter.filteredEvents.map(({ event, index }) => (
          <TraceEventRow
            key={`${event.timestamp}-${index}`}
            event={event}
            index={index}
            selected={selectedEventId === traceEventId(event, index)}
            highlighted={Boolean(linkEnabled && activePhase && activePhase === eventPhase(event))}
            onSelectPrompt={onSelectPrompt}
            onSelectEvent={onSelectEvent}
          />
        ))}
      </div>
    </div>
  )
}
