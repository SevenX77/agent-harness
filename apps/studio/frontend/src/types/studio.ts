import type { Edge, Node } from 'reactflow'
import type { StudioNodeData } from '../CustomNodes'
import type { LintError } from '../api/types'

export type ActiveTab = 'code' | 'trace' | 'diff' | 'history' | 'batch' | 'terminal' | 'settings'
export type LintStatus = 'idle' | 'checking' | 'passed' | 'failed'
export type RunStatus = 'idle' | 'running' | 'success' | 'error'
export type ToastKind = 'info' | 'success' | 'error'
export type TerminalStatus = 'idle' | 'connecting' | 'open' | 'closed' | 'error'

export interface Toast {
  id: string
  kind: ToastKind
  message: string
}

export interface EditorDraft {
  skillId: string | null
  code: string
  dirty: boolean
}

export interface LintOverride {
  skillId: string
  status: LintStatus
  errors: LintError[]
}

export interface GraphBuildResult {
  nodes: Node<StudioNodeData>[]
  edges: Edge[]
}

export interface VisualPhase {
  id: string
  name: string
  mode: string
  src: string | null
  role: string | null
  dependsOn: string[]
  subgraph: string | null
}

export type ApiKeyName = 'openai' | 'anthropic' | 'gemini'

export type ApiKeys = Record<ApiKeyName, string>
