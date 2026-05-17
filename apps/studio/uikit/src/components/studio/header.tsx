import { Layers, Sparkles } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"

type Status = "draft" | "compiled" | "running"

interface HeaderProps {
  projectName: string
  status: Status
  copilotOpen: boolean
  onCopilotToggle: () => void
}

const STATUS_VARIANT: Record<Status, "default" | "secondary" | "outline"> = {
  draft: "outline",
  compiled: "secondary",
  running: "default",
}

export function Header({
  projectName,
  status,
  copilotOpen,
  onCopilotToggle,
}: HeaderProps) {
  return (
    <header className="h-11 border-b border-border grid grid-cols-3 items-center px-3 bg-background">
      <div className="flex items-center gap-2">
        <div className="size-6 rounded-md bg-foreground flex items-center justify-center">
          <Layers className="size-3.5 text-background" strokeWidth={2} />
        </div>
        <span className="text-sm font-semibold text-foreground tracking-tight">
          GSkill Studio
        </span>
      </div>

      <div className="flex items-center justify-center gap-2">
        <span className="text-sm font-medium text-foreground">{projectName}</span>
        <Badge variant={STATUS_VARIANT[status]} className="uppercase">
          {status}
        </Badge>
      </div>

      <div className="flex items-center justify-end">
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              onClick={onCopilotToggle}
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
