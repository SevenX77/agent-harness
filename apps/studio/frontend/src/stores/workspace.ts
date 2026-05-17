import { create } from 'zustand'

type FileMap = Record<string, string>
type DirtyMap = Record<string, boolean>

interface WorkspaceState {
  files: FileMap
  activeFile: string | null
  dirty: DirtyMap
  isDirty: boolean
  setFiles: (files: FileMap) => void
  setActive: (path: string | null) => void
  updateFile: (path: string, content: string) => void
  markSaved: () => void
}

function firstFile(files: FileMap): string | null {
  return Object.keys(files).sort()[0] ?? null
}

function hasDirtyFile(dirty: DirtyMap): boolean {
  return Object.values(dirty).some(Boolean)
}

export const useWorkspaceStore = create<WorkspaceState>((set) => ({
  files: {},
  activeFile: null,
  dirty: {},
  isDirty: false,
  setFiles: (files) => {
    set({
      files,
      activeFile: firstFile(files),
      dirty: {},
      isDirty: false,
    })
  },
  setActive: (path) => {
    set((state) => ({
      activeFile: path && Object.prototype.hasOwnProperty.call(state.files, path) ? path : null,
    }))
  },
  updateFile: (path, content) => {
    set((state) => {
      const files = { ...state.files, [path]: content }
      const dirty = { ...state.dirty, [path]: true }
      return {
        files,
        activeFile: state.activeFile ?? path,
        dirty,
        isDirty: hasDirtyFile(dirty),
      }
    })
  },
  markSaved: () => {
    set({
      dirty: {},
      isDirty: false,
    })
  },
}))
