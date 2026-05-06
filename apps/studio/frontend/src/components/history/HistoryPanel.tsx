import { RefreshCw } from 'lucide-react'
import { useState } from 'react'
import type { RunDetail } from '../../api/types'
import { useRunHistory } from '../../hooks/useRunHistory'
import { errorMessage } from '../../utils/errors'
import type { ExportFormat } from '../../utils/reportTemplates'
import { renderRunReport, reportFileBase } from '../../utils/reportTemplates'
import { RunDetailDrawer } from './RunDetailDrawer'
import { RunHistoryRow } from './RunHistoryRow'

const PAGE_SIZE = 12

interface HistoryPanelProps {
  skillId: string | null
  onReplay: (detail: RunDetail) => void
  onCompare: (runId: string) => void
  pushToast: (message: string, kind?: 'info' | 'success' | 'error') => void
}

export function HistoryPanel({ skillId, onReplay, onCompare, pushToast }: HistoryPanelProps) {
  const history = useRunHistory(skillId)
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)
  const [detail, setDetail] = useState<RunDetail | null>(null)
  const [page, setPage] = useState(0)

  const pageCount = Math.max(1, Math.ceil(history.runs.length / PAGE_SIZE))
  const visibleRuns = history.runs.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)

  const selectRun = async (runId: string) => {
    setSelectedRunId(runId)
    try {
      const nextDetail = await history.fetchRunDetail(runId)
      setDetail(nextDetail)
    } catch (error) {
      pushToast(errorMessage(error), 'error')
    }
  }

  const deleteRun = async (runId: string) => {
    try {
      await history.deleteRun(runId)
      if (selectedRunId === runId) {
        setSelectedRunId(null)
        setDetail(null)
      }
      pushToast('Run deleted', 'success')
    } catch (error) {
      pushToast(errorMessage(error), 'error')
    }
  }

  const replayRun = async (runId: string) => {
    try {
      const nextDetail = detail?.metadata.run_id === runId ? detail : await history.fetchRunDetail(runId)
      if (nextDetail) {
        onReplay(nextDetail)
      }
    } catch (error) {
      pushToast(errorMessage(error), 'error')
    }
  }

  const exportRun = async (runId: string, format: ExportFormat): Promise<string> => {
    if (!skillId) {
      throw new Error('Select a skill before exporting.')
    }
    const nextDetail = detail?.metadata.run_id === runId ? detail : await history.fetchRunDetail(runId)
    if (!nextDetail) {
      throw new Error(`Run not found: ${runId}`)
    }
    return renderRunReport({ skillId, run: nextDetail }, format)
  }

  return (
    <div className="relative flex h-full flex-col bg-slate-50 dark:bg-slate-950">
      <div className="flex shrink-0 items-center justify-between border-b border-slate-200 px-4 py-3 dark:border-slate-800">
        <div>
          <h3 className="font-bold text-slate-800 dark:text-slate-100">Run History</h3>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            {history.total} runs tracked for this skill
          </p>
        </div>
        <button
          type="button"
          onClick={() => void history.refresh()}
          className="rounded-md p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-800 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100"
          title="Refresh history"
        >
          <RefreshCw className="h-4 w-4" />
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {history.error ? (
          <div className="m-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300">
            {errorMessage(history.error)}
          </div>
        ) : null}
        {history.isLoading ? (
          <div className="p-4 text-sm text-slate-500 dark:text-slate-400">Loading runs...</div>
        ) : null}
        {!history.isLoading && history.runs.length === 0 ? (
          <div className="flex h-full items-center justify-center p-8 text-center text-sm text-slate-500 dark:text-slate-400">
            No run history yet.
          </div>
        ) : null}
        {visibleRuns.length > 0 ? (
          <table className="w-full table-fixed">
            <thead className="sticky top-0 bg-slate-100 text-left text-xs uppercase text-slate-500 dark:bg-slate-900 dark:text-slate-400">
              <tr>
                <th className="w-24 px-3 py-2">Status</th>
                <th className="w-36 px-3 py-2">Run</th>
                <th className="px-3 py-2">Input</th>
                <th className="w-20 px-3 py-2">Tokens</th>
                <th className="w-36 px-3 py-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {visibleRuns.map((run) => (
                <RunHistoryRow
                  key={run.run_id}
                  run={run}
                  selected={selectedRunId === run.run_id}
                  filenameBase={reportFileBase(skillId, run.run_id)}
                  onSelect={(runId) => void selectRun(runId)}
                  onReplay={(runId) => void replayRun(runId)}
                  onCompare={onCompare}
                  onExport={(runId, format) => exportRun(runId, format)}
                  onDelete={(runId) => void deleteRun(runId)}
                />
              ))}
            </tbody>
          </table>
        ) : null}
      </div>

      <div className="flex shrink-0 items-center justify-between border-t border-slate-200 px-4 py-2 text-xs text-slate-500 dark:border-slate-800 dark:text-slate-400">
        <span>Page {page + 1} of {pageCount}</span>
        <div className="flex gap-2">
          <button
            type="button"
            disabled={page === 0}
            onClick={() => setPage((current) => Math.max(0, current - 1))}
            className="rounded border border-slate-300 px-2 py-1 disabled:opacity-50 dark:border-slate-700"
          >
            Prev
          </button>
          <button
            type="button"
            disabled={page >= pageCount - 1}
            onClick={() => setPage((current) => Math.min(pageCount - 1, current + 1))}
            className="rounded border border-slate-300 px-2 py-1 disabled:opacity-50 dark:border-slate-700"
          >
            Next
          </button>
        </div>
      </div>

      <RunDetailDrawer
        detail={detail}
        open={detail !== null}
        onClose={() => setDetail(null)}
        onReplay={async (runId) => {
          const nextDetail = detail?.metadata.run_id === runId ? detail : await history.fetchRunDetail(runId)
          if (nextDetail) {
            onReplay(nextDetail)
          }
        }}
        onCompare={onCompare}
        skillId={skillId}
      />
    </div>
  )
}
