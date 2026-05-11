import { FileJson, Loader2, X } from 'lucide-react'
import { useMemo, useState, type ChangeEvent } from 'react'
import type { JsonObject } from '../../api/types'
import { useInputPlayground, type PlaygroundInputSpec } from '../../hooks/useInputPlayground'
import { inferJsonSchema } from '../../lib/schema-infer'
import { errorMessage, isJsonObject } from '../../utils/errors'

interface PredictInputDialogProps {
  skillId: string
  inputs: PlaygroundInputSpec[]
  onClose: () => void
  onSubmit: (payload: JsonObject) => void
}

function defaultsFromInputs(inputs: PlaygroundInputSpec[]) {
  return Object.fromEntries(inputs.map((input) => [input.name, input.default ?? ''])) as JsonObject
}

export function PredictInputDialog({ skillId, inputs, onClose, onSubmit }: PredictInputDialogProps) {
  const playground = useInputPlayground(inputs)
  const [rawJson, setRawJson] = useState(() => JSON.stringify(defaultsFromInputs(inputs), null, 2))
  const [validating, setValidating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const parsed = useMemo(() => {
    try {
      const value: unknown = JSON.parse(rawJson)
      return isJsonObject(value) ? value : null
    } catch {
      return null
    }
  }, [rawJson])

  const schema = useMemo(() => (parsed ? inferJsonSchema(parsed) : null), [parsed])

  const handleFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) {
      return
    }
    setRawJson(await file.text())
    setError(null)
  }

  const validateAndSubmit = async () => {
    if (!parsed) {
      setError('JSON input must be an object.')
      return
    }

    setValidating(true)
    setError(null)
    try {
      await playground.validateRemote(skillId, parsed)
      onSubmit(parsed)
    } catch (remoteError) {
      setError(errorMessage(remoteError))
    } finally {
      setValidating(false)
    }
  }

  return (
    <div className="fixed inset-0 z-modal grid place-items-center bg-background/70 p-4 backdrop-blur-sm">
      <section className="flex max-h-[82vh] w-full max-w-2xl flex-col rounded-md border border-border bg-card shadow-xl">
        <header className="flex items-center justify-between border-b border-border px-4 py-3">
          <div>
            <h2 className="text-sm font-semibold text-foreground">Predict input</h2>
            <p className="mt-1 text-xs text-muted-foreground">{inputs.length || 'Raw'} declared input fields</p>
          </div>
          <button type="button" onClick={onClose} aria-label="Close input dialog" className="rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-foreground">
            <X className="size-4" />
          </button>
        </header>

        <div className="grid min-h-0 flex-1 gap-4 overflow-auto p-4 md:grid-cols-2">
          <label className="min-h-0">
            <span className="mb-2 block text-xs font-semibold uppercase tracking-wide text-muted-foreground">JSON payload</span>
            <textarea
              value={rawJson}
              onChange={(event) => {
                setRawJson(event.target.value)
                setError(null)
              }}
              className="h-72 w-full resize-none rounded-md border border-input bg-background p-3 font-mono text-xs text-foreground outline-none focus:ring-2 focus:ring-ring"
              spellCheck={false}
            />
          </label>
          <div className="min-h-0">
            <div className="mb-2 flex items-center justify-between gap-2">
              <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Inferred schema</span>
              <label className="inline-flex h-8 cursor-pointer items-center gap-2 rounded-md border border-border bg-background px-2 text-xs font-medium text-foreground hover:bg-accent">
                <FileJson className="size-3.5" />
                File
                <input type="file" accept="application/json,.json" onChange={handleFile} className="sr-only" />
              </label>
            </div>
            <pre className="h-72 overflow-auto rounded-md border border-border bg-muted/40 p-3 text-xs text-foreground">
              {schema ? JSON.stringify(schema, null, 2) : 'Invalid JSON object'}
            </pre>
          </div>
        </div>

        {error ? <div className="mx-4 mb-3 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</div> : null}

        <footer className="flex items-center justify-end gap-2 border-t border-border px-4 py-3">
          <button type="button" onClick={onClose} className="h-9 rounded-md border border-border bg-background px-3 text-sm font-medium text-foreground hover:bg-accent">
            Cancel
          </button>
          <button
            type="button"
            disabled={!parsed || validating}
            onClick={() => void validateAndSubmit()}
            className="inline-flex h-9 items-center gap-2 rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-45"
          >
            {validating ? <Loader2 className="size-4 animate-spin" /> : null}
            Validate input
          </button>
        </footer>
      </section>
    </div>
  )
}
