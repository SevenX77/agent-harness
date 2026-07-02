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
  return result.node_groups.flatMap((group) => group.field_differences)
}

interface NodeGroup {
  nodeId: string
  verdict: 'pass' | 'fail'
  score: number
  fields: FieldDifference[]
}

// D7 / golden-per-agent-node: the backend owns grouping; the UI only renders
// the node_groups contract and does not infer node identity from field paths.
function buildNodeGroups(result: CompareResult | null): NodeGroup[] {
  if (!result?.node_groups?.length) {
    return []
  }
  return result.node_groups.map((node) => ({
    nodeId: node.node_id,
    verdict: node.status,
    score: node.score,
    fields: node.field_differences,
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
          ? 'border-primary/60 bg-primary/10 text-primary'
          : 'border-border bg-card text-muted-foreground hover:bg-muted/40'
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
      <div className="flex h-full flex-col items-center justify-center gap-3 bg-background p-6 text-center">
        <GitCompareArrows className="h-9 w-9 text-muted-foreground" />
        <div>
          <h3 className="font-bold text-foreground">Golden Diff</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            Compare the latest run output against the active golden baseline.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            disabled={!canCompare}
            onClick={onCompare}
            className="flex items-center gap-2 rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/85 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <GitCompareArrows className="h-4 w-4" />
            Compare to Golden
          </button>
          <button
            type="button"
            disabled={!canPromote}
            onClick={onPromote}
            className="flex items-center gap-2 rounded-md border border-warning-border px-3 py-1.5 text-sm font-medium text-warning hover:bg-warning/10 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <BadgeCheck className="h-4 w-4" />
            Promote to Golden
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col bg-background">
      <div className="flex shrink-0 items-center justify-between border-b border-border px-4 py-3">
        <div className="flex items-center gap-3">
          <DiffScore score={result?.total_score ?? 0} />
          <div>
            <h3 className="font-bold text-foreground">Golden Diff</h3>
            <p className="flex flex-wrap gap-x-2 text-xs text-muted-foreground">
              {result ? (
                <>
                  <span>Baseline {result.baseline_id}</span>
                  {result.source_run_id ? <span>Source run {result.source_run_id}</span> : null}
                </>
              ) : (
                <span>No comparison loaded</span>
              )}
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          <ExportButton
            label="Export Compare"
            title="Export comparison report"
            disabled={!result || !skillId}
            filenameBase={reportFileBase(skillId, runId ?? 'compare', result?.baseline_id)}
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
            className="flex items-center gap-2 rounded-md border border-border px-3 py-1.5 text-xs font-medium text-foreground hover:bg-muted/40 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
            Compare
          </button>
          <button
            type="button"
            disabled={!canPromote}
            onClick={onPromote}
            className="flex items-center gap-2 rounded-md bg-warning px-3 py-1.5 text-xs font-medium text-warning-foreground hover:bg-warning/85 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <BadgeCheck className="h-3.5 w-3.5" />
            Promote
          </button>
        </div>
      </div>

      {error ? (
        <div className="m-4 rounded-md border border-destructive-border/60 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      <div className="grid min-h-0 flex-1 grid-cols-[14rem_1fr]">
        <div className="overflow-y-auto border-e border-border p-3">
          {allFields.length === 0 && nodeGroups.length === 0 ? (
            <div className="text-sm text-muted-foreground">
              {loading ? 'Loading diff...' : 'No fields to compare.'}
            </div>
          ) : null}
          {nodeGroups.length > 0 ? (
            <div className="space-y-3">
              {nodeGroups.map((group) => (
                <div key={group.nodeId}>
                  <div className="mb-1 flex items-center justify-between gap-2 px-1">
                    <span className="truncate font-mono text-xs font-semibold text-foreground">
                      {group.nodeId}
                    </span>
                    <span className="flex items-center gap-1.5 text-[11px]">
                      <span
                        className={`rounded px-1.5 py-0.5 font-semibold uppercase ${
                          group.verdict === 'pass'
                            ? 'bg-success/15 text-success'
                            : 'bg-destructive/15 text-destructive'
                        }`}
                      >
                        {group.verdict}
                      </span>
                      <span className="text-muted-foreground">{Math.round(group.score * 100)}%</span>
                    </span>
                  </div>
                  {group.fields.length === 0 ? (
                    <div className="px-1 pb-1 text-[11px] text-muted-foreground">No differences</div>
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
