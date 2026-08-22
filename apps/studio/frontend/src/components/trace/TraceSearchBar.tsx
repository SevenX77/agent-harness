import { SearchIcon, XIcon } from 'lucide-react'
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupInput,
  InputGroupText,
} from '../ui/input-group'
import { Tooltip, TooltipContent, TooltipTrigger } from '../ui/tooltip'
import { useTraceCopy } from './trace-copy'

interface TraceSearchBarProps {
  value: string
  onChange: (value: string) => void
  /** How many filter tags are on. Reported here so a closed filter row is never a silent one. */
  activeFilterCount?: number
  /**
   * How many steps the narrowing left, or `null` when nothing is narrowed.
   *
   * Read off the very list below it rather than counted again here — F3's
   * 2026-08-20 rule is that a count nobody can find by looking is worse than no
   * count, and two counts of one thing are exactly how that happens. Zero is
   * reported, not hidden: "nothing matched" is the answer the reader needs most.
   */
  matchCount?: number | null
}

/**
 * Composed exactly as the shadcn InputGroup example composes it (decision
 * 2026-08-09 D10): the icons carry no size or colour of their own, because the
 * addon and the button already state both. Overriding them is what made this
 * bar look wrong at every size it was tried at.
 */
export function TraceSearchBar({ value, onChange, activeFilterCount = 0, matchCount = null }: TraceSearchBarProps) {
  const t = useTraceCopy()
  return (
    <InputGroup>
      <InputGroupInput
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={t('search.placeholder')}
      />
      <InputGroupAddon>
        <SearchIcon />
      </InputGroupAddon>
      {activeFilterCount > 0 ? (
        <InputGroupAddon
          align="inline-end"
          className="group-focus-within/trace-search:hidden"
        >
          <Tooltip>
            <TooltipTrigger asChild>
              <InputGroupText aria-label={t('search.filtersOn', { count: activeFilterCount })}>
                {activeFilterCount}
              </InputGroupText>
            </TooltipTrigger>
            <TooltipContent>
              {t('search.filtersTooltip', { count: activeFilterCount })}
            </TooltipContent>
          </Tooltip>
        </InputGroupAddon>
      ) : null}
      {matchCount === null ? null : (
        <InputGroupAddon align="inline-end">
          <Tooltip>
            <TooltipTrigger asChild>
              <InputGroupText
                data-trace-match-count={matchCount}
                aria-label={t('search.matchCount', { count: matchCount })}
              >
                {t('search.matchCount', { count: matchCount })}
              </InputGroupText>
            </TooltipTrigger>
            <TooltipContent>{t('search.matchCountTooltip', { count: matchCount })}</TooltipContent>
          </Tooltip>
        </InputGroupAddon>
      )}
      {value ? (
        <InputGroupAddon align="inline-end">
          <Tooltip>
            <TooltipTrigger asChild>
              <InputGroupButton type="button" aria-label={t('search.clear')} onClick={() => onChange('')}>
                <XIcon />
              </InputGroupButton>
            </TooltipTrigger>
            <TooltipContent>{t('search.clear')}</TooltipContent>
          </Tooltip>
        </InputGroupAddon>
      ) : null}
    </InputGroup>
  )
}
