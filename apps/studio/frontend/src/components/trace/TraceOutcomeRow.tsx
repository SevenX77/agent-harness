import { AlertCircle, CheckCircle2, CirclePause, Clock, FileText, Hash } from 'lucide-react'
import { openLocalPath } from '../../lib/tauri'
import { formatRunDuration, formatRunTokens } from '../../utils/run-format'
import type { TraceOutcomeEntry } from '../../utils/trace-outcome'

const OUTCOME_PRESENTATION = {
  success: { icon: CheckCircle2, label: 'Run succeeded', tone: 'text-success' },
  failed: { icon: AlertCircle, label: 'Run failed', tone: 'text-destructive' },
  interrupted: { icon: CirclePause, label: 'Run interrupted', tone: 'text-warning' },
} as const

/**
 * The last thing in a run's trace: how it ended, what it cost, and the report.
 *
 * A report is this run's product, and a product belongs at the end of the
 * process that made it (decision 2026-08-09 D8) — reachable by reading to the
 * bottom, rather than by knowing to look in a menu. It is deliberately NOT a
 * step: no engine work happened here, so it neither expands nor takes part in
 * the node grouping above it.
 */
export function TraceOutcomeRow({ outcome }: { outcome: TraceOutcomeEntry }) {
  const { icon: Icon, label, tone } = OUTCOME_PRESENTATION[outcome.status]
  const duration = formatRunDuration(outcome.wallTimeSec)
  const tokens = formatRunTokens(outcome.totalTokens)

  return (
    <div data-trace-outcome={outcome.status} className="relative mt-2 pl-5">
      <div className={`absolute -left-[7px] top-2.5 size-3 rounded-full border-2 border-background bg-current ${tone}`} />
      <div className="rounded-md border border-border bg-muted/30 px-2.5 py-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className={`flex items-center gap-1.5 text-xs font-semibold ${tone}`}>
            <Icon className="h-3.5 w-3.5" />
            {label}
          </span>
          {duration ? (
            <span className="flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
              <Clock className="h-3 w-3" />
              {duration}
            </span>
          ) : null}
          {tokens ? (
            <span className="flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
              <Hash className="h-3 w-3" />
              {tokens}
            </span>
          ) : null}
        </div>
        {outcome.reportPath ? (
          <button
            type="button"
            data-trace-outcome-report
            onClick={() => { void openLocalPath(outcome.reportPath as string) }}
            className="mt-1.5 flex items-center gap-1.5 text-xs text-muted-foreground underline-offset-2 transition-colors hover:text-foreground hover:underline"
          >
            <FileText className="h-3.5 w-3.5" />
            Open run report
          </button>
        ) : null}
      </div>
    </div>
  )
}
