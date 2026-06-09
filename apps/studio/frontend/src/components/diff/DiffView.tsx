import { BadgeCheck, GitCompareArrows, RefreshCw } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import type { CompareResult, FieldDifference } from '../../api/types'
import { renderCompareReport, reportFileBase } from '../../utils/reportTemplates'
import { ExportButton } from '../export/ExportButton'
import { Button } from '../ui/button'
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
  const [selectedPath, setSelectedPath] = useState<string | null>(null)
  const selectedField = fields.find((field) => field.field_path === selectedPath) ?? fields[0] ?? null

  useEffect(() => {
    setSelectedPath(fields[0]?.field_path ?? null)
  }, [fields])

  if (!result && !loading && !error) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 bg-muted/30 p-6 text-center">
        <GitCompareArrows className="h-9 w-9 text-muted-foreground/80" />
        <div>
          <h3 className="font-bold text-foreground">Golden Diff</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            Compare the latest run output against the active golden baseline.
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            type="button"
            disabled={!canCompare}
            onClick={onCompare}
          >
            <GitCompareArrows className="h-4 w-4" />
            Compare to Golden
          </Button>
          <Button
            type="button"
            variant="outline"
            disabled={!canPromote}
            onClick={onPromote}
          >
            <BadgeCheck className="h-4 w-4" />
            Promote to Golden
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col bg-muted/10">
      <div className="flex shrink-0 flex-col gap-3 border-b border-border px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <DiffScore score={result?.total_score ?? 0} />
          <div>
            <h3 className="font-bold text-foreground">Golden Diff</h3>
            <p className="text-xs text-muted-foreground">
              {result ? `Against ${result.golden_run_id}` : 'No comparison loaded'}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
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
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={!canCompare || loading}
            onClick={onCompare}
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
            Compare
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={!canPromote}
            onClick={onPromote}
          >
            <BadgeCheck className="h-3.5 w-3.5" />
            Promote
          </Button>
        </div>
      </div>

      {error ? (
        <div className="m-4 rounded-md border border-destructive/20 bg-destructive/10 px-3 py-2 text-sm text-destructive dark:border-destructive/40 dark:bg-destructive/20 dark:text-destructive-foreground">
          {error}
        </div>
      ) : null}

      <div className="grid min-h-0 flex-1 grid-cols-1 md:grid-cols-[14rem_1fr]">
        <div className="max-h-36 overflow-y-auto border-b border-border p-3 md:max-h-none md:border-b-0 md:border-e">
          {fields.length === 0 ? (
            <div className="text-sm text-muted-foreground">
              {loading ? 'Loading diff...' : 'No fields to compare.'}
            </div>
          ) : null}
          <div className="space-y-2">
            {fields.map((field) => (
              <button
                key={field.field_path}
                type="button"
                onClick={() => setSelectedPath(field.field_path)}
                className={`block w-full rounded-md border px-2 py-2 text-start text-xs ${
                  selectedField?.field_path === field.field_path
                    ? 'border-primary/50 bg-primary/10 text-primary dark:border-primary/60 dark:bg-primary/20 dark:text-primary-foreground'
                    : 'border-border bg-card text-card-foreground hover:bg-accent hover:text-accent-foreground'
                }`}
              >
                <div className="truncate font-mono font-semibold">{field.field_path}</div>
                <div className="mt-1 flex items-center justify-between">
                  <span>{field.type}</span>
                  <span>{Math.round(field.score * 100)}%</span>
                </div>
              </button>
            ))}
          </div>
        </div>
        <div className="min-w-0 overflow-y-auto p-4">
          {selectedField ? <DiffField field={selectedField} /> : null}
        </div>
      </div>
    </div>
  )
}
