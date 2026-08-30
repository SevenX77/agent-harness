import { Activity, FileInput, Files, History, Moon, Settings, Settings2, Sun } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"
import { toggleTheme, useThemeValue } from "@/store/themeStore"

export type PanelKind = "assets" | "input" | "trace" | "properties" | "local-history"

interface ToolbarProps {
  activePanel: PanelKind | null
  onPanelChange: (panel: PanelKind | null) => void
  settingsOpen: boolean
  onSettingsToggle: () => void
}

export function Toolbar({ activePanel, onPanelChange, settingsOpen, onSettingsToggle }: ToolbarProps) {
  const theme = useThemeValue()
  const { t } = useTranslation("studioShell")

  const tools: Array<{ id: PanelKind; icon: typeof Files; label: string; shortcut: string }> = [
    { id: "assets", icon: Files, label: t("rail.assets"), shortcut: "1" },
    { id: "properties", icon: Settings2, label: t("rail.properties"), shortcut: "2" },
    { id: "input", icon: FileInput, label: t("rail.io"), shortcut: "3" },
    // One trace surface, named after what it holds (decision 2026-08-09 D1). The
    // second slot used to be "Full Trace"; the trace itself now reads end to end,
    // so a document view of the same events was the same thing twice.
    { id: "trace", icon: Activity, label: t("rail.trace"), shortcut: "4" },
    { id: "local-history", icon: History, label: t("rail.localHistory"), shortcut: "5" },
  ]

  return (
    // data-studio-rail: the compile-error drawer's outside-dismiss gate
    // (CompileErrorDrawer.isOutsideDismissExempt) treats the rail like the
    // side panels it switches — clicking here must not close the drawer.
    <aside
      data-studio-rail="true"
      className="z-10 flex w-12 shrink-0 flex-col items-center border-r border-border bg-sidebar px-2 py-3"
    >
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
