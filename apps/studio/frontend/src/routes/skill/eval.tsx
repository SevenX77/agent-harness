import { BadgeCheck, GitCompare, Loader2, Rocket } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { saveGoldenBaseline } from '../../api/client'
import type { RunDetail } from '../../api/types'
import { DiffView } from '../../components/diff/DiffView'
import { PublishModal } from '../../components/studio/publish-modal'
import { useGoldenDiff } from '../../hooks/useGoldenDiff'
import { useRunHistory } from '../../hooks/useRunHistory'
import { useSkills } from '../../hooks/useSkills'
import { errorMessage } from '../../utils/errors'
import { celebrateSuccess } from '../../lib/confetti'

export default function Eval() {
  const { skillId = '' } = useParams()
  const [searchParams, setSearchParams] = useSearchParams()
  const { skillDetail } = useSkills(skillId)
  const history = useRunHistory(skillId)
  const selectedRunId = searchParams.get('run_id') ?? history.runs[0]?.run_id ?? null
  const diff = useGoldenDiff(skillId, selectedRunId)
  const [runDetail, setRunDetail] = useState<RunDetail | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [savingGolden, setSavingGolden] = useState(false)
  const [publishOpen, setPublishOpen] = useState(false)

  useEffect(() => {
    if (!selectedRunId) {
      setRunDetail(null)
      return
    }
    let cancelled = false
    history.fetchRunDetail(selectedRunId)
      .then((detail) => {
        if (!cancelled) {
          setRunDetail(detail)
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setMessage(errorMessage(error))
        }
      })
    return () => {
      cancelled = true
    }
  }, [history, selectedRunId])

  useEffect(() => {
    if (selectedRunId) {
      void diff.compare()
    } else {
      diff.clear()
    }
  }, [diff.compare, diff.clear, selectedRunId])

  const artifact = useMemo(() => runDetail?.final_context ?? {}, [runDetail])

  const saveGolden = async () => {
    if (!selectedRunId) {
      setMessage('Select a run before saving a golden baseline.')
      return
    }

    setSavingGolden(true)
    setMessage(null)
    try {
      const baseline = await saveGoldenBaseline(skillId, selectedRunId, false)
      setMessage(`Saved golden baseline ${baseline.id}.`)
      celebrateSuccess()
      await history.refresh()
    } catch (error) {
      setMessage(errorMessage(error))
    } finally {
      setSavingGolden(false)
    }
  }

  return (
    <main className="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)] bg-background text-foreground">
      <header className="border-b border-border bg-card px-5 py-4">
        <div className="flex items-center justify-between gap-4">
          <div>
            <div className="mb-2 inline-flex items-center gap-2 rounded-md border border-border bg-secondary px-2 py-1 text-xs font-medium text-secondary-foreground">
              <GitCompare className="size-3.5" />
              Eval
            </div>
            <h1 className="text-xl font-semibold text-foreground">{skillDetail?.manifest.name ?? skillId}</h1>
            <p className="mt-1 text-sm text-muted-foreground">Compare a run artifact against the active golden baseline.</p>
          </div>
          <div className="flex items-center gap-2">
            <select
              value={selectedRunId ?? ''}
              onChange={(event) => setSearchParams(event.target.value ? { run_id: event.target.value } : {})}
              className="h-9 rounded-md border border-input bg-background px-2 text-sm text-foreground"
              aria-label="Select eval run"
            >
              <option value="">Select run</option>
              {history.runs.map((run) => (
                <option key={run.run_id} value={run.run_id}>{run.run_id}</option>
              ))}
            </select>
            <button
              type="button"
              disabled={!selectedRunId || diff.loading}
              onClick={() => void diff.compare()}
              className="inline-flex h-9 items-center gap-2 rounded-md border border-border bg-background px-3 text-sm font-medium text-foreground hover:bg-accent disabled:cursor-not-allowed disabled:opacity-45"
            >
              {diff.loading ? 'Comparing' : 'Compare'}
            </button>
            <button
              type="button"
              disabled={!selectedRunId || savingGolden}
              onClick={() => void saveGolden()}
              className="inline-flex h-9 items-center gap-2 rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-45"
            >
              {savingGolden ? <Loader2 className="size-4 animate-spin" /> : <BadgeCheck className="size-4" />}
              Save as Golden
            </button>
            <button
              type="button"
              onClick={() => setPublishOpen(true)}
              className="inline-flex h-9 items-center gap-2 rounded-md border border-border bg-background px-3 text-sm font-medium text-foreground hover:bg-accent"
            >
              <Rocket className="size-4" />
              Publish
            </button>
          </div>
        </div>
        {message ? <div className="mt-3 rounded-md border border-border bg-background px-3 py-2 text-sm text-muted-foreground">{message}</div> : null}
        {diff.error ? <div className="mt-3 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">{diff.error}</div> : null}
      </header>

      <section className="grid min-h-0 overflow-hidden md:grid-cols-2">
        <div className="flex min-h-0 flex-col border-b border-border md:border-b-0 md:border-r">
          <div className="border-b border-border px-4 py-3">
            <h2 className="text-sm font-semibold text-foreground">Current artifact</h2>
            <p className="mt-1 text-xs text-muted-foreground">{selectedRunId ?? 'No run selected'}</p>
          </div>
          <pre className="min-h-0 flex-1 overflow-auto bg-background p-4 text-xs text-foreground">
            {JSON.stringify(artifact, null, 2)}
          </pre>
        </div>
        <div className="flex min-h-0 flex-col">
          <DiffView
            result={diff.result}
            skillId={skillId}
            runId={selectedRunId}
            loading={diff.loading}
            error={diff.error}
            canCompare={Boolean(selectedRunId)}
            canPromote={Boolean(selectedRunId)}
            onCompare={() => void diff.compare()}
            onPromote={() => void saveGolden()}
          />
        </div>
      </section>
      <PublishModal open={publishOpen} onClose={() => setPublishOpen(false)} />
    </main>
  )
}
