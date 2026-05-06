import { GitCompareArrows, RefreshCw, Trash2 } from 'lucide-react'
import type { RunMetadata } from '../../api/types'
import { runTokenTotal } from '../../hooks/useRunHistory'

interface RunHistoryRowProps {
  run: RunMetadata
  selected: boolean
  onSelect: (runId: string) => void
  onReplay: (runId: string) => void
  onCompare: (runId: string) => void
  onDelete: (runId: string) => void
}

function statusClass(status: RunMetadata['status']): string {
  if (status === 'success') {
    return 'bg-green-100 text-green-700 dark:bg-green-950/50 dark:text-green-300'
  }
  if (status === 'failed') {
    return 'bg-red-100 text-red-700 dark:bg-red-950/50 dark:text-red-300'
  }
  return 'bg-sky-100 text-sky-700 dark:bg-sky-950/50 dark:text-sky-300'
}

function shortRunId(runId: string): string {
  return runId.length > 18 ? `${runId.slice(0, 18)}...` : runId
}

function relativeTime(value: string): string {
  const timestamp = new Date(value).getTime()
  if (Number.isNaN(timestamp)) {
    return value
  }
  const seconds = Math.max(0, Math.floor((Date.now() - timestamp) / 1000))
  if (seconds < 60) {
    return `${seconds}s ago`
  }
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) {
    return `${minutes}m ago`
  }
  const hours = Math.floor(minutes / 60)
  if (hours < 24) {
    return `${hours}h ago`
  }
  return `${Math.floor(hours / 24)}d ago`
}

export function RunHistoryRow({
  run,
  selected,
  onSelect,
  onReplay,
  onCompare,
  onDelete,
}: RunHistoryRowProps) {
  const totalTokens = runTokenTotal(run)

  return (
    <tr
      className={`cursor-pointer border-b border-slate-200 text-sm hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-900 ${
        selected ? 'bg-sky-50 dark:bg-sky-950/30' : ''
      }`}
      onClick={() => onSelect(run.run_id)}
    >
      <td className="px-3 py-2">
        <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${statusClass(run.status)}`}>
          {run.status}
        </span>
      </td>
      <td className="px-3 py-2">
        <div className="font-mono text-xs font-semibold text-slate-700 dark:text-slate-200">
          {shortRunId(run.run_id)}
        </div>
        <div className="text-xs text-slate-500 dark:text-slate-400">{relativeTime(run.started_at)}</div>
      </td>
      <td className="max-w-[13rem] truncate px-3 py-2 text-xs text-slate-600 dark:text-slate-300">
        {run.input_summary ?? 'No input summary'}
      </td>
      <td className="px-3 py-2 text-xs text-slate-600 dark:text-slate-300">
        {totalTokens === null ? 'n/a' : totalTokens.toLocaleString()}
      </td>
      <td className="px-3 py-2">
        <div className="flex items-center justify-end gap-1">
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation()
              onReplay(run.run_id)
            }}
            className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-800 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100"
            title="Replay run"
          >
            <RefreshCw className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation()
              onCompare(run.run_id)
            }}
            className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-800 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100"
            title="Compare run"
          >
            <GitCompareArrows className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation()
              onDelete(run.run_id)
            }}
            className="rounded-md p-1.5 text-red-500 hover:bg-red-50 hover:text-red-700 dark:hover:bg-red-950/40"
            title="Delete run"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </td>
    </tr>
  )
}
