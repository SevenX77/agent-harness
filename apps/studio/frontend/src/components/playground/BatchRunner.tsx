import { ListChecks, RefreshCw, Rocket } from 'lucide-react'
import type { TestInputMetadata } from '../../api/types'

interface BatchRunnerProps {
  inputs: TestInputMetadata[]
  selectedIds: string[]
  loading: boolean
  running: boolean
  error: string | null
  onToggleInput: (inputId: string) => void
  onRunBatch: () => void
  onRefresh: () => void
}

function formatBytes(value: number): string {
  if (value < 1024) {
    return `${value} B`
  }
  return `${(value / 1024).toFixed(1)} KB`
}

export function BatchRunner({
  inputs,
  selectedIds,
  loading,
  running,
  error,
  onToggleInput,
  onRunBatch,
  onRefresh,
}: BatchRunnerProps) {
  return (
    <section className="border-b border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
      <div className="flex items-center justify-between gap-3 px-4 py-3">
        <div>
          <h3 className="flex items-center gap-2 font-bold text-slate-800 dark:text-slate-100">
            <ListChecks className="h-4 w-4" />
            Batch Runner
          </h3>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            Select test inputs and run them as one batch.
          </p>
        </div>
        <button
          type="button"
          onClick={onRefresh}
          className="rounded-md p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-800 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100"
          title="Refresh test inputs"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {error ? (
        <div className="mx-4 mb-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300">
          {error}
        </div>
      ) : null}

      <div className="max-h-72 overflow-y-auto px-4 pb-3">
        {inputs.length === 0 ? (
          <div className="rounded-md border border-dashed border-slate-300 p-4 text-center text-sm text-slate-500 dark:border-slate-700 dark:text-slate-400">
            {loading ? 'Loading test inputs...' : 'No JSON test inputs found.'}
          </div>
        ) : null}
        <div className="space-y-2">
          {inputs.map((input) => (
            <label
              key={input.id}
              className="flex cursor-pointer items-start gap-3 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 hover:bg-slate-100 dark:border-slate-800 dark:bg-slate-950 dark:hover:bg-slate-900"
            >
              <input
                type="checkbox"
                checked={selectedIds.includes(input.id)}
                onChange={() => onToggleInput(input.id)}
                className="mt-1 h-4 w-4 rounded border-slate-300 text-sky-600 focus:ring-sky-500"
              />
              <span className="min-w-0 flex-1">
                <span className="flex items-center justify-between gap-2">
                  <span className="truncate text-sm font-semibold text-slate-800 dark:text-slate-100">
                    {input.name}
                  </span>
                  <span className="shrink-0 text-xs text-slate-500 dark:text-slate-400">
                    {formatBytes(input.size_bytes)}
                  </span>
                </span>
                <span className="mt-1 block truncate font-mono text-xs text-slate-500 dark:text-slate-400">
                  {input.content_preview}
                </span>
              </span>
            </label>
          ))}
        </div>
      </div>

      <div className="flex items-center justify-between border-t border-slate-200 px-4 py-3 dark:border-slate-800">
        <span className="text-xs font-medium text-slate-500 dark:text-slate-400">
          {selectedIds.length} selected
        </span>
        <button
          type="button"
          disabled={selectedIds.length === 0 || running}
          onClick={onRunBatch}
          className="inline-flex items-center gap-2 rounded-md bg-sky-600 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-700 disabled:cursor-not-allowed disabled:bg-sky-300 dark:disabled:bg-sky-900"
        >
          <Rocket className="h-4 w-4" />
          {running ? 'Running...' : 'Run Batch'}
        </button>
      </div>
    </section>
  )
}
