import { useState } from "react"
import { AlertCircle, ArrowLeft, CheckCircle2, RefreshCw } from "lucide-react"
import { ScrollArea } from "@/components/ui/scroll-area"
import { TracePanel } from "@/components/TracePanel"
import { getRunDetail } from "@/api/client"
import type { CallbackEvent } from "@/api/types"
import { useRunHistory } from "../../../hooks/useRunHistory"
import { errorMessage } from "../../../utils/errors"
import { useWorkspaceContext } from "../WorkspaceContext"
import { Button } from "../../ui/button"

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

export function TimelinePanel() {
  const { currentSkillId } = useWorkspaceContext()
  const { runs, isLoading, error, refresh } = useRunHistory(currentSkillId)
  // F2 (trace): clicking a past run loads its full trace (RunDetail.events) in place.
  const [selected, setSelected] = useState<{ runId: string; events: CallbackEvent[] } | null>(null)
  const [traceError, setTraceError] = useState<string | null>(null)
  const [loadingRunId, setLoadingRunId] = useState<string | null>(null)

  const openRun = async (runId: string) => {
    if (!currentSkillId) return
    setLoadingRunId(runId)
    setTraceError(null)
    try {
      const detail = await getRunDetail(currentSkillId, runId)
      setSelected({ runId, events: detail.events })
    } catch (caught) {
      setTraceError(errorMessage(caught))
    } finally {
      setLoadingRunId(null)
    }
  }

  if (selected) {
    return (
      <div className="flex h-full flex-col bg-background">
        <div className="flex h-10 shrink-0 items-center gap-2 border-b border-border px-3">
          <Button
            type="button"
            variant="ghost"
            size="icon-lg"
            onClick={() => setSelected(null)}
            aria-label="Back to timeline"
          >
            <ArrowLeft className="size-4" />
          </Button>
          <span className="truncate font-mono text-xs text-muted-foreground">
            Run {selected.runId.slice(0, 12)}…
          </span>
        </div>
        <div className="min-h-0 flex-1">
          <TracePanel traceLogs={selected.events} activePhase={null} onSelectPrompt={() => undefined} />
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col bg-background">
      <div className="flex h-10 shrink-0 items-center justify-between border-b border-border px-3">
        <div>
          <h3 className="text-xs font-medium text-foreground">Timeline</h3>
          <p className="text-[11px] text-muted-foreground">{runs.length} runs</p>
        </div>
        <Button
          type="button"
          variant="ghost"
          size="icon-lg"
          onClick={() => void refresh()}
          aria-label="Refresh timeline"
          title="Refresh timeline"
        >
          <RefreshCw className="size-4" />
        </Button>
      </div>

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
          {traceError ? (
            <div className="rounded-md border border-destructive/20 bg-destructive/10 p-3 text-xs text-destructive">
              {traceError}
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
              onClick={() => void openRun(run.run_id)}
              disabled={loadingRunId !== null}
              aria-label={`View trace for run ${run.run_id}`}
              className="group w-full cursor-pointer rounded-md border border-transparent px-2 py-2 text-left transition-colors hover:border-border hover:bg-accent disabled:opacity-60"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  {run.status === "success" ? (
                    <CheckCircle2 className="size-4 text-emerald-500" />
                  ) : (
                    <AlertCircle className="size-4 text-destructive" />
                  )}
                  <span className="max-w-[120px] truncate font-mono text-xs text-muted-foreground group-hover:text-foreground">
                    {run.run_id.slice(0, 12)}...
                  </span>
                </div>
                <span className="text-[10px] text-muted-foreground">
                  {loadingRunId === run.run_id ? "Loading…" : relativeTime(run.started_at)}
                </span>
              </div>
              <div className="mt-1 flex items-center justify-between pl-6 text-[11px] text-muted-foreground">
                <span>{formatDuration((run.metrics as unknown as Record<string, unknown>)?.wall_time_sec as number | null)}</span>
                {run.metrics?.total_tokens ? <span>{run.metrics.total_tokens} tokens</span> : null}
              </div>
            </button>
          ))}
        </div>
      </ScrollArea>
    </div>
  )
}
