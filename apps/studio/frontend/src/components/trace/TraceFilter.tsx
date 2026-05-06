import { FilterX } from 'lucide-react'

interface TraceFilterProps {
  eventTypes: string[]
  phases: string[]
  selectedTypes: string[]
  selectedPhases: string[]
  activePhase: string | null
  onToggleType: (eventType: string) => void
  onTogglePhase: (phase: string) => void
  onClear: () => void
}

function chipClass(selected: boolean): string {
  return selected
    ? 'border-sky-300 bg-sky-50 text-sky-700 dark:border-sky-700 dark:bg-sky-900/30 dark:text-sky-300'
    : 'border-gray-200 bg-white text-gray-600 hover:bg-gray-50 dark:border-slate-800 dark:bg-slate-900 dark:text-gray-400 dark:hover:bg-slate-800'
}

export function TraceFilter({
  eventTypes,
  phases,
  selectedTypes,
  selectedPhases,
  activePhase,
  onToggleType,
  onTogglePhase,
  onClear,
}: TraceFilterProps) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-3">
        <div className="text-xs font-semibold uppercase text-gray-400 dark:text-gray-500">
          Filters {activePhase ? <span className="normal-case text-sky-600 dark:text-sky-400">active phase: {activePhase}</span> : null}
        </div>
        <button
          type="button"
          onClick={onClear}
          className="flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-gray-500 hover:bg-gray-100 hover:text-gray-800 dark:text-gray-400 dark:hover:bg-slate-800 dark:hover:text-gray-100"
        >
          <FilterX className="h-3.5 w-3.5" />
          Clear
        </button>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {eventTypes.map((eventType) => (
          <button
            key={eventType}
            type="button"
            onClick={() => onToggleType(eventType)}
            className={`rounded-full border px-2 py-0.5 text-xs font-medium ${chipClass(selectedTypes.includes(eventType))}`}
          >
            {eventType}
          </button>
        ))}
      </div>
      <div className="flex flex-wrap gap-1.5">
        {phases.map((phase) => (
          <button
            key={phase}
            type="button"
            onClick={() => onTogglePhase(phase)}
            className={`rounded-full border px-2 py-0.5 text-xs font-medium ${chipClass(selectedPhases.includes(phase))}`}
          >
            {phase}
          </button>
        ))}
      </div>
    </div>
  )
}
