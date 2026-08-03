import type { LintError } from '../api/types'

export type ActiveTab = 'code' | 'trace' | 'diff' | 'history' | 'batch' | 'terminal' | 'settings'
export type LintStatus = 'idle' | 'checking' | 'passed' | 'failed'
export type RunStatus = 'idle' | 'running' | 'success' | 'error'
export type ToastKind = 'info' | 'success' | 'error'

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
