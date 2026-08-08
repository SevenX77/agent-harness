import { AlertCircle, CheckCircle2, CirclePause, FlaskConical, Loader2, RefreshCw } from "lucide-react"
import { ScrollArea } from "@/components/ui/scroll-area"
import type { RunMetadata } from "@/api/types"
import { useRunHistory } from "../../../hooks/useRunHistory"
import { useWorkspaceContext } from "../WorkspaceContext"
import { Button } from "../../ui/button"
import { Tooltip, TooltipContent, TooltipTrigger } from "../../ui/tooltip"
import { PanelHeader } from "./_shared/PanelHeader"

const formatDuration = (sec?: number | null) => {
  if (sec == null) return "n/a"
  return sec < 1 ? `${(sec * 1000).toFixed(0)}ms` : `${sec.toFixed(1)}s`
}

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
 * Row-leading icon. A predict attempt differs from a real run by ICON ONLY (PM:
 * predict 历史行仅用 icon 与真实 run 行区分,其余样式一致) — the flask keeps the
 * status color so a failed predict still reads as failed.
 */
function RunRowIcon({ run }: { run: RunMetadata }) {
  const statusColor =
    run.status === "success"
      ? "text-success"
      : run.status === "running"
        ? "text-muted-foreground"
        : run.status === "paused"
          ? "text-warning"
          : "text-destructive"
  if (run.kind === "predict") {
    return <FlaskConical aria-label="Predict attempt" className={`size-4 ${statusColor}`} />
  }
  if (run.status === "running") {
    return <Loader2 aria-label="Run in progress" className="size-4 animate-spin text-muted-foreground" />
  }
  if (run.status === "paused") {
    return <CirclePause aria-label="Run paused" className="size-4 text-warning" />
  }
  if (run.status === "success") {
    return <CheckCircle2 className="size-4 text-success" />
  }
  return <AlertCircle className="size-4 text-destructive" />
}

interface TimelinePanelProps {
  /** Open one run's trace (viewed-run model: Workspace owns the fetch + view). */
  onSelectRun?: (run: RunMetadata) => void
  /** The run whose detail is currently being fetched (progress affordance). */
  loadingRunId?: string | null
}

/**
 * Timeline region, list view: every predict/run attempt for the current skill,
 * newest first. Viewing a run's trace is owned by the Workspace-level viewed-run
 * state (decision 2026-08-07); this panel only reports the row click.
 */
export function TimelinePanel({ onSelectRun, loadingRunId = null }: TimelinePanelProps) {
  const { currentSkillId } = useWorkspaceContext()
  const { runs, isLoading, error, refresh } = useRunHistory(currentSkillId)

  return (
    <div className="flex h-full flex-col bg-background">
      <PanelHeader
        title="Timeline"
        extra={<span className="text-[11px] text-muted-foreground">{runs.length} runs</span>}
        right={(
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="icon-lg"
                onClick={() => void refresh()}
                aria-label="Refresh timeline"
              >
                <RefreshCw className="size-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Refresh timeline</TooltipContent>
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
            <button
              type="button"
              key={run.run_id}
              onClick={() => onSelectRun?.(run)}
              disabled={loadingRunId !== null}
              aria-label={`View trace for run ${run.run_id}`}
              className="group w-full cursor-pointer rounded-md px-2 py-2 text-left transition-colors hover:bg-accent disabled:opacity-60"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <RunRowIcon run={run} />
                  <span className="max-w-[120px] truncate font-mono text-xs text-muted-foreground group-hover:text-foreground">
                    {run.run_id.slice(0, 12)}...
                  </span>
                </div>
                <span className="text-[10px] text-muted-foreground">
                  {loadingRunId === run.run_id ? "Loading…" : relativeTime(run.started_at)}
                </span>
              </div>
              <div className="mt-1 flex items-center justify-between pl-6 text-[11px] text-muted-foreground">
                <span>{formatDuration(run.metrics?.wall_time_sec)}</span>
                {run.metrics?.total_tokens ? <span>{run.metrics.total_tokens} tokens</span> : null}
              </div>
              <div className="pl-6">
                <RunIdentityInline run={run} />
              </div>
            </button>
          ))}
        </div>
      </ScrollArea>
    </div>
  )
}
