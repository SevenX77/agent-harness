import { Layers, Sparkles } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"

interface HeaderProps {
  skillId: string | null
  copilotOpen: boolean
  onCopilotToggle: () => void
}

export function Header({ skillId, copilotOpen, onCopilotToggle }: HeaderProps) {
  return (
    <header
      data-tauri-drag-region
      className="grid h-11 shrink-0 grid-cols-3 items-center border-b border-border bg-background px-3"
    >
      <div className="flex items-center gap-2">
        <div className="flex size-6 items-center justify-center rounded-md bg-foreground">
          <Layers className="size-3.5 text-background" strokeWidth={2} />
        </div>
        <span className="text-sm font-semibold tracking-tight text-foreground">
          GSkill Studio
        </span>
      </div>

      <div className="flex min-w-0 items-center justify-center gap-2">
        <span className="truncate text-sm font-medium text-foreground">
          {skillId ? `Skill ${skillId}` : "Studio Workspace"}
        </span>
        <Badge variant="outline" className="uppercase">
          Draft
        </Badge>
      </div>

      <div className="flex items-center justify-end">
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              onClick={onCopilotToggle}
              aria-label={copilotOpen ? "Hide Copilot" : "Show Copilot"}
              aria-pressed={copilotOpen}
            >
              <Sparkles />
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            {copilotOpen ? "Hide Copilot" : "Show Copilot"}
          </TooltipContent>
        </Tooltip>
      </div>
    </header>
  )
}
