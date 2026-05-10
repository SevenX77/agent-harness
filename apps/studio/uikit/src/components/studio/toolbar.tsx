
import { cn } from "@/lib/utils"
import {
  Plus,
  Files,
  Clock,
  Settings2,
  Code2,
  Search,
  HelpCircle,
  Layers,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { Separator } from "@/components/ui/separator"

interface ToolbarProps {
  activePanel: string | null
  onPanelChange: (panel: string | null) => void
}

const tools = [
  { id: "add", icon: Plus, label: "Add Node", shortcut: "A", dividerAfter: true },
  { id: "assets", icon: Files, label: "Assets", shortcut: "1" },
  { id: "timeline", icon: Clock, label: "Trace Timeline", shortcut: "2" },
  { id: "properties", icon: Settings2, label: "Properties", shortcut: "3" },
  { id: "editor", icon: Code2, label: "Code Editor", shortcut: "4" },
  { id: "search", icon: Search, label: "Search", shortcut: "/" },
]

export function Toolbar({ activePanel, onPanelChange }: ToolbarProps) {
  return (
    <div className="flex flex-col items-center py-3 px-2 bg-sidebar border-r border-border w-12">
      {/* Logo */}
      <div className="size-7 rounded-md bg-foreground flex items-center justify-center mb-4">
        <Layers className="size-4 text-background" strokeWidth={2} />
      </div>

      {/* Tools */}
      <div className="flex flex-col gap-1">
        {tools.map((tool) => {
          const isActive = activePanel === tool.id
          const isAdd = tool.id === "add"
          return (
            <div key={tool.id}>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant={isActive ? "secondary" : "ghost"}
                    size="icon"
                    onClick={() =>
                      isAdd
                        ? undefined
                        : onPanelChange(isActive ? null : tool.id)
                    }
                    className={cn("size-8", isAdd && "text-primary")}
                    aria-pressed={isActive}
                  >
                    <tool.icon className="size-4" strokeWidth={1.75} />
                  </Button>
                </TooltipTrigger>
                <TooltipContent side="right" sideOffset={8}>
                  <span>{tool.label}</span>
                  <span className="ml-2 text-muted-foreground text-xs">
                    {tool.shortcut}
                  </span>
                </TooltipContent>
              </Tooltip>
              {tool.dividerAfter && <Separator className="my-2" />}
            </div>
          )
        })}
      </div>

      {/* Spacer */}
      <div className="flex-1" />

      {/* Help */}
      <Tooltip>
        <TooltipTrigger asChild>
          <Button variant="ghost" size="icon" className="size-8">
            <HelpCircle className="size-4" strokeWidth={1.75} />
          </Button>
        </TooltipTrigger>
        <TooltipContent side="right" sideOffset={8}>
          Help
        </TooltipContent>
      </Tooltip>
    </div>
  )
}
