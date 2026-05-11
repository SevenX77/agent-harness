import { Outlet, useParams } from 'react-router-dom'
import { Group, Panel, Separator } from 'react-resizable-panels'

function WorkspaceHeaderPlaceholder() {
  return (
    <header className="flex h-11 shrink-0 items-center border-b border-border bg-background px-3">
      <span className="text-sm font-medium text-foreground">Studio Workspace</span>
    </header>
  )
}

function ToolbarPlaceholder() {
  return (
    <aside className="flex w-12 shrink-0 items-center justify-center border-r border-border bg-sidebar text-sidebar-foreground">
      <span className="sr-only">Workspace navigation</span>
    </aside>
  )
}

function LeftPanelPlaceholder() {
  return (
    <section className="h-full bg-background p-3 text-sm text-muted-foreground">
      Workspace panel
    </section>
  )
}

function CopilotRailPlaceholder() {
  return (
    <aside className="flex h-full flex-col bg-sidebar p-4 text-sidebar-foreground">
      <p className="text-sm font-medium">Copilot</p>
      <p className="mt-2 text-xs text-muted-foreground">Always-on assistant rail</p>
    </aside>
  )
}

export default function SkillLayout() {
  const { skillId } = useParams()
  const autoSaveId = skillId ? `workspace-layout-${skillId}` : 'workspace-layout-new'

  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden bg-background text-foreground">
      <WorkspaceHeaderPlaceholder />
      <div className="flex min-h-0 flex-1">
        <ToolbarPlaceholder />
        <Group orientation="horizontal" id={autoSaveId} className="min-w-0 flex-1">
          <Panel id="workspace-left" defaultSize={20} minSize={14} maxSize={35}>
            <LeftPanelPlaceholder />
          </Panel>
          <Separator className="z-20 w-px bg-border transition-colors hover:bg-ring" />
          <Panel id="workspace-center" defaultSize={58} minSize={30}>
            <main className="h-full overflow-hidden bg-background">
              <Outlet />
            </main>
          </Panel>
          <Separator className="z-20 w-px bg-border transition-colors hover:bg-ring" />
          <Panel id="workspace-copilot" defaultSize={22} minSize={18} maxSize={35}>
            <CopilotRailPlaceholder />
          </Panel>
        </Group>
      </div>
    </div>
  )
}
