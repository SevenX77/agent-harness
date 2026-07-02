import { Tooltip, TooltipContent, TooltipTrigger } from '../ui/tooltip'

interface DirtyIndicatorProps {
  dirty: boolean
}

export function DirtyIndicator({ dirty }: DirtyIndicatorProps) {
  if (!dirty) {
    return null
  }

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          aria-label="Unsaved draft"
          className="inline-flex h-2.5 w-2.5 rounded-full bg-warning ring-[3px] ring-warning/20"
        />
      </TooltipTrigger>
      <TooltipContent>Unsaved draft</TooltipContent>
    </Tooltip>
  )
}
