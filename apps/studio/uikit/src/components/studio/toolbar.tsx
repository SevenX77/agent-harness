
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
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarSeparator,
} from "@/components/ui/sidebar"

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
    <Sidebar
      collapsible="icon"
      side="left"
      className="top-11 h-[calc(100svh-2.75rem)]"
    >
      <SidebarHeader className="items-center py-3">
        <div className="size-8 rounded-md bg-sidebar-primary flex items-center justify-center">
          <Layers className="size-4 text-sidebar-primary-foreground" strokeWidth={2} />
        </div>
      </SidebarHeader>

      <SidebarContent>
        <SidebarMenu className="items-center gap-1 px-2">
        {tools.map((tool) => {
          const isActive = activePanel === tool.id
          const isAdd = tool.id === "add"
          return (
            <SidebarMenuItem key={tool.id} className="w-8">
              <SidebarMenuButton
                isActive={isActive}
                tooltip={`${tool.label} ${tool.shortcut}`}
                onClick={() =>
                  isAdd
                    ? undefined
                    : onPanelChange(isActive ? null : tool.id)
                }
                className="size-8 rounded-md justify-center text-sidebar-foreground dark:text-sidebar-foreground"
                aria-pressed={isActive}
              >
                <tool.icon className="size-4" strokeWidth={1.75} />
                <span>{tool.label}</span>
              </SidebarMenuButton>
              {tool.dividerAfter && <SidebarSeparator className="my-2" />}
            </SidebarMenuItem>
          )
        })}
        </SidebarMenu>
      </SidebarContent>

      <SidebarFooter className="items-center py-3">
        <SidebarMenu className="items-center">
          <SidebarMenuItem className="w-8">
            <SidebarMenuButton
              tooltip="Help"
              className="size-8 rounded-md justify-center text-sidebar-foreground dark:text-sidebar-foreground"
            >
            <HelpCircle className="size-4" strokeWidth={1.75} />
              <span>Help</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  )
}
