import { useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { GraphCanvas, type SkillGraphNodeData } from '../../components/GraphCanvas'
import { PropertiesPanel } from '../../components/studio/PropertiesPanel'
import { useSkills } from '../../hooks/useSkills'

export default function Edit() {
  const { skillId = '' } = useParams()
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [selectedNode, setSelectedNode] = useState<{ id: string, data: SkillGraphNodeData } | null>(null)
  const { skillDetail, skillDetailError } = useSkills(skillId)
  const isLoading = useMemo(() => !skillDetail && !skillDetailError, [skillDetail, skillDetailError])

  return (
    <div className="grid h-full min-h-0 grid-cols-[minmax(0,1fr)_320px] bg-background text-foreground">
      <div className="min-h-0 min-w-0">
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
      <PropertiesPanel skillDetail={skillDetail} selectedNode={selectedNode} />
    </div>
  )
}
