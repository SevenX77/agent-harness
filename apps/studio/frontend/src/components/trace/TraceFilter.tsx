import { FilterX } from 'lucide-react'
import { Button } from '../ui/button'
import { ToggleGroup, ToggleGroupItem } from '../ui/toggle-group'
import { TRACE_CATEGORIES, TRACE_CATEGORY_LABEL, type TraceCategory } from './trace-category'

interface TraceFilterProps {
  phases: string[]
  selectedCategories: TraceCategory[]
  selectedPhases: string[]
  activePhase: string | null
  onSelectCategories: (categories: TraceCategory[]) => void
  onSelectPhases: (phases: string[]) => void
  onClear: () => void
}

/**
 * Two rows, both of fixed height: the four semantic buckets, then the run's
 * nodes. Node chips scroll sideways rather than wrapping — the filter is a
 * control strip, and a control strip that grows a row per handful of nodes eats
 * the panel it is meant to serve.
 */
export function TraceFilter({
  phases,
  selectedCategories,
  selectedPhases,
  activePhase,
  onSelectCategories,
  onSelectPhases,
  onClear,
}: TraceFilterProps) {
  const hasFilters = selectedCategories.length > 0 || selectedPhases.length > 0

  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-2">
        <ToggleGroup
          type="multiple"
          size="sm"
          variant="outline"
          spacing={1}
          value={selectedCategories}
          onValueChange={(value: string[]) => onSelectCategories(value as TraceCategory[])}
          aria-label="Filter by event category"
        >
          {TRACE_CATEGORIES.map((category) => (
            <ToggleGroupItem key={category} value={category} aria-label={TRACE_CATEGORY_LABEL[category]}>
              {TRACE_CATEGORY_LABEL[category]}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
        {activePhase ? (
          <span className="truncate text-xs text-muted-foreground" title={`Linked to ${activePhase}`}>
            → {activePhase}
          </span>
        ) : null}
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="ml-auto h-6 shrink-0 px-2 text-xs"
          onClick={onClear}
          disabled={!hasFilters}
        >
          <FilterX className="size-3.5" />
          Clear
        </Button>
      </div>
      {phases.length > 0 ? (
        <div
          data-trace-node-filter
          className="overflow-x-auto [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
        >
          <ToggleGroup
            type="multiple"
            size="sm"
            variant="outline"
            spacing={1}
            value={selectedPhases}
            onValueChange={onSelectPhases}
            aria-label="Filter by node"
            className="w-max flex-nowrap"
          >
            {phases.map((phase) => (
              <ToggleGroupItem key={phase} value={phase} className="shrink-0 font-mono">
                {phase}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        </div>
      ) : null}
    </div>
  )
}
