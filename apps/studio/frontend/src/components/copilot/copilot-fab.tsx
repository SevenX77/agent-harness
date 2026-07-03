import { cn } from '@/lib/utils'
import { Button } from '../ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '../ui/tooltip'
import { MoiraiMark } from './moirai-mark'

interface CopilotFabProps {
  onClick: () => void
  className?: string
}

/**
 * Floating action button that opens the collapsed copilot panel. A solid
 * primary-filled circle (not a bare icon on the canvas) so it stays legible on
 * the near-black canvas; the MoirAI mark inherits `text-primary-foreground`.
 */
export function CopilotFab({ onClick, className }: CopilotFabProps) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          type="button"
          onClick={onClick}
          aria-label="打开 MoirAI"
          className={cn(
            'size-12 rounded-full p-0 shadow-lg shadow-primary/40 ring-1 ring-inset ring-primary-foreground/20',
            className,
          )}
        >
          <MoiraiMark className="size-6" />
        </Button>
      </TooltipTrigger>
      <TooltipContent side="left">打开 MoirAI</TooltipContent>
    </Tooltip>
  )
}
