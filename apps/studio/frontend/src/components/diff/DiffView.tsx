import { BadgeCheck, GitCompareArrows, RefreshCw } from 'lucide-react'
import { useEffect, useMemo, useState, type ReactElement } from 'react'
import type { CompareResult, FieldDifference } from '../../api/types'
import { renderCompareReport, reportFileBase } from '../../utils/reportTemplates'
import { ExportButton } from '../export/ExportButton'
import { DiffField } from './DiffField'
import { DiffScore } from './DiffScore'

interface DiffViewProps {
  result: CompareResult | null
  skillId: string | null
  runId?: string | null
  loading: boolean
  error: string | null
  canCompare: boolean
  canPromote: boolean
  onCompare: () => void
  onPromote: () => void
}

function visibleFields(result: CompareResult | null): FieldDifference[] {
  if (!result) {
    return []
  }
  const fields = result.differences.filter((field) => field.field_path !== 'output')
  return fields.length > 0 ? fields : result.differences
}

interface NodeGroup {
  nodeId: string
  verdict: 'pass' | 'fail'
  score: number
  fields: FieldDifference[]
}

// D7 / golden-per-agent-node: organize the diff by node so each agent node
// carries its own pass/fail verdict and score, with field differences nested.
function buildNodeGroups(result: CompareResult | null): NodeGroup[] {
  if (!result?.node_results?.length) {
    return []
  }
  return result.node_results.map((node) => ({
    nodeId: node.node_id,
    verdict: node.verdict,
    score: node.score,
    fields: node.differences.filter((field) => field.field_path !== 'output'),
  }))
}

function fieldButton(
  field: FieldDifference,
  selectedField: FieldDifference | null,
  setSelectedPath: (path: string) => void,
): ReactElement {
  const isSelected = selectedField?.field_path === field.field_path
  return (
    <button
      key={field.field_path}
      type="button"
      onClick={() => setSelectedPath(field.field_path)}
      className={`block w-full rounded-md border px-2 py-2 text-start text-xs ${
        isSelected
          ? 'border-sky-400 bg-sky-50 text-sky-800 dark:border-sky-500 dark:bg-sky-950/40 dark:text-sky-200'
          : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-100 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800'
      }`}
    >
      <div className="truncate font-mono font-semibold">{field.field_path}</div>
      <div className="mt-1 flex items-center justify-between">
        <span>{field.type}</span>
        <span>{Math.round(field.score * 100)}%</span>
      </div>
    </button>
  )
}

export function DiffView({
  result,
  skillId,
  runId = null,
  loading,
  error,
  canCompare,
  canPromote,
  onCompare,
  onPromote,
}: DiffViewProps) {
  const fields = useMemo(() => visibleFields(result), [result])
  const nodeGroups = useMemo(() => buildNodeGroups(result), [result])
  const allFields = useMemo(
    () => (nodeGroups.length > 0 ? nodeGroups.flatMap((group) => group.fields) : fields),
    [nodeGroups, fields],
  )
  const [selectedPath, setSelectedPath] = useState<string | null>(null)
  const selectedField = allFields.find((field) => field.field_path === selectedPath) ?? allFields[0] ?? null

  useEffect(() => {
    setSelectedPath(allFields[0]?.field_path ?? null)
  }, [allFields])

  if (!result && !loading && !error) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 bg-slate-50 p-6 text-center dark:bg-slate-950">
        <GitCompareArrows className="h-9 w-9 text-slate-400" />
        <div>
          <h3 className="font-bold text-slate-800 dark:text-slate-100">Golden Diff</h3>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            Compare the latest run output against the active golden baseline.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            disabled={!canCompare}
            onClick={onCompare}
            className="flex items-center gap-2 rounded-md bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-700 disabled:cursor-not-allowed disabled:bg-sky-300 dark:disabled:bg-sky-900"
          >
            <GitCompareArrows className="h-4 w-4" />
            Compare to Golden
          </button>
          <button
            type="button"
            disabled={!canPromote}
            onClick={onPromote}
            className="flex items-center gap-2 rounded-md border border-amber-300 px-3 py-1.5 text-sm font-medium text-amber-700 hover:bg-amber-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-amber-800 dark:text-amber-300 dark:hover:bg-amber-950/40"
          >
            <BadgeCheck className="h-4 w-4" />
            Promote to Golden
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col bg-slate-50 dark:bg-slate-950">
      <div className="flex shrink-0 items-center justify-between border-b border-slate-200 px-4 py-3 dark:border-slate-800">
        <div className="flex items-center gap-3">
          <DiffScore score={result?.total_score ?? 0} />
          <div>
            <h3 className="font-bold text-slate-800 dark:text-slate-100">Golden Diff</h3>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              {result ? `Against ${result.golden_run_id}` : 'No comparison loaded'}
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          <ExportButton
            label="Export Compare"
            title="Export comparison report"
            disabled={!result || !skillId}
            filenameBase={reportFileBase(skillId, runId ?? 'compare', result?.golden_run_id)}
            buildContent={(format) => {
              if (!result || !skillId) {
                throw new Error('Run a comparison before exporting.')
              }
              return renderCompareReport({ skillId, runId, result }, format)
            }}
          />
          <button
            type="button"
            disabled={!canCompare || loading}
            onClick={onCompare}
            className="flex items-center gap-2 rounded-md border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-white disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-900"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
            Compare
          </button>
          <button
            type="button"
            disabled={!canPromote}
            onClick={onPromote}
            className="flex items-center gap-2 rounded-md bg-amber-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-amber-600 disabled:cursor-not-allowed disabled:bg-amber-300"
          >
            <BadgeCheck className="h-3.5 w-3.5" />
            Promote
          </button>
        </div>
      </div>

      {error ? (
        <div className="m-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300">
          {error}
        </div>
      ) : null}

      <div className="grid min-h-0 flex-1 grid-cols-[14rem_1fr]">
        <div className="overflow-y-auto border-e border-slate-200 p-3 dark:border-slate-800">
          {allFields.length === 0 && nodeGroups.length === 0 ? (
            <div className="text-sm text-slate-500 dark:text-slate-400">
              {loading ? 'Loading diff...' : 'No fields to compare.'}
            </div>
          ) : null}
          {nodeGroups.length > 0 ? (
            <div className="space-y-3">
              {nodeGroups.map((group) => (
                <div key={group.nodeId}>
                  <div className="mb-1 flex items-center justify-between gap-2 px-1">
                    <span className="truncate font-mono text-xs font-semibold text-slate-700 dark:text-slate-200">
                      {group.nodeId}
                    </span>
                    <span className="flex items-center gap-1.5 text-[11px]">
                      <span
                        className={`rounded px-1.5 py-0.5 font-semibold uppercase ${
                          group.verdict === 'pass'
                            ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300'
                            : 'bg-red-100 text-red-700 dark:bg-red-950/50 dark:text-red-300'
                        }`}
                      >
                        {group.verdict}
                      </span>
                      <span className="text-slate-500 dark:text-slate-400">{Math.round(group.score * 100)}%</span>
                    </span>
                  </div>
                  {group.fields.length === 0 ? (
                    <div className="px-1 pb-1 text-[11px] text-slate-400 dark:text-slate-500">No differences</div>
                  ) : (
                    <div className="space-y-1">{group.fields.map((field) => fieldButton(field, selectedField, setSelectedPath))}</div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div className="space-y-2">{fields.map((field) => fieldButton(field, selectedField, setSelectedPath))}</div>
          )}
        </div>
        <div className="overflow-y-auto p-4">
          {selectedField ? <DiffField field={selectedField} /> : null}
        </div>
      </div>
    </div>
  )
}
