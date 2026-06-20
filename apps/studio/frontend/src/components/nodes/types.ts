import type { Node } from '@xyflow/react'
import type { CompileError, IoDeclaration } from '@/api/types'
import type { GoldenNodeState } from '@/components/studio/node-golden'

export type SkillNodeStatus = 'idle' | 'running' | 'success' | 'error' | 'paused' | 'breakpoint'

export interface SubagentRef {
  name: string
  path: string
  description: string
}

export interface SkillGraphNodeData extends Record<string, unknown> {
  skillId: string
  label: string
  mode: string
  role?: string | null
  tools?: string[]
  filePath?: string
  status: SkillNodeStatus
  /** Compile/lint errors attributed to this phase node (separate channel from run status). */
  compileErrors?: CompileError[]
  /**
   * Golden acceptance tri-state for this node (N4 atom #30), a separate channel from
   * run status and compile health: 'has-golden' (🟢, node in a golden baseline's cases)
   * > 'logic-ok' (🟡, agent node ran in the most-recent predict) > undefined (🔘
   * untested). See node-golden.ts.
   */
  goldenState?: GoldenNodeState
  dependsOn: string[]
  subgraphPath?: string | null
  subagents?: SubagentRef[]
  isExpanded?: boolean
  onToggleSubgraph?: () => void
  activeConflict?: { nodeId: string; fieldName: string; ancestorNodeId: string }
  isConflictCancelled?: boolean
  onAllowSequentialOverwrite?: (nodeId: string, fieldName: string) => void
  onCancelWarning?: (nodeId: string) => void
}

export type SkillGraphNode = Node<SkillGraphNodeData, 'skill'>

export interface GlobalNodeData extends Record<string, unknown> {
  type: 'global-input' | 'global-output'
  schema: IoDeclaration
}

export type GraphCanvasNode =
  | Node<SkillGraphNodeData, 'skill'>
  | Node<GlobalNodeData, 'globalInput'>
  | Node<GlobalNodeData, 'globalOutput'>
