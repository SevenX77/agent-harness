import { AlertTriangle, Loader2, Play, RotateCcw, Trash2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { startRun } from '../../api/client'
import type { JsonObject, RunDetail, RunMetadata } from '../../api/types'
import { TracePanel } from '../../components/TracePanel'
import { readLintStatus } from '../../hooks/useDebouncedLint'
import { useRunHistory } from '../../hooks/useRunHistory'
import { useRunStream } from '../../hooks/useRunStream'
import { useSkills } from '../../hooks/useSkills'
import { useTraceSelection } from '../../hooks/useTraceSelection'
import { errorMessage, isJsonObject } from '../../utils/errors'

export default function Run() {
  const { skillId = '', runId = null } = useParams()
  const navigate = useNavigate()
  const { skillDetail } = useSkills(skillId)
  const history = useRunHistory(skillId)
  const stream = useRunStream(runId)
  const traceSelection = useTraceSelection()
  const compilePassed = readLintStatus(skillId) === 'passed'
  const [rawInput, setRawInput] = useState('{}')
  const [currentRun, setCurrentRun] = useState<RunMetadata | null>(null)
  const [runDetail, setRunDetail] = useState<RunDetail | null>(null)
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const declaredInputs = useMemo(() => {
    const manifest = skillDetail?.manifest
    return manifest?.type === 'graph' ? manifest.io.inputs : []
  }, [skillDetail])

  const parsedInput = useMemo(() => {
    try {
      const parsed: unknown = JSON.parse(rawInput)
      return isJsonObject(parsed) ? parsed : null
    } catch {
      return null
    }
  }, [rawInput])
  const traceEvents = useMemo(() => {
    const persisted = runDetail?.events ?? []
    return stream.events.length > 0 ? [...persisted, ...stream.events] : persisted
  }, [runDetail?.events, stream.events])

  useEffect(() => {
    if (!runId) {
      setRunDetail(null)
      return
    }

    let cancelled = false
    history.fetchRunDetail(runId)
      .then((detail) => {
        if (!cancelled) {
          setRunDetail(detail)
          setCurrentRun(detail?.metadata ?? null)
        }
      })
      .catch((detailError: unknown) => {
        if (!cancelled) {
          setError(errorMessage(detailError))
        }
      })
    return () => {
      cancelled = true
    }
  }, [history, runId])

  const handleStart = async () => {
    if (!parsedInput) {
      setError('Run input must be a JSON object.')
      return
    }

    setStarting(true)
    setError(null)
    try {
      const run = await startRun(skillId, parsedInput as JsonObject)
      setCurrentRun(run)
      await history.startOptimisticRun(run)
      void navigate(`/skill/${skillId}/run/${run.run_id}`)
    } catch (startError) {
      setError(errorMessage(startError))
    } finally {
      setStarting(false)
    }
  }

  return (
    <main className="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)] bg-background text-foreground">
      <header className="border-b border-border bg-card px-5 py-4">
        <div className="flex items-center justify-between gap-4">
          <div>
            <div className="mb-2 inline-flex items-center gap-2 rounded-md border border-border bg-secondary px-2 py-1 text-xs font-medium text-secondary-foreground">
              <Play className="size-3.5" />
              Run
            </div>
            <h1 className="text-xl font-semibold text-foreground">{skillDetail?.manifest.name ?? skillId}</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Start a full run and stream trace events from the backend.
            </p>
          </div>
          <button
            type="button"
            disabled={!compilePassed || starting}
            onClick={() => void handleStart()}
            className="inline-flex h-9 items-center gap-2 rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-45"
          >
            {starting ? <Loader2 className="size-4 animate-spin" /> : <Play className="size-4" />}
            {starting ? 'Starting' : 'Start run'}
          </button>
        </div>
      </header>

      <section className="min-h-0 overflow-auto p-5">
        {!compilePassed ? (
          <div className="mb-5 rounded-md border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-amber-700 dark:text-amber-300">
            <div className="flex items-center gap-2 font-medium">
              <AlertTriangle className="size-4" />
              Run is locked until Edit lint passes.
            </div>
          </div>
        ) : null}

        <div className="grid gap-5 xl:grid-cols-[360px_minmax(0,1fr)_320px]">
          <label className="block rounded-md border border-border bg-card p-4">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-sm font-semibold text-foreground">Run input JSON</span>
              <button
                type="button"
                onClick={() => {
                  setRawInput('{}')
                  setError(null)
                }}
                className="inline-flex items-center gap-1 rounded-md border border-border bg-background px-2 py-1 text-xs text-muted-foreground hover:bg-accent"
              >
                <RotateCcw className="size-3.5" />
                Reset
              </button>
            </div>
            <textarea
              value={rawInput}
              onChange={(event) => {
                setRawInput(event.target.value)
                setError(null)
              }}
              className="h-72 w-full resize-none rounded-md border border-input bg-background p-3 font-mono text-xs text-foreground outline-none focus:ring-2 focus:ring-ring"
              spellCheck={false}
              aria-label="Run input JSON"
            />
            {error ? <div className="mt-3 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</div> : null}
          </label>

          <section className="min-h-[36rem] overflow-hidden rounded-md border border-border bg-card">
            <TracePanel
              traceLogs={traceEvents}
              activePhase={traceSelection.selectedPhaseId}
              selectedEventId={traceSelection.selectedEventId}
              linkEnabled={traceSelection.linkEnabled}
              onToggleLink={traceSelection.setLinkEnabled}
              onSelectPrompt={() => undefined}
              onSelectEvent={(index, event) => traceSelection.selectEvent(event, index)}
              canCompare={Boolean(runId)}
            />
          </section>

          <aside className="space-y-5">
            <div className="rounded-md border border-border bg-card p-4">
            <h2 className="text-sm font-semibold text-foreground">Run status</h2>
            <dl className="mt-4 space-y-3 text-sm">
              <div className="flex justify-between gap-3">
                <dt className="text-muted-foreground">Route run</dt>
                <dd className="truncate font-mono text-foreground">{runId ?? 'none'}</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-muted-foreground">Current run</dt>
                <dd className="truncate font-mono text-foreground">{currentRun?.run_id ?? 'not started'}</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-muted-foreground">Status</dt>
                <dd className="font-medium text-foreground">{currentRun?.status ?? (runId ? 'loading' : 'idle')}</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-muted-foreground">Inputs</dt>
                <dd className="font-medium text-foreground">{declaredInputs.length}</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-muted-foreground">Stream</dt>
                <dd className="font-medium text-foreground">{stream.status}</dd>
              </div>
              {stream.reconnectInMs ? (
                <div className="flex justify-between gap-3">
                  <dt className="text-muted-foreground">Reconnect</dt>
                  <dd className="font-medium text-foreground">{Math.round(stream.reconnectInMs / 1000)}s</dd>
                </div>
              ) : null}
              {stream.error ? (
                <div className="rounded-md border border-destructive/30 bg-destructive/10 px-2 py-1 text-xs text-destructive">
                  {stream.error}
                </div>
              ) : null}
            </dl>
            </div>
            <div className="rounded-md border border-border bg-card p-4">
              <div className="mb-3 flex items-center justify-between">
                <h2 className="text-sm font-semibold text-foreground">History</h2>
                <button type="button" onClick={() => void history.refresh()} className="text-xs font-medium text-muted-foreground hover:text-foreground">
                  Refresh
                </button>
              </div>
              <div className="max-h-72 space-y-2 overflow-auto">
                {history.runs.map((run) => (
                  <div key={run.run_id} className="rounded-md border border-border bg-background p-2">
                    <button
                      type="button"
                      onClick={() => void navigate(`/skill/${skillId}/run/${run.run_id}`)}
                      className="block w-full truncate text-left font-mono text-xs font-medium text-foreground hover:text-primary"
                    >
                      {run.run_id}
                    </button>
                    <div className="mt-1 flex items-center justify-between gap-2 text-xs text-muted-foreground">
                      <span>{run.status}</span>
                      <button
                        type="button"
                        aria-label={`Delete run ${run.run_id}`}
                        onClick={() => void history.deleteRun(run.run_id)}
                        className="rounded p-1 hover:bg-accent hover:text-destructive"
                      >
                        <Trash2 className="size-3.5" />
                      </button>
                    </div>
                  </div>
                ))}
                {history.runs.length === 0 ? <div className="text-sm text-muted-foreground">No runs yet.</div> : null}
              </div>
            </div>
          </aside>
        </div>
      </section>
    </main>
  )
}
