import { RotateCcw, Save, X } from 'lucide-react'
import { useEffect } from 'react'
import type { PhaseFormData } from '../../hooks/usePhaseForm'
import { phaseFormErrors } from '../../hooks/usePhaseForm'
import { PhaseFormBody } from './PhaseFormBody'

interface PhaseDrawerProps {
  open: boolean
  phaseId: string | null
  data: PhaseFormData
  availableTools: string[]
  dirty: boolean
  onChange: <Key extends keyof PhaseFormData>(field: Key, value: PhaseFormData[Key]) => void
  onApply: () => void
  onReset: () => void
  onClose: () => void
}

export function PhaseDrawer({
  open,
  phaseId,
  data,
  availableTools,
  dirty,
  onChange,
  onApply,
  onReset,
  onClose,
}: PhaseDrawerProps) {
  const errors = phaseFormErrors(data)
  const canApply = Object.keys(errors).length === 0

  useEffect(() => {
    if (!open) {
      return
    }
    const handler = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose, open])

  if (!open) {
    return null
  }

  return (
    <div className="pointer-events-none fixed inset-0 z-40">
      <aside className="pointer-events-auto absolute right-0 top-0 flex h-full w-[min(42rem,44vw)] min-w-[32rem] flex-col border-l border-slate-200 bg-slate-50 shadow-2xl dark:border-slate-800 dark:bg-slate-950">
        <div className="flex shrink-0 items-start justify-between border-b border-slate-200 bg-white px-5 py-4 dark:border-slate-800 dark:bg-slate-900">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-sky-600 dark:text-sky-400">
              Phase form
            </p>
            <h2 className="mt-1 text-lg font-bold text-slate-900 dark:text-slate-50">
              {phaseId ?? 'Unknown phase'}
            </h2>
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
              Changes apply only after pressing Apply.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-800 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100"
            title="Close phase form"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto p-5">
          <PhaseFormBody data={data} availableTools={availableTools} onChange={onChange} />
        </div>

        <div className="flex shrink-0 items-center justify-between border-t border-slate-200 bg-white px-5 py-4 dark:border-slate-800 dark:bg-slate-900">
          <span className={`text-xs font-medium ${dirty ? 'text-amber-600 dark:text-amber-300' : 'text-slate-500 dark:text-slate-400'}`}>
            {dirty ? 'Unsaved form edits' : 'Synced with SKILL.md'}
          </span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onReset}
              className="inline-flex items-center gap-2 rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
            >
              <RotateCcw className="h-4 w-4" />
              Reset
            </button>
            <button
              type="button"
              disabled={!canApply}
              onClick={onApply}
              className="inline-flex items-center gap-2 rounded-md bg-sky-600 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-700 disabled:cursor-not-allowed disabled:bg-sky-300 dark:disabled:bg-sky-900"
            >
              <Save className="h-4 w-4" />
              Apply
            </button>
          </div>
        </div>
      </aside>
    </div>
  )
}
