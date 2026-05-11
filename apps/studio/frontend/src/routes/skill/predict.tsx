import { AlertTriangle, CheckCircle2, Loader2, Sparkles } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { postPredictRun, type PredictRunResponse } from '../../api/client'
import type { JsonObject } from '../../api/types'
import { PredictInputDialog } from '../../components/playground/PredictInputDialog'
import { readLintStatus } from '../../hooks/useDebouncedLint'
import { useSkills } from '../../hooks/useSkills'
import { errorMessage } from '../../utils/errors'

export default function Predict() {
  const { skillId = '' } = useParams()
  const { skillDetail } = useSkills(skillId)
  const [inputOpen, setInputOpen] = useState(false)
  const [payload, setPayload] = useState<JsonObject | null>(null)
  const [predictResult, setPredictResult] = useState<PredictRunResponse | null>(null)
  const [running, setRunning] = useState(false)
  const [predictError, setPredictError] = useState<string | null>(null)
  const lintStatus = readLintStatus(skillId)
  const compilePassed = lintStatus === 'passed'

  const inputCount = useMemo(() => {
    const manifest = skillDetail?.manifest
    return manifest?.type === 'graph' ? manifest.io.inputs.length : 0
  }, [skillDetail])
  const inputs = useMemo(() => {
    const manifest = skillDetail?.manifest
    return manifest?.type === 'graph' ? manifest.io.inputs : []
  }, [skillDetail])

  const runPredict = async (nextPayload: JsonObject) => {
    setPayload(nextPayload)
    setInputOpen(false)
    setRunning(true)
    setPredictError(null)
    try {
      const response = await postPredictRun(skillId, nextPayload)
      setPredictResult(response)
    } catch (error) {
      setPredictResult(null)
      setPredictError(errorMessage(error))
    } finally {
      setRunning(false)
    }
  }

  return (
    <main className="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)] bg-background text-foreground">
      <header className="border-b border-border bg-card px-5 py-4">
        <div className="flex items-center justify-between gap-4">
          <div>
            <div className="mb-2 inline-flex items-center gap-2 rounded-md border border-border bg-secondary px-2 py-1 text-xs font-medium text-secondary-foreground">
              <Sparkles className="size-3.5" />
              Predict
            </div>
            <h1 className="text-xl font-semibold text-foreground">{skillDetail?.manifest.name ?? skillId}</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Run the compiled skill against one input and prepare a golden baseline draft.
            </p>
          </div>
          <button
            type="button"
            disabled={!compilePassed || running}
            onClick={() => setInputOpen(true)}
            className="inline-flex h-9 items-center justify-center gap-2 rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground shadow-sm transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-45"
          >
            {running ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
            {running ? 'Predicting' : 'New predict'}
          </button>
        </div>
      </header>

      <section className="min-h-0 overflow-auto p-5">
        <div className="rounded-md border border-border bg-card p-4">
          <div className="flex items-start gap-3">
            {compilePassed ? (
              <CheckCircle2 className="mt-0.5 size-5 text-emerald-600 dark:text-emerald-400" />
            ) : (
              <AlertTriangle className="mt-0.5 size-5 text-amber-600 dark:text-amber-300" />
            )}
            <div>
              <h2 className="text-sm font-semibold text-foreground">
                {compilePassed ? 'Compile guard passed' : 'Predict is locked'}
              </h2>
              <p className="mt-1 text-sm text-muted-foreground">
                {compilePassed
                  ? `Ready for runtime input${inputCount ? ` (${inputCount} declared field${inputCount === 1 ? '' : 's'})` : ''}.`
                  : 'Open Edit, wait for lint to pass, then return to Predict.'}
              </p>
            </div>
          </div>
        </div>

        <div className="mt-5 rounded-md border border-border bg-card p-4">
          <h2 className="text-sm font-semibold text-foreground">Current input</h2>
          <pre className="mt-3 max-h-72 overflow-auto rounded-md border border-border bg-muted/40 p-3 text-xs text-foreground">
            {JSON.stringify(payload ?? {}, null, 2)}
          </pre>
        </div>

        <div className="mt-5 rounded-md border border-border bg-card p-4">
          <h2 className="text-sm font-semibold text-foreground">Predict result</h2>
          {predictError ? (
            <div className="mt-3 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {predictError}
            </div>
          ) : (
            <pre className="mt-3 max-h-96 overflow-auto rounded-md border border-border bg-muted/40 p-3 text-xs text-foreground">
              {JSON.stringify(predictResult ?? { status: running ? 'running' : 'idle' }, null, 2)}
            </pre>
          )}
        </div>

        {inputOpen ? (
          <PredictInputDialog
            skillId={skillId}
            inputs={inputs}
            onClose={() => setInputOpen(false)}
            onSubmit={(nextPayload) => void runPredict(nextPayload)}
          />
        ) : null}
      </section>
    </main>
  )
}
