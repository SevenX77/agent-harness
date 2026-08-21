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
}

/**
 * Composed exactly as the shadcn InputGroup example composes it (decision
 * 2026-08-09 D10): the icons carry no size or colour of their own, because the
 * addon and the button already state both. Overriding them is what made this
 * bar look wrong at every size it was tried at.
 */
export function TraceSearchBar({ value, onChange, activeFilterCount = 0 }: TraceSearchBarProps) {
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
