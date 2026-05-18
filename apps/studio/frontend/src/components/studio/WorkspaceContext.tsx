import { createContext, useContext } from 'react'
import type { FileMeta } from './file-types'

export type EditorSide = 'left' | 'right'

export interface OpenFile extends FileMeta {
  skillId: string
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

export interface NodePropertyField {
  name: string
  type?: string | null
}

export interface SelectedNodeForProperties {
  id: string
  label: string
  kind: 'phase' | 'input' | 'output'
  modeLabel?: string
  dependsOn?: string[]
  role?: string | null
  tools?: string[]
  filePath?: string
  fields?: NodePropertyField[]
}

export interface WorkspaceContextValue {
  currentSkillId: string | null
  navStack: string[]
  activeFiles: { left?: string, right?: string }
  activeFileDetails: Partial<Record<EditorSide, OpenFile>>
  splitMode: boolean
  propertiesPanelOpen: boolean
  selectedNodeForProperties: SelectedNodeForProperties | null
  onFileOpen: (fileOrPath: FileMeta | string, side?: EditorSide) => void
  openSplitEditor: () => void
  openProperties: (node: SelectedNodeForProperties) => void
  closeProperties: () => void
  closeFile: (side: EditorSide) => void
  updateFileContent: (side: EditorSide, content: string) => void
  markFileSaved: (side: EditorSide, hash: string) => void
  setFileInFlight: (side: EditorSide, inFlight: boolean) => void
  onSaveConflict: (conflict: SaveConflict) => void
  reloadOpenFile: (side: EditorSide) => Promise<void>
  pushNavSkill: (skillId: string) => void
  popNavTo: (index: number) => void
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
