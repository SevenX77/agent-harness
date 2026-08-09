import { FileText, FlaskConical, Play, RefreshCw } from "lucide-react"
import { ScrollArea } from "@/components/ui/scroll-area"
import { openLocalPath } from "@/lib/tauri"
import { formatRunDuration, formatRunTokens } from "@/utils/run-format"
import { runStatusMark } from "@/utils/run-status-mark"
import type { RunMetadata } from "@/api/types"
import { useRunHistory } from "../../../hooks/useRunHistory"
import { useWorkspaceContext } from "../WorkspaceContext"
import { Button } from "../../ui/button"
import { Tooltip, TooltipContent, TooltipTrigger } from "../../ui/tooltip"
import { PanelHeader } from "./_shared/PanelHeader"

const relativeTime = (value: string): string => {
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

const shortHash = (value?: string | null): string | null => {
  if (!value) return null
  const normalized = value.startsWith("sha256:") ? value.slice("sha256:".length) : value
  return normalized.slice(0, 8)
}

const shortRefTail = (value?: string | null): string | null => {
  if (!value) return null
  const parts = value.split("/")
  return parts.at(-1) || value
}

export function RunIdentityInline({ run }: { run: RunMetadata }) {
  const artifactId = run.artifact_ref?.artifact_id ?? null
  const contentHash = shortHash(run.artifact_ref?.content_hash)
  const fingerprint = shortHash(run.execution_fingerprint ?? run.artifact_ref?.execution_fingerprint)
  const sourceMap = shortRefTail(run.source_map_ref ?? run.artifact_ref?.source_map_ref)
  if (!artifactId && !contentHash && !fingerprint && !sourceMap) return null
  return (
    <div className="mt-1 flex min-w-0 flex-wrap items-center gap-1.5 text-[10px] text-muted-foreground">
      {contentHash ? (
        <span className="rounded-md border border-border bg-muted/40 px-1.5 py-0.5 font-mono">art {contentHash}</span>
      ) : null}
      {fingerprint ? (
        <span className="rounded-md border border-border bg-muted/40 px-1.5 py-0.5 font-mono">fp {fingerprint}</span>
      ) : null}
      {artifactId ? (
        <span className="max-w-[140px] truncate rounded-md border border-border bg-muted/40 px-1.5 py-0.5 font-mono">
          {artifactId}
        </span>
      ) : null}
      {sourceMap ? (
        <span className="max-w-[140px] truncate rounded-md border border-border bg-muted/40 px-1.5 py-0.5 font-mono">
          map {sourceMap}
        </span>
      ) : null}
    </div>
  )
}

/**
 * What KIND of attempt this row is — and nothing else (decision 2026-08-09 D9).
 *
 * The old leading slot answered two questions at once: a predict got the flask
 * tinted by its status, a run got its status icon outright, so the same
 * position sometimes said "this is a rehearsal" and sometimes said "this
 * succeeded". Type and outcome are separate facts; they now have separate
 * marks, and this one is deliberately neutral-coloured.
 */
function RunTypeMark({ run }: { run: RunMetadata }) {
  const predict = run.kind === "predict"
  const Icon = predict ? FlaskConical : Play
  return (
    <Icon
      data-run-type={predict ? "predict" : "run"}
      aria-label={predict ? "Predict attempt" : "Run"}
      className="size-4 shrink-0 text-muted-foreground"
    />
  )
}

/** How the row's run ended, in the same vocabulary the Trace strip uses (D9). */
function RunStatusBadge({ run }: { run: RunMetadata }) {
  const mark = runStatusMark(run.status)
  if (!mark) return null
  const Icon = mark.icon
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Icon
          data-run-status={run.status}
          aria-label={mark.label}
          className={`size-4 shrink-0 ${mark.tone}`}
        />
      </TooltipTrigger>
      <TooltipContent>{mark.label}</TooltipContent>
    </Tooltip>
  )
}

/**
 * D8 entrance ②: the report is reachable from the run's own row.
 *
 * Absent rather than disabled when the run left none — a report either exists
 * on disk or does not, and a greyed control implies it could be enabled.
 */
