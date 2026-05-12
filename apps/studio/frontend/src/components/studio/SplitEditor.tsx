import { Group, Panel, Separator } from 'react-resizable-panels'
import { GraphCanvas, type SkillGraphNodeData } from '../GraphCanvas'
import type { SkillDetail } from '../../api/types'
import { LazyMonacoPanel } from './LazyMonacoPanel'
import type { FileMeta } from './Panels'

interface SplitEditorProps {
  file: FileMeta
  value: string
  onChange: (value: string) => void
  onCloseFile: () => void
  skillId: string
  skillDetail?: SkillDetail
  isLoading?: boolean
  error?: unknown
  selectedNodeId?: string | null
  onNodeSelect?: (node: { id: string, data: SkillGraphNodeData }) => void
}

export function SplitEditor({
  file,
  value,
  onChange,
  onCloseFile,
  skillId,
  skillDetail,
  isLoading,
  error,
  selectedNodeId,
  onNodeSelect,
}: SplitEditorProps) {
  return (
    <Group id="studio-canvas-v" orientation="vertical" className="size-full">
      <Panel id="top-editor" defaultSize="70%" minSize="30%">
        <LazyMonacoPanel
          title={file.path}
          language={file.language}
          value={value}
          onChange={onChange}
          onClose={onCloseFile}
        />
      </Panel>
      <Separator className="z-20 h-px bg-border transition-colors hover:bg-ring" />
      <Panel id="bottom-mini" defaultSize="30%" minSize="15%" maxSize="60%">
        <div className="size-full border-t border-border">
          <GraphCanvas
            skillId={skillId}
            skillDetail={skillDetail}
            isLoading={isLoading}
            error={error}
            selectedNodeId={selectedNodeId}
            onNodeSelect={onNodeSelect}
          />
        </div>
      </Panel>
    </Group>
  )
}
