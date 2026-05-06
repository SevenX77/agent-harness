import { AlertTriangle, X } from 'lucide-react'
import type { StoredDraft } from '../../hooks/useDraftPersist'

interface DraftRestoreModalProps {
  open: boolean
  skillId: string | null
  draft: StoredDraft | null
  baseHash: string
  onRestore: () => void
  onDiscard: () => void
  onCancel: () => void
}

function formatTime(timestamp: number): string {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(timestamp))
}

function lineCount(value: string): number {
  return value.split('\n').length
}

export function DraftRestoreModal({
  open,
  skillId,
  draft,
  baseHash,
  onRestore,
  onDiscard,
  onCancel,
}: DraftRestoreModalProps) {
  if (!open || !draft || !skillId) {
    return null
  }

  const baseChanged = draft.baseHash !== baseHash

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-6 dark:bg-black/80">
      <div className="w-full max-w-lg rounded-md border border-gray-200 bg-white shadow-2xl dark:border-slate-800 dark:bg-slate-900">
        <div className="flex items-start justify-between gap-4 border-b border-gray-200 px-5 py-4 dark:border-slate-800">
          <div className="flex items-start gap-3">
            <span className="mt-0.5 rounded bg-amber-100 p-2 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300">
              <AlertTriangle className="h-5 w-5" />
            </span>
            <div>
              <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100">Unsaved draft found</h2>
              <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                Restore the local draft for {skillId}, or discard it and keep the saved file.
              </p>
            </div>
          </div>
          <button type="button" onClick={onCancel} className="rounded p-1 text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-slate-800">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-4 p-5">
          <div className="grid gap-3 text-sm md:grid-cols-2">
            <div className="rounded-md border border-gray-200 bg-gray-50 p-3 dark:border-slate-800 dark:bg-slate-950">
              <div className="text-xs font-semibold uppercase text-gray-400 dark:text-gray-500">Saved</div>
              <div className="mt-1 text-gray-700 dark:text-gray-300">{formatTime(draft.timestamp)}</div>
            </div>
            <div className="rounded-md border border-gray-200 bg-gray-50 p-3 dark:border-slate-800 dark:bg-slate-950">
              <div className="text-xs font-semibold uppercase text-gray-400 dark:text-gray-500">Draft Size</div>
              <div className="mt-1 text-gray-700 dark:text-gray-300">{lineCount(draft.content)} lines</div>
            </div>
          </div>

          {baseChanged ? (
            <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200">
              The saved SKILL.md has changed since this draft was recorded. Review carefully after restoring.
            </div>
          ) : null}
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-gray-200 px-5 py-4 dark:border-slate-800">
          <button
            type="button"
            onClick={onDiscard}
            className="rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 dark:border-slate-700 dark:text-gray-300 dark:hover:bg-slate-800"
          >
            Discard
          </button>
          <button
            type="button"
            onClick={onCancel}
            className="rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 dark:border-slate-700 dark:text-gray-300 dark:hover:bg-slate-800"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onRestore}
            className="rounded-md bg-sky-600 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-700"
          >
            Restore
          </button>
        </div>
      </div>
    </div>
  )
}

