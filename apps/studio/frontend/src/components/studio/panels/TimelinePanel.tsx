import { useEffect, useMemo, useState } from "react"
import { AlertCircle, ArrowLeft, CheckCircle2, RefreshCw } from "lucide-react"
import { ScrollArea } from "@/components/ui/scroll-area"
import { TracePanel } from "@/components/TracePanel"
import { PromptInspector } from "@/components/PromptInspector"
import { getRunDetail } from "@/api/client"
import type { CallbackEvent, EventEnvelope, RunMetadata } from "@/api/types"
import { findPromptEvent } from "@/utils/trace"
import { useRunHistory } from "../../../hooks/useRunHistory"
import { errorMessage } from "../../../utils/errors"
import { useWorkspaceContext } from "../WorkspaceContext"
import { Button } from "../../ui/button"
import { EdgeContextView } from "./EdgeContextView"

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

function RunIdentityInline({ run }: { run: RunMetadata }) {
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

export function TimelinePanel() {
  const { currentSkillId, selectedEdge, setSelectedEdge } = useWorkspaceContext()
  const { runs, isLoading, error, refresh } = useRunHistory(currentSkillId)
  // F2 (trace): clicking a past run loads its full trace (RunDetail.events) in place.
  const [selected, setSelected] = useState<{ runId: string; events: EventEnvelope[]; metadata: RunMetadata } | null>(null)
  const [traceError, setTraceError] = useState<string | null>(null)
  const [loadingRunId, setLoadingRunId] = useState<string | null>(null)
  // D8 (prompt 回溯): the historical trace owns its own PromptInspector selection
  // state. Clicking "Inspect prompt" on any row resolves — via findPromptEvent —
  // back to the driving prompt_captured event in the same phase.
  const [promptIndex, setPromptIndex] = useState<number | null>(null)
  const promptEvent = useMemo<CallbackEvent | null>(() => {
    if (!selected || promptIndex === null) return null
    return findPromptEvent(selected.events.map((envelope) => envelope.payload as CallbackEvent), promptIndex)
  }, [selected, promptIndex])

  // D14 mode precedence: the panel has three mutually-exclusive views (edge dot
  // context, a selected run's trace, the run list). A dot click (selectedEdge)
  // takes over, so clear any open run-detail; opening a run clears the dot.
  useEffect(() => {
    if (selectedEdge) {
      setSelected(null)
    }
  }, [selectedEdge])

  const openRun = async (runId: string) => {
    if (!currentSkillId) return
    setSelectedEdge?.(null)
    setLoadingRunId(runId)
    setTraceError(null)
    try {
      const detail = await getRunDetail(currentSkillId, runId)
      setSelected({ runId, events: detail.events, metadata: detail.metadata })
    } catch (caught) {
      setTraceError(errorMessage(caught))
    } finally {
      setLoadingRunId(null)
    }
  }

  // Dot/edge context is trace-owned (D14 / properties F3); it takes precedence.
  if (selectedEdge) {
    return <EdgeContextView selectedEdge={selectedEdge} onClear={() => setSelectedEdge?.(null)} />
  }

  if (selected) {
    return (
      <div className="flex h-full flex-col bg-background">
        <div className="flex shrink-0 items-start gap-2 border-b border-border px-3 py-2">
          <Button
            type="button"
            variant="ghost"
            size="icon-lg"
            onClick={() => {
              setSelected(null)
              setPromptIndex(null)
            }}
            aria-label="Back to timeline"
          >
            <ArrowLeft className="size-4" />
          </Button>
          <div className="min-w-0 flex-1">
            <span className="block truncate font-mono text-xs text-muted-foreground">
              Run {selected.runId.slice(0, 12)}…
            </span>
            <RunIdentityInline run={selected.metadata} />
          </div>
        </div>
        <div className="min-h-0 flex-1">
          <TracePanel traceLogs={selected.events} activePhase={null} onSelectPrompt={setPromptIndex} />
        </div>
        <PromptInspector promptEvent={promptEvent} onClose={() => setPromptIndex(null)} />
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
