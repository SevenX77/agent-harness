import { CheckCircle, Save } from 'lucide-react'
import { useWorkspaceStore } from '../stores/workspace'

interface DirtyBarProps {
  onSave: () => void
}

export function DirtyBar({ onSave }: DirtyBarProps) {
  const isDirty = useWorkspaceStore((state) => state.isDirty)
  const dirty = useWorkspaceStore((state) => state.dirty)
  const dirtyCount = Object.values(dirty).filter(Boolean).length

  if (!isDirty) {
    return (
      <div className="flex h-8 shrink-0 items-center justify-between border-b border-gray-200 bg-gray-50 px-6 text-xs text-gray-500 dark:border-slate-800 dark:bg-slate-950 dark:text-gray-400">
        <span className="flex items-center gap-2">
          <CheckCircle className="h-3.5 w-3.5 text-emerald-500" />
          All changes saved
        </span>
      </div>
    )
  }

  return (
    <div className="flex h-8 shrink-0 items-center justify-between border-b border-amber-200 bg-amber-50 px-6 text-xs text-amber-800 dark:border-amber-900/50 dark:bg-amber-950/40 dark:text-amber-200">
      <span>{dirtyCount} unsaved file{dirtyCount === 1 ? '' : 's'}</span>
      <button
        type="button"
        onClick={onSave}
        className="flex items-center gap-1 rounded border border-amber-300 bg-white px-2 py-0.5 font-medium text-amber-800 hover:bg-amber-100 dark:border-amber-800 dark:bg-slate-900 dark:text-amber-200 dark:hover:bg-amber-950"
      >
        <Save className="h-3 w-3" />
        Save All
      </button>
    </div>
  )
}
