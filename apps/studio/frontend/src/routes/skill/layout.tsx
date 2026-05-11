import { Outlet, useParams } from 'react-router-dom'
import { Group, Panel, Separator } from 'react-resizable-panels'
import { Header } from '../../components/studio/Header'
import { Toolbar } from '../../components/studio/Toolbar'

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
      <Header />
      <div className="flex min-h-0 flex-1">
        <Toolbar />
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
