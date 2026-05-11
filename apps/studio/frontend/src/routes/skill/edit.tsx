import { useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { GraphCanvas, type SkillGraphNodeData } from '../../components/GraphCanvas'
import { CompilationWidget } from '../../components/studio/CompilationWidget'
import { LazyMonacoPanel } from '../../components/studio/LazyMonacoPanel'
import { PropertiesPanel } from '../../components/studio/PropertiesPanel'
import { useCopilotContext } from '../../hooks/useCopilotContext'
import { readLintStatus } from '../../hooks/useDebouncedLint'
import { useDraftPersist } from '../../hooks/useDraftPersist'
import { useSkills } from '../../hooks/useSkills'

export default function Edit() {
  const { skillId = '' } = useParams()
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [selectedNode, setSelectedNode] = useState<{ id: string, data: SkillGraphNodeData } | null>(null)
  const [promptDrafts, setPromptDrafts] = useState<Record<string, string>>({})
  const { skillDetail, skillDetailError } = useSkills(skillId)
  const isLoading = useMemo(() => !skillDetail && !skillDetailError, [skillDetail, skillDetailError])
  const promptKey = selectedNode?.id ?? 'skill'
  const basePrompt = `# ${selectedNode?.data.label ?? skillId}\n\nDescribe the agent prompt here.`
  const promptValue = promptDrafts[promptKey] ?? basePrompt
  const draft = useDraftPersist({
    skillId,
    content: promptValue,
    baseContent: basePrompt,
    dirty: promptValue !== basePrompt,
  })

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
      current_file: promptKey,
      prompt_preview: promptValue,
      lint_status: readLintStatus(skillId),
      local_draft: {
        dirty: draft.isDirty,
        base_hash: draft.baseHash,
        saved_at: draft.draft?.timestamp ?? null,
      },
    },
  })

  return (
    <div className="grid h-full min-h-0 grid-cols-[minmax(0,1fr)_320px] bg-background text-foreground">
      <div className="grid min-h-0 min-w-0 grid-rows-[minmax(0,1fr)_64px_280px]">
        <div className="min-h-0">
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
        </div>
        <CompilationWidget skillId={skillId} markdown={promptValue} />
        <LazyMonacoPanel
          title={selectedNode ? selectedNode.data.label : 'Skill prompt'}
          value={promptValue}
          onChange={(value) => setPromptDrafts((current) => ({ ...current, [promptKey]: value }))}
        />
      </div>
      <PropertiesPanel skillDetail={skillDetail} selectedNode={selectedNode} />
    </div>
  )
}
