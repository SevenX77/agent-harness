import { createContext, useContext } from 'react'
import type { EventEnvelope, LintResult } from '@/api/types'
import type { FileOpenInput, FileMeta } from './file-types'

export type EditorSide = 'left' | 'right'
export type WorkspacePanelKind = 'assets' | 'input' | 'timeline' | 'properties' | 'local-history' | null

// One node-to-node micro operation recorded between the upstream phase end and
// the downstream phase start. The engine already emits each of these on the run
// event stream (blackboard_reduce / input_dispatch / input_file_injected /
// artifact_saved); EdgeContextView renders the ordered list as the dot's
// "what happened across this transition" operation log.
export type EdgeOperation =
  | { kind: 'reduce'; reducer: string; changed_keys: string[] }
  | { kind: 'dispatch'; dispatched_keys: string[]; changed_keys: string[] }
  | { kind: 'inject'; file_ref: string; target_field: string }
  | { kind: 'persist'; name: string; path: string; size_bytes: number | null }

export interface EdgeContextJson {
  inputs?: unknown
  phase_outputs?: Record<string, unknown>
  operations?: EdgeOperation[]
  [key: string]: unknown
}

export interface SelectedEdge {
  id: string
  source: string
  target: string
  contextJson?: EdgeContextJson
}

export interface OpenFile extends FileMeta {
  skillId: string
  workspaceRoot?: string | null
  hash: string | null
  savedContent: string
  dirty?: boolean
  title?: string
  saveEnabled?: boolean
}

export interface SaveConflict {
  skillId: string
  path: string
  side: EditorSide
  localContent: string
  remoteContent: string
  remoteHash: string | null
}

export interface WorkspaceContextValue {
  currentSkillId: string | null
  navStack: string[]
  activeFiles: { left?: string, right?: string }
  activeFileDetails: Partial<Record<EditorSide, OpenFile>>
  editorLintResult?: LintResult | null
  splitMode: boolean
  onFileOpen: (fileOrPath: FileOpenInput, side?: EditorSide) => void
  /** Reverse of node→file reveal: select the canvas node a node-definition file
   * belongs to. No-op for files that are not a phase node file or that belong to
   * a graph not on the root canvas. */
  onRevealNodeForFile?: (file: FileMeta) => void
  /** Reveal a node inside a subgraph's inline canvas topology: expand every
   * subgraph ancestor and select the leaf child phase node. `phaseChain` is the
   * root→leaf chain of phase ids (e.g. ["timeline", "extraction", "review"]).
   * Driven by clicking a subgraph child file in the Assets trees. */
  onRevealSubgraphChildNode?: (phaseChain: string[]) => void
  /** Expand a subgraph's own inline canvas topology and deselect any node.
   * `phaseChain` is the root→here chain of phase ids identifying the subgraph.
   * Driven by clicking the subgraph's GRAPH.md in the Assets trees. */
  onRevealSubgraphGraph?: (phaseChain: string[]) => void
  openSplitEditor: () => void
  closeFile: (side: EditorSide) => void
  updateFileContent: (side: EditorSide, content: string) => void
  markFileSaved: (side: EditorSide, hash: string) => void
  setFileInFlight: (side: EditorSide, inFlight: boolean) => void
  onSaveConflict: (conflict: SaveConflict) => void
  reloadOpenFile: (side: EditorSide) => Promise<void>
  pushNavSkill: (skillId: string) => void
  popNavTo: (index: number) => void
  selectedEdge?: SelectedEdge | null
  setSelectedEdge?: (edge: SelectedEdge | null) => void
  onPanelChange?: (panel: WorkspacePanelKind) => void
  // Unfiltered trace events for the active run. The edge dot reads these to
  // resolve the real blackboard snapshot dispatched across the clicked edge.
  traceEvents?: EventEnvelope[]
}

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null)

export const WorkspaceProvider = WorkspaceContext.Provider

export function useWorkspaceContext(): WorkspaceContextValue {
  const context = useContext(WorkspaceContext)
  if (!context) {
    throw new Error('WorkspaceContext is missing')
  }
  return context
}

export function useOptionalWorkspaceContext(): WorkspaceContextValue | null {
  return useContext(WorkspaceContext)
}
