import { GitCompareArrows, RefreshCw, X } from 'lucide-react'
import type { RunDetail } from '../../api/types'

interface RunDetailDrawerProps {
  detail: RunDetail | null
  open: boolean
  onClose: () => void
  onReplay: (runId: string) => void
  onCompare: (runId: string) => void
}

function jsonBlock(value: unknown): string {
  return JSON.stringify(value ?? {}, null, 2)
}

export function RunDetailDrawer({
  detail,
  open,
  onClose,
  onReplay,
  onCompare,
}: RunDetailDrawerProps) {
  if (!open || !detail) {
    return null
  }

  return (
    <div className="absolute inset-0 z-20 bg-slate-950/20 dark:bg-slate-950/60">
      <aside className="absolute right-0 top-0 flex h-full w-[88%] flex-col border-l border-slate-200 bg-white shadow-xl dark:border-slate-800 dark:bg-slate-950">
        <div className="flex shrink-0 items-start justify-between border-b border-slate-200 px-4 py-3 dark:border-slate-800">
          <div className="min-w-0">
            <h3 className="truncate font-mono text-sm font-bold text-slate-800 dark:text-slate-100">
              {detail.metadata.run_id}
            </h3>
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
              {detail.metadata.status} / {new Date(detail.metadata.started_at).toLocaleString()}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-800 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100"
            title="Close run detail"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex shrink-0 items-center gap-2 border-b border-slate-200 px-4 py-3 dark:border-slate-800">
          <button
            type="button"
            onClick={() => onReplay(detail.metadata.run_id)}
            className="inline-flex items-center gap-2 rounded-md bg-sky-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-sky-700"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Replay
          </button>
          <button
            type="button"
            onClick={() => onCompare(detail.metadata.run_id)}
            className="inline-flex items-center gap-2 rounded-md border border-slate-300 px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            <GitCompareArrows className="h-3.5 w-3.5" />
            Compare
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          <div className="grid grid-cols-2 gap-3">
            <section>
              <h4 className="mb-2 text-xs font-bold uppercase text-slate-500 dark:text-slate-400">
                Input
              </h4>
              <pre className="max-h-80 overflow-auto rounded-md bg-slate-950 p-3 text-xs text-slate-100">
                {jsonBlock(detail.input_data)}
              </pre>
            </section>
            <section>
              <h4 className="mb-2 text-xs font-bold uppercase text-slate-500 dark:text-slate-400">
                Output
              </h4>
              <pre className="max-h-80 overflow-auto rounded-md bg-slate-950 p-3 text-xs text-slate-100">
                {jsonBlock(detail.final_context)}
              </pre>
            </section>
          </div>

          <section className="mt-4">
            <h4 className="mb-2 text-xs font-bold uppercase text-slate-500 dark:text-slate-400">
              Metrics
            </h4>
            <pre className="max-h-48 overflow-auto rounded-md bg-slate-100 p-3 text-xs text-slate-700 dark:bg-slate-900 dark:text-slate-200">
              {jsonBlock(detail.metadata.metrics)}
            </pre>
          </section>
        </div>
      </aside>
    </div>
  )
}
