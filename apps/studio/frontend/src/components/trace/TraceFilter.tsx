import { Filter, X } from 'lucide-react'
import { Badge } from '../ui/badge'
import { Button } from '../ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '../ui/popover'
import { Tooltip, TooltipContent, TooltipTrigger } from '../ui/tooltip'
import { ToggleGroup, ToggleGroupItem } from '../ui/toggle-group'
import { TRACE_CATEGORIES, TRACE_CATEGORY_LABEL, type TraceCategory } from './trace-category'

interface TraceFilterProps {
  phases: string[]
  selectedCategories: TraceCategory[]
  selectedPhases: string[]
  onSelectCategories: (categories: TraceCategory[]) => void
  onSelectPhases: (phases: string[]) => void
}

/**
 * The filter controls, on demand.
 *
 * Filtering is occasional and the event list is the point of the panel, so the
 * controls live behind one icon button instead of two permanently-mounted
 * toggle rows that cost ~74px of an ~830px panel whether or not anyone is
 * filtering (decision 2026-08-08 D4). The button carries the active-condition
 * count; {@link TraceFilterChips} names those conditions, and renders nothing
 * when there are none.
 */
export function TraceFilterButton({
  phases,
  selectedCategories,
  selectedPhases,
  onSelectCategories,
  onSelectPhases,
}: TraceFilterProps) {
  const activeCount = selectedCategories.length + selectedPhases.length

  return (
    <Popover>
      <Tooltip>
        <TooltipTrigger asChild>
          <PopoverTrigger asChild>
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              aria-label="Filter events"
              className={activeCount > 0 ? 'relative text-foreground' : 'relative text-muted-foreground'}
            >
              <Filter className="size-4" />
              {activeCount > 0 ? (
                <Badge
                  variant="secondary"
                  className="absolute -right-1 -top-1 size-3.5 justify-center rounded-full p-0 text-[9px] leading-none"
                >
                  {activeCount}
                </Badge>
              ) : null}
            </Button>
          </PopoverTrigger>
        </TooltipTrigger>
        <TooltipContent>Filter the trace by event kind or node</TooltipContent>
      </Tooltip>
      <PopoverContent align="end" className="w-64 space-y-3 p-3">
        <section className="space-y-1.5">
          <p className="text-xs font-medium text-muted-foreground">Kind</p>
          <ToggleGroup
            type="multiple"
            size="sm"
            variant="outline"
            spacing={1}
            value={selectedCategories}
            onValueChange={(value: string[]) => onSelectCategories(value as TraceCategory[])}
            aria-label="Filter by event category"
            className="flex-wrap justify-start"
          >
            {TRACE_CATEGORIES.map((category) => (
              <ToggleGroupItem key={category} value={category} aria-label={TRACE_CATEGORY_LABEL[category]}>
                {TRACE_CATEGORY_LABEL[category]}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        </section>
        {phases.length > 0 ? (
          <section className="space-y-1.5">
            <p className="text-xs font-medium text-muted-foreground">Node</p>
            <ToggleGroup
              type="multiple"
              size="sm"
              variant="outline"
              spacing={1}
              value={selectedPhases}
              onValueChange={onSelectPhases}
              aria-label="Filter by node"
              className="flex-wrap justify-start"
            >
              {phases.map((phase) => (
                <ToggleGroupItem key={phase} value={phase} className="font-mono">
                  {phase}
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
          </section>
        ) : null}
      </PopoverContent>
    </Popover>
  )
}

/**
 * Which conditions are currently narrowing the list, each removable in place.
 * Returns null when nothing is filtered, so the region it sits in has no height
 * in the resting state.
 */
export function TraceFilterChips({
  selectedCategories,
  selectedPhases,
  onSelectCategories,
  onSelectPhases,
}: Omit<TraceFilterProps, 'phases'>) {
  if (selectedCategories.length === 0 && selectedPhases.length === 0) {
    return null
  }
  return (
    <>
      {selectedCategories.map((category) => (
        <FilterChip
          key={`category-${category}`}
          label={TRACE_CATEGORY_LABEL[category]}
          onRemove={() => onSelectCategories(selectedCategories.filter((value) => value !== category))}
        />
      ))}
      {selectedPhases.map((phase) => (
        <FilterChip
          key={`phase-${phase}`}
          label={phase}
          mono
          onRemove={() => onSelectPhases(selectedPhases.filter((value) => value !== phase))}
        />
      ))}
    </>
  )
}

function FilterChip({ label, mono = false, onRemove }: { label: string, mono?: boolean, onRemove: () => void }) {
  return (
    <Badge variant="secondary" className={`gap-1 ${mono ? 'font-mono' : ''}`}>
      {label}
      <button
        type="button"
        aria-label={`Remove filter ${label}`}
        onClick={onRemove}
        className="text-muted-foreground hover:text-foreground"
      >
        <X className="size-3" />
      </button>
    </Badge>
  )
}
