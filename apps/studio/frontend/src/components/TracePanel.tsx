import type { CallbackEvent } from '../api/types'
import { useTraceFilter } from '../hooks/useTraceFilter'
import { BadgeCheck, GitCompareArrows } from 'lucide-react'
import { TraceFilter } from './trace/TraceFilter'
import { TraceSearchBar } from './trace/TraceSearchBar'
import { VirtualTraceList } from './trace/VirtualTraceList'

interface TracePanelProps {
  traceLogs: CallbackEvent[]
  activePhase?: string | null
  selectedEventId?: string | null
  linkEnabled?: boolean
  onToggleLink?: (enabled: boolean) => void
  onSelectPrompt: (index: number) => void
  onSelectEvent?: (index: number, event: CallbackEvent) => void
  canCompare?: boolean
  compareLoading?: boolean
  onCompareToGolden?: () => void
  onPromoteToGolden?: () => void
}

export function TracePanel({
  traceLogs,
  activePhase = null,
  selectedEventId = null,
  linkEnabled = true,
  onToggleLink,
  onSelectPrompt,
  onSelectEvent,
  canCompare = false,
  compareLoading = false,
  onCompareToGolden,
  onPromoteToGolden,
}: TracePanelProps) {
  const filter = useTraceFilter(traceLogs, linkEnabled ? activePhase : null)

  if (traceLogs.length === 0) {
    return (
      <div
        role="log"
        aria-live="polite"
        aria-label="Trace Timeline"
        className="flex h-full items-center justify-center text-sm font-medium text-slate-400 dark:text-slate-500"
      >
        Waiting for run events
      </div>
    )
  }

  return (
    <div role="log" aria-live="polite" aria-label="Trace Timeline" className="flex h-full min-h-0 flex-col">
      <div className="shrink-0 space-y-3 border-b border-border bg-card p-4">
        <div className="flex items-center justify-between gap-3">
          <h3 className="font-semibold text-foreground">Trace Timeline</h3>
          <div className="flex items-center gap-2">
            <button
              type="button"
              aria-label="Compare trace to golden baseline"
              disabled={!canCompare || compareLoading}
              onClick={onCompareToGolden}
              className="flex items-center gap-1 rounded-md border border-sky-200 px-2 py-1 text-xs font-semibold text-sky-700 hover:bg-sky-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-sky-900 dark:text-sky-300 dark:hover:bg-sky-950/40"
            >
              <GitCompareArrows className="h-3.5 w-3.5" />
              {compareLoading ? 'Comparing' : 'Compare'}
            </button>
            <button
              type="button"
              aria-label="Promote run to golden baseline"
              disabled={!canCompare}
              onClick={onPromoteToGolden}
              className="flex items-center gap-1 rounded-md border border-amber-200 px-2 py-1 text-xs font-semibold text-amber-700 hover:bg-amber-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-amber-900 dark:text-amber-300 dark:hover:bg-amber-950/40"
            >
              <BadgeCheck className="h-3.5 w-3.5" />
              Golden
            </button>
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
        <div className="text-xs font-medium text-muted-foreground">
          Showing {filter.filteredEvents.length} of {traceLogs.length} events
        </div>
      </div>
      <div className="min-h-0 flex-1 p-4">
        <VirtualTraceList
          events={filter.filteredEvents}
          activePhase={activePhase}
          selectedEventId={selectedEventId}
          linkEnabled={linkEnabled}
          onSelectPrompt={onSelectPrompt}
          onSelectEvent={onSelectEvent}
        />
      </div>
    </div>
  )
}
