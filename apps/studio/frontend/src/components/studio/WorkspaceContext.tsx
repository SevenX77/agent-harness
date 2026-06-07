import { createContext, useContext } from 'react'
import type { FileMeta } from './file-types'

export type EditorSide = 'left' | 'right'
export type WorkspacePanelKind = 'assets' | 'input' | 'timeline' | 'properties' | 'local-history' | null
export interface EdgeContextJson {
  inputs?: unknown
  phase_outputs?: Record<string, unknown>
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
  splitMode: boolean
  onFileOpen: (fileOrPath: FileMeta | string, side?: EditorSide) => void
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
