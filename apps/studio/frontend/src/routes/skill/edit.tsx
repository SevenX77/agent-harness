import { useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { GraphCanvas } from '../../components/GraphCanvas'
import { useSkills } from '../../hooks/useSkills'

export default function Edit() {
  const { skillId = '' } = useParams()
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const { skillDetail, skillDetailError } = useSkills(skillId)
  const isLoading = useMemo(() => !skillDetail && !skillDetailError, [skillDetail, skillDetailError])

  return (
    <div className="flex h-full min-h-0 flex-col bg-background text-foreground">
      <GraphCanvas
        skillId={skillId}
        skillDetail={skillDetail}
        isLoading={isLoading}
        error={skillDetailError}
        selectedNodeId={selectedNodeId}
        onNodeSelect={setSelectedNodeId}
      />
    </div>
  )
}
