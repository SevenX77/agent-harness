import { cn } from "@/lib/utils"
import { Clock, FileInput, Files, Moon, Settings, Settings2, Sun } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { useTheme } from "@/hooks/use-theme"

interface ToolbarProps {
  activePanel: string | null
  onPanelChange: (panel: string | null) => void
  onSettingsOpen: () => void
}

const tools = [
  { id: "assets", icon: Files, label: "Assets", shortcut: "1" },
  { id: "input", icon: FileInput, label: "Input", shortcut: "2" },
  { id: "timeline", icon: Clock, label: "Trace Timeline", shortcut: "3" },
  { id: "properties", icon: Settings2, label: "Properties", shortcut: "4" },
]

export function Toolbar({ activePanel, onPanelChange, onSettingsOpen }: ToolbarProps) {
  const { theme, toggleTheme } = useTheme()

  return (
    <div className="flex flex-col items-center py-3 px-2 bg-sidebar border-r border-border w-12">
      <div className="flex flex-col gap-1">
        {tools.map((tool) => {
          const isActive = activePanel === tool.id
          return (
            <Tooltip key={tool.id}>
              <TooltipTrigger asChild>
                <Button
                  variant={isActive ? "secondary" : "ghost"}
                  size="icon"
                  onClick={() => onPanelChange(isActive ? null : tool.id)}
                  className={cn("size-8")}
                  aria-label={tool.label}
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
          )
        })}
      </div>

      <div className="flex-1" />

      <div className="flex flex-col gap-1">
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              onClick={toggleTheme}
              className="size-8"
              aria-label="Toggle theme"
            >
              {theme === "dark" ? (
                <Sun className="size-4" strokeWidth={1.75} />
              ) : (
                <Moon className="size-4" strokeWidth={1.75} />
              )}
            </Button>
          </TooltipTrigger>
          <TooltipContent side="right" sideOffset={8}>
            {theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          </TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              onClick={onSettingsOpen}
              className="size-8"
              aria-label="Settings"
            >
              <Settings className="size-4" strokeWidth={1.75} />
            </Button>
          </TooltipTrigger>
          <TooltipContent side="right" sideOffset={8}>
            Settings
          </TooltipContent>
        </Tooltip>
      </div>
    </div>
  )
}