function RunReportLink({ run }: { run: RunMetadata }) {
  const reportPath = run.report_path
  if (!reportPath) return null
  return (
    <button
      type="button"
      data-run-report
      aria-label={`Open report for run ${run.run_id}`}
      onClick={() => { void openLocalPath(reportPath) }}
      className="flex items-center gap-1 text-[11px] text-muted-foreground underline-offset-2 transition-colors hover:text-foreground hover:underline"
    >
      <FileText className="size-3" />
      Report
    </button>
  )
}

interface TimelinePanelProps {
  /** Open one run's trace (viewed-run model: Workspace owns the fetch + view). */
  onSelectRun?: (run: RunMetadata) => void
  /** The run whose detail is currently being fetched (progress affordance). */
  loadingRunId?: string | null
}

/**
 * Trace region, list view: every predict/run attempt for the current skill,
 * newest first. Viewing a run's trace is owned by the Workspace-level viewed-run
 * state (decision 2026-08-07); this panel only reports the row click.
 *
 * The header says "Trace" because that is the region's name — 2026-08-09 D1
 * retired "Timeline" as a user-facing noun. The nav slot was renamed with the
 * decision; this header was not, so the same region announced itself by two
 * different names depending on where you looked.
 */
export function TimelinePanel({ onSelectRun, loadingRunId = null }: TimelinePanelProps) {
  const { currentSkillId } = useWorkspaceContext()
  const { runs, isLoading, error, refresh } = useRunHistory(currentSkillId)

  return (
    <div className="flex h-full flex-col bg-background">
      <PanelHeader
        title="Trace"
        extra={<span className="text-[11px] text-muted-foreground">{runs.length} runs</span>}
        right={(
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="icon-lg"
                onClick={() => void refresh()}
                aria-label="Refresh run list"
              >
                <RefreshCw className="size-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Refresh run list</TooltipContent>
          </Tooltip>
        )}
      />

      <ScrollArea className="flex-1">
        <div className="space-y-1 px-2 py-2">
          {isLoading && runs.length === 0 ? (
            <div className="p-3 text-xs text-muted-foreground">Loading runs...</div>
          ) : null}
          {error ? (
            <div className="rounded-md border border-destructive/20 bg-destructive/10 p-3 text-xs text-destructive">
              Failed to load run history
            </div>
          ) : null}
          {!isLoading && !error && runs.length === 0 ? (
            <div className="p-3 text-center text-xs text-muted-foreground">
              No runs recorded yet. Compile and run your skill to see them here!
            </div>
          ) : null}
          {runs.map((run) => (
            // The row opens the trace; the report link is its sibling, not its
            // child — a button inside a button is invalid and would swallow the
            // row click on the way out.
            <div key={run.run_id} className="group rounded-md transition-colors hover:bg-accent">
              <button
                type="button"
                onClick={() => onSelectRun?.(run)}
                disabled={loadingRunId !== null}
                aria-label={`View trace for run ${run.run_id}`}
                className="w-full cursor-pointer px-2 pt-2 text-left disabled:opacity-60"
              >
                <div className="flex items-center gap-2">
                  <RunTypeMark run={run} />
                  <span className="min-w-0 flex-1 break-all font-mono text-xs text-muted-foreground group-hover:text-foreground">
                    {run.run_id}
                  </span>
                  <RunStatusBadge run={run} />
                </div>
                <div className="mt-1 flex items-center justify-between pl-6 text-[11px] text-muted-foreground">
                  <span>
                    {formatRunDuration(run.metrics?.wall_time_sec) ?? "n/a"}
                    {formatRunTokens(run.metrics?.total_tokens)
                      ? ` · ${formatRunTokens(run.metrics?.total_tokens)}`
                      : ""}
                  </span>
                  <span>{loadingRunId === run.run_id ? "Loading…" : relativeTime(run.started_at)}</span>
                </div>
                <div className="pl-6">
                  <RunIdentityInline run={run} />
                </div>
              </button>
              <div className="px-2 pb-2 pl-8">
                <RunReportLink run={run} />
              </div>
            </div>
          ))}
        </div>
      </ScrollArea>
    </div>
  )
}
