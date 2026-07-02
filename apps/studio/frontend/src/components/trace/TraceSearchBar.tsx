import { Search, X } from 'lucide-react'
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupInput,
} from '../ui/input-group'
import { Tooltip, TooltipContent, TooltipTrigger } from '../ui/tooltip'

interface TraceSearchBarProps {
  value: string
  onChange: (value: string) => void
}

export function TraceSearchBar({ value, onChange }: TraceSearchBarProps) {
  return (
    <InputGroup>
      <InputGroupAddon>
        <Search className="h-4 w-4 text-muted-foreground" />
      </InputGroupAddon>
      <InputGroupInput
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder="Search trace events"
      />
      {value ? (
        <InputGroupAddon align="inline-end">
          <Tooltip>
            <TooltipTrigger asChild>
              <InputGroupButton
                type="button"
                aria-label="Clear search"
                onClick={() => onChange('')}
              >
                <X className="h-4 w-4" />
              </InputGroupButton>
            </TooltipTrigger>
            <TooltipContent>Clear search</TooltipContent>
          </Tooltip>
        </InputGroupAddon>
      ) : null}
    </InputGroup>
  )
}
