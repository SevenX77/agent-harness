import type { BatchRunStatus } from '../../api/types'

interface BatchSummaryProps {
  status: BatchRunStatus | null
  onOpenRun: (runId: string) => void
}

function progressPercent(status: BatchRunStatus): number {
  return status.total === 0 ? 0 : Math.round((status.completed / status.total) * 100)
}

function statusClass(status: string): string {
  if (status === 'success') {
    return 'text-green-600 dark:text-green-400'
  }
  if (status === 'failed') {
    return 'text-red-600 dark:text-red-400'
  }
  return 'text-sky-600 dark:text-sky-400'
}

export function BatchSummary({ status, onOpenRun }: BatchSummaryProps) {
  if (!status) {
    return (
      <section className="flex flex-1 items-center justify-center p-6 text-center text-sm text-slate-500 dark:text-slate-400">
        Run a batch to see progress and per-case results.
      </section>
    )
  }

  const percent = progressPercent(status)

  return (
    <section className="min-h-0 flex-1 overflow-y-auto bg-slate-50 p-4 dark:bg-slate-950">
      <div className="mb-4 rounded-md border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h3 className="font-bold text-slate-800 dark:text-slate-100">{status.batch_id}</h3>
            <p className={`text-sm font-semibold ${statusClass(status.status)}`}>{status.status}</p>
          </div>
          <div className="text-right text-sm text-slate-500 dark:text-slate-400">
            {status.completed}/{status.total} complete
          </div>
        </div>
        <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800">
          <div
            className="h-full rounded-full bg-sky-500 transition-all"
            style={{ width: `${percent}%` }}
          />
        </div>
      </div>

      <div className="overflow-hidden rounded-md border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
        <table className="w-full table-fixed">
          <thead className="bg-slate-100 text-left text-xs uppercase text-slate-500 dark:bg-slate-800 dark:text-slate-400">
            <tr>
              <th className="px-3 py-2">Input</th>
              <th className="w-24 px-3 py-2">Status</th>
              <th className="w-24 px-3 py-2">Tokens</th>
              <th className="w-24 px-3 py-2 text-right">Trace</th>
            </tr>
          </thead>
          <tbody>
            {status.items.map((item) => (
              <tr key={item.run_id} className="border-t border-slate-200 text-sm dark:border-slate-800">
                <td className="truncate px-3 py-2 font-mono text-xs text-slate-700 dark:text-slate-200">
                  {item.input_id}
                </td>
                <td className={`px-3 py-2 text-xs font-semibold ${statusClass(item.status)}`}>
                  {item.status}
                </td>
                <td className="px-3 py-2 text-xs text-slate-500 dark:text-slate-400">
                  {item.metrics?.total_tokens?.toLocaleString() ?? 'n/a'}
                </td>
                <td className="px-3 py-2 text-right">
                  <button
                    type="button"
                    onClick={() => onOpenRun(item.run_id)}
                    className="rounded-md border border-slate-300 px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
                  >
                    Open
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
