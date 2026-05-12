import type { PanelKind } from './Toolbar'

interface PanelsProps {
  activePanel: PanelKind
  skillId: string | null
}

const PANEL_COPY: Record<PanelKind, { title: string, description: string }> = {
  assets: {
    title: 'Assets',
    description: 'Skill files and artifacts will be wired up in Phase 2.',
  },
  input: {
    title: 'Input',
    description: 'Input files and schema editing will be wired up in Phase 3.',
  },
  timeline: {
    title: 'Timeline',
    description: 'Run history and trace timeline will be wired up in Phase 2.',
  },
  properties: {
    title: 'Properties',
    description: 'Node and skill properties will be wired up in Phase 2.',
  },
}

export function Panels({ activePanel, skillId }: PanelsProps) {
  const panel = PANEL_COPY[activePanel]

  return (
    <div className="flex h-full w-full flex-col bg-sidebar">
      <div className="flex h-10 shrink-0 items-center px-3">
        <span className="text-xs font-medium text-foreground">{panel.title}</span>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="space-y-2 p-4">
          <h2 className="text-sm font-medium text-foreground">{panel.title}</h2>
          <p className="text-xs text-muted-foreground">{panel.description}</p>
          {skillId ? <p className="text-xs text-muted-foreground">Current skill: {skillId}</p> : null}
        </div>
      </div>
    </div>
  )
}
