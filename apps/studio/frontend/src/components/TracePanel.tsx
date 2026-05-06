import type { CallbackEvent } from '../api/types'
import { useTraceFilter } from '../hooks/useTraceFilter'
import { TraceFilter } from './trace/TraceFilter'
import { TraceEventRow } from './trace/TraceEventRow'
import { TraceSearchBar } from './trace/TraceSearchBar'

interface TracePanelProps {
  traceLogs: CallbackEvent[]
  activePhase?: string | null
  onSelectPrompt: (index: number) => void
}

export function TracePanel({ traceLogs, activePhase = null, onSelectPrompt }: TracePanelProps) {
  const filter = useTraceFilter(traceLogs, activePhase)

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
        <h3 className="font-bold text-gray-700 dark:text-gray-300">Trace Timeline</h3>
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
            onSelectPrompt={onSelectPrompt}
          />
        ))}
      </div>
    </div>
  )
}
