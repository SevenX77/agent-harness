import type { Node } from '@xyflow/react'
import type { CompileError, IoDeclaration, SkillDetail } from '@/api/types'
import type { GoldenNodeState } from '@/components/studio/node-golden'
import type { SubgraphProgress } from '@/components/GraphCanvas/subgraph-run'

export type SkillNodeStatus = 'idle' | 'running' | 'success' | 'error' | 'paused' | 'breakpoint'

/**
 * The wall clock of one node's run segment, in epoch milliseconds.
 *
 * Only the two ENDPOINTS live here, never an elapsed number: a card showing a
 * still-open segment has to keep counting, and a duration baked into node data
 * would force every node on the board to be rebuilt once a second to advance
 * one card's clock. `endedAtMs === null` is the whole signal that the segment
 * is open; the card ticks locally off `startedAtMs` until it closes.
 *
 * Derived by `deriveNodeRuntimes` (run-status-projection) from the same event
 * stream and the same run filter as the node's status, so the clock and the
 * light can never describe different runs.
 */
export interface NodeRuntime {
  startedAtMs: number
  endedAtMs: number | null
}

export interface SubagentRef {
  name: string
  path: string
  description: string
}

export interface SkillGraphNodeData extends Record<string, unknown> {
  skillId: string
  /** Absolute skill root that relative subgraph paths resolve against, when known. */
  workspaceRoot?: string | null
  /** Skill id used only for backend child-topology boundary resolution. */
  topologyOwnerSkillId?: string
  /** Canonical phase id inside its own skill. React Flow node ids may be namespaced. */
  phaseId?: string
  /**
   * This node's identity in a RUN: the dot-joined chain of enclosing subgraph
   * container phases plus its own phase name (`event_timeline.extract`). A
   * root-graph node's path is its phase name, so it reads identically to
   * `phaseId` there — the two diverge only inside an expanded subgraph, where
   * `phaseId` stays the child's local name and this becomes the key every run
   * projection files that node's status, failure and clock under (canvas F7).
   */
  phasePath: string
  /**
   * For a SUBGRAPH container: how far its own graph got in this run (canvas
   * F7 ④). Absent when the run never entered it, so the chip shows nothing
   * rather than `0/n`.
   */
  subgraphProgress?: SubgraphProgress
  label: string
  mode: string
  role?: string | null
  tools?: string[]
  filePath?: string
  status: SkillNodeStatus
  /**
   * N5 atom #1 (spec F1): one-line error summary for a failed/halted node, derived
   * from this phase's last failure event by the
   * same event→node-status derivation that drives the red light. Rendered in-place on
   * the node so the user sees *why* the run stopped without opening the Properties
   * panel. Only meaningful when `status === 'error'`.
   */
  errorMessage?: string
  /**
   * This node's run segment (start / end), when the active run reached it. The
   * card renders it as an elapsed time beside the status capsule — ticking
   * while the segment is open, frozen once it closes. Absent for a node the
   * run never entered, which is why "no duration" and "0s" stay distinct.
   */
  runtime?: NodeRuntime
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
  /** True only when GRAPH.md marks this phase ref with the explicit `output` flag. */
  isOutput?: boolean
  subgraphPath?: string | null
  subagents?: SubagentRef[]
  isExpanded?: boolean
  onToggleSubgraph?: () => void
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
  /** Full detail for a path-resolved child graph node, when this node is shown from an inline/drilled subgraph. */
  resolvedSkillDetail?: SkillDetail
  onAllowSequentialOverwrite?: (nodeId: string, fieldName: string, ancestorNodeId: string) => void
  onCancelSequentialOverwrite?: (nodeId: string, fieldName: string, ancestorNodeId: string) => void
}

export type SkillGraphNode = Node<SkillGraphNodeData, 'skill'>

export interface GlobalNodeData extends Record<string, unknown> {
  type: 'global-input' | 'global-output'
  schema: IoDeclaration
  skillId?: string
  workspaceRoot?: string | null
  /**
   * How this endpoint stands in the run (canvas F8). The endpoints are not
   * phases and execute nothing, so this comes from the run segments of the
   * edges at their end of the graph (`boundaryNodeStatus`) — the same status
   * vocabulary and the same capsule a phase node wears, which is what "IO
   * 端点与普通 node 统一" means concretely.
   */
  status?: SkillNodeStatus
  /** Compile/lint errors attributed to this global I/O boundary. */
  compileErrors?: CompileError[]
}

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
  /**
   * How the CONTAINER phase itself stands in the run (canvas F7 ⑤) — distinct
   * from `status`, which is whether the child topology could be fetched. A
   * running container's frame marches the same dashes as a running node card
   * and a running edge, so "this is executing" reads as one idea at all three
   * scales instead of three unrelated effects.
   */
  runStatus?: SkillNodeStatus
  childName?: string
  message?: string
  // Drill INTO the child graph (focus the canvas on this subgraph). Wired by the
  // host canvas onto the expanded board's "open canvas" button.
  onOpenCanvas?: (path: string, label: string) => void
}

export type GraphCanvasNode =
  | Node<SkillGraphNodeData, 'skill'>
  | Node<GlobalNodeData, 'globalInput'>
  | Node<GlobalNodeData, 'globalOutput'>
  | Node<SubgraphGroupNodeData, 'subgraphGroup'>
