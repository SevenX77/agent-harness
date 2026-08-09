import { ToggleGroup, ToggleGroupItem } from '../ui/toggle-group'
import { TRACE_CATEGORIES, TRACE_CATEGORY_LABEL, type TraceCategory } from './trace-category'

interface TraceFilterRowProps {
  phases: string[]
  selectedCategories: TraceCategory[]
  selectedPhases: string[]
  onSelectCategories: (categories: TraceCategory[]) => void
  onSelectPhases: (phases: string[]) => void
}

/**
 * The filter tags, living under the search box (decision 2026-08-09 D11).
 *
 * Searching and filtering are the same act — "show me less" — so they share one
 * place and one moment: the row opens while the search area holds focus and
 * closes when it does not. Focus is read with `focus-within` on the shared
 * `group/trace-search` wrapper rather than on the input, because clicking a tag
 * moves focus INTO the row, and a row that closes the instant you reach for it
 * cannot be used.
 *
 * Closing does not clear anything. What is still filtering is reported as a
 * count inside the search box ({@link TraceSearchBar}), which is where the
 * reader is already looking — not back up on the run identity strip.
 */
export function TraceFilterRow({
  phases,
  selectedCategories,
  selectedPhases,
  onSelectCategories,
  onSelectPhases,
}: TraceFilterRowProps) {
  return (
    <div className="grid grid-rows-[0fr] transition-[grid-template-rows] duration-200 ease-out group-focus-within/trace-search:grid-rows-[1fr]">
      {/* The 0fr→1fr grid row is what makes an unknown height animate; the inner
          clip is what keeps the collapsed row from spilling. */}
      <div className="overflow-hidden">
        <div className="scrollbar-thin invisible flex flex-nowrap items-center gap-1 overflow-x-auto overflow-y-hidden pt-2 pb-0.5 opacity-0 transition-opacity duration-200 group-focus-within/trace-search:visible group-focus-within/trace-search:opacity-100">
          <ToggleGroup
            type="multiple"
            size="sm"
            variant="outline"
            spacing={1}
            value={selectedCategories}
            onValueChange={(value: string[]) => onSelectCategories(value as TraceCategory[])}
            aria-label="Filter by event kind"
            className="flex-nowrap"
          >
            {TRACE_CATEGORIES.map((category) => (
              <ToggleGroupItem key={category} value={category} className="shrink-0">
                {TRACE_CATEGORY_LABEL[category]}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
          {phases.length > 0 ? (
            <>
              <span aria-hidden="true" className="mx-1 h-4 w-px shrink-0 bg-border" />
              <ToggleGroup
                type="multiple"
                size="sm"
                variant="outline"
                spacing={1}
                value={selectedPhases}
                onValueChange={onSelectPhases}
                aria-label="Filter by node"
                className="flex-nowrap"
              >
                {phases.map((phase) => (
                  <ToggleGroupItem key={phase} value={phase} className="shrink-0 font-mono">
                    {phase}
                  </ToggleGroupItem>
                ))}
              </ToggleGroup>
            </>
          ) : null}
        </div>
      </div>
    </div>
  )
}
