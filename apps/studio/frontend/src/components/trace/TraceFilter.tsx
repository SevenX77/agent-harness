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
    ? 'border-primary/60 bg-primary/10 text-primary'
    : 'border-border bg-card text-muted-foreground hover:bg-muted/40'
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
        <div className="text-xs font-semibold uppercase text-muted-foreground">
          Filters {activePhase ? <span className="normal-case text-primary">active phase: {activePhase}</span> : null}
        </div>
        <button
          type="button"
          onClick={onClear}
          className="flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-muted-foreground hover:bg-muted/40 hover:text-foreground"
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
