import { useEffect, useMemo, useState } from 'react'
import { Play, RotateCcw } from 'lucide-react'
import type { JsonObject } from '../../api/types'
import { useInputPlayground } from '../../hooks/useInputPlayground'
import type { PlaygroundInputSpec } from '../../hooks/useInputPlayground'
import type { RunStatus } from '../../types/studio'
import type { ToastKind } from '../../types/studio'
import { isJsonObject } from '../../utils/errors'
import { FieldRenderer } from './FieldRenderer'
import { PresetToolbar } from './PresetToolbar'

interface InputPlaygroundProps {
  skillId: string
  inputs: PlaygroundInputSpec[]
  runStatus: RunStatus
  onRun: (values: JsonObject) => void
  onPayloadChange: (values: JsonObject, isValid: boolean) => void
  pushToast: (message: string, kind?: ToastKind) => void
}

export function InputPlayground({
  skillId,
  inputs,
  runStatus,
  onRun,
  onPayloadChange,
  pushToast,
}: InputPlaygroundProps) {
  const playground = useInputPlayground(inputs)
  const [showPreview, setShowPreview] = useState(false)
  const [rawJson, setRawJson] = useState('{}')
  const [rawError, setRawError] = useState<string | null>(null)
  const hasDeclaredInputs = inputs.length > 0

  const rawPayload = useMemo(() => {
    try {
      const parsed: unknown = JSON.parse(rawJson)
      return isJsonObject(parsed) ? parsed : null
    } catch {
      return null
    }
  }, [rawJson])

  const payload = hasDeclaredInputs ? playground.values : rawPayload
  const isValid = hasDeclaredInputs ? playground.isValid : rawPayload !== null && rawError === null

  useEffect(() => {
    onPayloadChange(payload ?? {}, isValid)
  }, [isValid, onPayloadChange, payload])

  return (
    <div className="flex max-h-[70vh] w-[34rem] flex-col rounded-md border border-border bg-card shadow-xl">
      <div className="flex shrink-0 items-center justify-between border-b border-border px-4 py-3">
        <div>
          <h4 className="font-bold text-foreground">Run Input</h4>
          <p className="text-xs text-muted-foreground">{skillId}</p>
        </div>
        <div className="flex items-center gap-2">
          <PresetToolbar
            skillId={skillId}
            values={payload ?? {}}
            onLoad={(values) => {
              if (hasDeclaredInputs) {
                playground.setValues(values)
              } else {
                setRawJson(JSON.stringify(values, null, 2))
                setRawError(null)
              }
            }}
            pushToast={pushToast}
          />
          <button
            type="button"
            onClick={() => {
              playground.reset()
              setRawJson('{}')
              setRawError(null)
            }}
            className="flex items-center gap-1 rounded-md border border-border px-2 py-1 text-xs font-medium text-muted-foreground hover:bg-muted/40"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            Reset
          </button>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        {hasDeclaredInputs ? (
          <div className="space-y-3">
            {inputs.map((input) => (
              <FieldRenderer
                key={input.name}
                input={input}
                value={playground.values[input.name]}
                error={playground.errors[input.name]}
                onChange={(value) => playground.setValue(input.name, value)}
              />
            ))}
          </div>
        ) : (
          <label className="block">
            <span className="mb-1 block text-sm font-semibold text-foreground">Raw JSON</span>
            <textarea
              value={rawJson}
              onChange={(event) => {
                const next = event.target.value
                setRawJson(next)
                try {
                  const parsed: unknown = JSON.parse(next)
                  setRawError(isJsonObject(parsed) ? null : 'JSON must be an object.')
                } catch {
                  setRawError('Invalid JSON object.')
                }
              }}
              className="h-40 w-full resize-none rounded-md border border-input bg-input/20 px-3 py-2 font-mono text-xs focus:outline-none focus:ring-2 focus:ring-ring/50"
            />
            {rawError ? <span className="mt-1 block text-xs text-destructive">{rawError}</span> : null}
          </label>
        )}

        <button
          type="button"
          onClick={() => setShowPreview((open) => !open)}
          className="mt-4 text-xs font-medium text-primary hover:text-primary/80"
        >
          {showPreview ? 'Hide JSON preview' : 'Show JSON preview'}
        </button>
        {showPreview ? (
          <pre className="mt-2 max-h-48 overflow-auto rounded-md bg-muted/30 p-3 text-xs text-foreground">
            {JSON.stringify(payload ?? {}, null, 2)}
          </pre>
        ) : null}
      </div>

      <div className="flex shrink-0 items-center justify-between border-t border-border px-4 py-3">
        <span className={`text-xs font-medium ${isValid ? 'text-success' : 'text-destructive'}`}>
          {isValid ? 'Inputs valid' : 'Resolve input errors before running'}
        </span>
        <button
          type="button"
          data-testid="input-playground-run"
          disabled={!isValid || runStatus === 'running'}
          onClick={() => {
            const submitted = hasDeclaredInputs ? playground.submitInputs() : rawPayload
            if (submitted) {
              onRun(submitted)
            }
          }}
          className="flex items-center gap-2 rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/85 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Play className="h-4 w-4" />
          {runStatus === 'running' ? 'Running...' : 'Run'}
        </button>
      </div>
    </div>
  )
}
