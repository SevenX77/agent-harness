import { useMemo, useState } from 'react'
import { Group, Panel, Separator } from 'react-resizable-panels'
import { GraphCanvas, type SkillGraphNodeData } from '../GraphCanvas'
import { CopilotPanel } from '../copilot/copilot-panel'
import { useCopilotContext } from '../../hooks/useCopilotContext'
import { readLintStatus } from '../../hooks/useDebouncedLint'
import { useSkills } from '../../hooks/useSkills'
import { WelcomePage } from '../welcome/WelcomePage'
import { Header } from './Header'
import { Panels, type FileMeta } from './Panels'
import { SettingsPage } from './SettingsPage'
import { SplitEditor } from './SplitEditor'
import { Toolbar, type PanelKind } from './Toolbar'

interface WorkspaceProps {
  skillId: string | null
  onSelectSkill: (skillId: string) => void
  onCloseSkill: () => void
}

export function Workspace({ skillId, onSelectSkill }: WorkspaceProps) {
  const [activePanel, setActivePanel] = useState<PanelKind | null>('assets')
  const [copilotOpen, setCopilotOpen] = useState(true)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [openFile, setOpenFile] = useState<FileMeta | null>(null)
  const [fileDrafts, setFileDrafts] = useState<Record<string, string>>({})
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [selectedNode, setSelectedNode] = useState<{ id: string, data: SkillGraphNodeData } | null>(null)
  const { skillDetail, skillDetailError } = useSkills(skillId)
  const isLoading = useMemo(() => Boolean(skillId && !skillDetail && !skillDetailError), [skillDetail, skillDetailError, skillId])

  useCopilotContext({
    skillId,
    view: 'Edit',
    context: {
      selected_node_id: selectedNodeId,
      selected_node: selectedNode ? {
        id: selectedNode.id,
        label: selectedNode.data.label,
        status: selectedNode.data.status,
        summary: typeof selectedNode.data.summary === 'string' ? selectedNode.data.summary : null,
      } : null,
      lint_status: skillId ? readLintStatus(skillId) : 'idle',
    },
  })

  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden bg-background text-foreground">
      <Header skillId={skillId} copilotOpen={copilotOpen} onCopilotToggle={() => setCopilotOpen((open) => !open)} />
      <div className="relative flex min-h-0 flex-1">
        <Toolbar activePanel={activePanel} onPanelChange={setActivePanel} onSettingsOpen={() => setSettingsOpen(true)} />
        <Group id="studio-workspace-h" orientation="horizontal" className="min-w-0 flex-1">
          {activePanel ? (
            <>
              <Panel id="left-panel" defaultSize="20%" minSize="14%" maxSize="35%">
                <Panels
                  activePanel={activePanel}
                  skillId={skillId}
                  skillDetail={skillDetail}
                  selectedNode={selectedNode}
                  onFileOpen={(file) => {
                    setOpenFile(file)
                    setSettingsOpen(false)
                  }}
                />
              </Panel>
              <Separator className="z-20 w-px bg-border transition-colors hover:bg-ring" />
            </>
          ) : null}

          <Panel id="canvas" defaultSize={copilotOpen ? '60%' : '80%'} minSize="30%">
            <div className="relative size-full">
              {settingsOpen ? (
                <SettingsPage onClose={() => setSettingsOpen(false)} />
              ) : skillId && openFile ? (
                <SplitEditor
                  file={openFile}
                  value={fileDrafts[openFile.path] ?? openFile.content}
                  onChange={(value) => setFileDrafts((current) => ({ ...current, [openFile.path]: value }))}
                  onCloseFile={() => setOpenFile(null)}
                  skillId={skillId}
                  skillDetail={skillDetail}
                  isLoading={isLoading}
                  error={skillDetailError}
                  selectedNodeId={selectedNodeId}
                  onNodeSelect={(node) => {
                    setSelectedNodeId(node.id)
                    setSelectedNode(node)
                  }}
                />
              ) : skillId === null ? (
                <WelcomePage onSelectSkill={onSelectSkill} />
              ) : (
                <GraphCanvas
                  skillId={skillId}
                  skillDetail={skillDetail}
                  isLoading={isLoading}
                  error={skillDetailError}
                  selectedNodeId={selectedNodeId}
                  onNodeSelect={(node) => {
                    setSelectedNodeId(node.id)
                    setSelectedNode(node)
                  }}
                />
              )}
            </div>
          </Panel>

          {copilotOpen ? (
            <>
              <Separator className="z-20 w-px bg-border transition-colors hover:bg-ring" />
              <Panel id="copilot" defaultSize="20%" minSize="18%" maxSize="35%">
                <CopilotPanel skillId={skillId} />
              </Panel>
            </>
          ) : null}
        </Group>
      </div>
    </div>
  )
}
