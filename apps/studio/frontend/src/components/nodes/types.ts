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
  /**
   * N5 atom #1 (spec F1): one-line error summary for a failed/halted node, derived
   * from this phase's last failure event (validation_fail / retry_exhausted) by the
   * same event→node-status derivation that drives the red light. Rendered in-place on
   * the node so the user sees *why* the run stopped without opening the Properties
   * panel. Only meaningful when `status === 'error'`.
   */
  errorMessage?: string
  /** Compile/lint errors attributed to this phase node (separate channel from run status). */
  compileErrors?: CompileError[]
  /**
   * Golden acceptance tri-state for this node (N4 atom #30), a separate channel from
   * run status and compile health: 'has-golden' (🟢, node in a golden baseline's cases)
   * > 'logic-ok' (🟡, agent node ran in the most-recent predict) > undefined (🔘
   * untested). See node-golden.ts.
   */
  goldenState?: GoldenNodeState
  /**
   * N5 atom #3 (dirty-downstream-graying, spec F3): true when this node is in the
   * `affected_downstream` set the resume-validity endpoint returned for the node
   * the user is resuming from — i.e. an upstream edit made this downstream node's
   * checkpoint stale, so its node-level Resume must NOT be offered. The canvas
   * grays/dims the node and explains why (its Resume can't continue). Unrelated
   * side-branches are absent from the set and stay normal. Driven only by the real
   * backend slice — never set when resume is clean.
   */
  isDirtyDownstream?: boolean
  dependsOn: string[]
  subgraphPath?: string | null
  subagents?: SubagentRef[]
  isExpanded?: boolean
  onToggleSubgraph?: () => void
  /**
   * N2 atom #13 (subgraph-inline-preview): true for the read-only child phase
   * nodes rendered inside an expanded subgraph's inline container. The canvas
   * interaction handlers (select / drill / double-click open-file) skip these so
   * a synthetic preview node never routes to a real phase file or selection.
   */
  isSubgraphPreview?: boolean
  /**
   * N2 atom #15 (l3-step-edit): the agent phase body (SKILL.md text, sans
   * frontmatter handling — the full file content is fine since the step
   * transforms only touch `<step>` blocks). Present only for AGENT nodes so the
   * inline L3 step editor can parse/edit the `<step>` blocks. Sourced from the
   * real SkillDetail.files in build-nodes — never a test-injected field.
   */
  agentBody?: string
  /** Whether the node's inline L3 step editor is expanded (canvas-owned toggle). */
  isStepsExpanded?: boolean
  /** Toggle the inline L3 step editor open/closed (AGENT nodes only). */
  onToggleSteps?: () => void
  /**
   * Persist an edited agent body through the normal phase-file save path
   * (handlePhaseFileSave -> doWriteSkillFile -> native-fs / browser fallback).
   * The canvas binds the file path + optimistic-lock hash; this only forwards the
   * rewritten body string.
   */
  onStepsSave?: (nextBody: string) => void
  activeConflict?: { nodeId: string; fieldName: string; ancestorNodeId: string }
  isConflictCancelled?: boolean
  onAllowSequentialOverwrite?: (nodeId: string, fieldName: string) => void
  onCancelWarning?: (nodeId: string) => void
}

export type SkillGraphNode = Node<SkillGraphNodeData, 'skill'>

export interface GlobalNodeData extends Record<string, unknown> {
  type: 'global-input' | 'global-output'
  schema: IoDeclaration
  isSubgraphPreview?: boolean
}

export const SUBGRAPH_PREVIEW_INPUT_TARGET_HANDLE_ID = 'subgraph-preview-input-target'

/**
 * N2 atom #13 (subgraph-inline-preview): data for the dashed container node that
 * frames an expanded subgraph's inline child topology. Carries the resolve state
 * so the container can render loading / error affordances; loaded child
 * nodes/edges are emitted as siblings in the parent ReactFlow instance (see
 * subgraph-expansion.ts).
 */
export interface SubgraphGroupNodeData extends Record<string, unknown> {
  parentLabel: string
  path: string
  status: 'loading' | 'error' | 'loaded'
  childName?: string
  message?: string
}

export type GraphCanvasNode =
  | Node<SkillGraphNodeData, 'skill'>
  | Node<GlobalNodeData, 'globalInput'>
  | Node<GlobalNodeData, 'globalOutput'>
  | Node<SubgraphGroupNodeData, 'subgraphGroup'>
