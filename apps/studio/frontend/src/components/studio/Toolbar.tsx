import { Clock, FileInput, Files, FileText, History, Moon, Settings, Settings2, Sun } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"
import { toggleTheme, useThemeValue } from "@/store/themeStore"

export type PanelKind = "assets" | "input" | "timeline" | "trace-doc" | "properties" | "local-history"

interface ToolbarProps {
  activePanel: PanelKind | null
  onPanelChange: (panel: PanelKind | null) => void
  settingsOpen: boolean
  onSettingsToggle: () => void
}

const tools: Array<{ id: PanelKind; icon: typeof Files; label: string; shortcut: string }> = [
  { id: "assets", icon: Files, label: "Assets", shortcut: "1" },
  { id: "properties", icon: Settings2, label: "Properties", shortcut: "2" },
  { id: "input", icon: FileInput, label: "I/O", shortcut: "3" },
  { id: "timeline", icon: Clock, label: "Timeline", shortcut: "4" },
  { id: "trace-doc", icon: FileText, label: "Full Trace", shortcut: "5" },
  { id: "local-history", icon: History, label: "Local History", shortcut: "6" },
]

export function Toolbar({ activePanel, onPanelChange, settingsOpen, onSettingsToggle }: ToolbarProps) {
  const theme = useThemeValue()

  return (
    <aside className="z-10 flex w-12 shrink-0 flex-col items-center border-r border-border bg-sidebar px-2 py-3">
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
                <span className="ml-2 text-xs text-muted-foreground">
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
              onClick={() => toggleTheme()}
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
              variant={settingsOpen ? "secondary" : "ghost"}
              size="icon"
              onClick={onSettingsToggle}
              className="size-8"
              aria-label="Settings"
              aria-pressed={settingsOpen}
            >
              <Settings className="size-4" strokeWidth={1.75} />
            </Button>
          </TooltipTrigger>
          <TooltipContent side="right" sideOffset={8}>
            Settings
          </TooltipContent>
        </Tooltip>
      </div>
    </aside>
  )
}
