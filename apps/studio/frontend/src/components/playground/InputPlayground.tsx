import { useEffect, useMemo, useState } from 'react'
import { Play, RotateCcw } from 'lucide-react'
import type { JsonObject } from '../../api/types'
import { useInputPlayground } from '../../hooks/useInputPlayground'
import type { PlaygroundInputSpec } from '../../hooks/useInputPlayground'
import type { RunStatus } from '../../types/studio'
import { isJsonObject } from '../../utils/errors'
import { FieldRenderer } from './FieldRenderer'

interface InputPlaygroundProps {
  skillId: string
  inputs: PlaygroundInputSpec[]
  runStatus: RunStatus
  onRun: (values: JsonObject) => void
  onPayloadChange: (values: JsonObject, isValid: boolean) => void
  toolbarSlot?: React.ReactNode
}

export function InputPlayground({
  skillId,
  inputs,
  runStatus,
  onRun,
  onPayloadChange,
  toolbarSlot,
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
    <div className="flex max-h-[70vh] w-[34rem] flex-col rounded-md border border-gray-200 bg-white shadow-xl dark:border-slate-800 dark:bg-slate-900">
      <div className="flex shrink-0 items-center justify-between border-b border-gray-200 px-4 py-3 dark:border-slate-800">
        <div>
          <h4 className="font-bold text-gray-800 dark:text-gray-100">Run Input</h4>
          <p className="text-xs text-gray-500 dark:text-gray-400">{skillId}</p>
        </div>
        <div className="flex items-center gap-2">
          {toolbarSlot}
          <button
            type="button"
            onClick={() => {
              playground.reset()
              setRawJson('{}')
              setRawError(null)
            }}
            className="flex items-center gap-1 rounded-md border border-gray-300 px-2 py-1 text-xs font-medium text-gray-600 hover:bg-gray-50 dark:border-slate-700 dark:text-gray-300 dark:hover:bg-slate-800"
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
            <span className="mb-1 block text-sm font-semibold text-gray-800 dark:text-gray-200">Raw JSON</span>
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
              className="h-40 w-full resize-none rounded-md border border-gray-300 px-3 py-2 font-mono text-xs focus:outline-none focus:ring-2 focus:ring-sky-500 dark:border-slate-700 dark:bg-slate-800"
            />
            {rawError ? <span className="mt-1 block text-xs text-red-600 dark:text-red-400">{rawError}</span> : null}
          </label>
        )}

        <button
          type="button"
          onClick={() => setShowPreview((open) => !open)}
          className="mt-4 text-xs font-medium text-sky-600 hover:text-sky-700 dark:text-sky-400 dark:hover:text-sky-300"
        >
          {showPreview ? 'Hide JSON preview' : 'Show JSON preview'}
        </button>
        {showPreview ? (
          <pre className="mt-2 max-h-48 overflow-auto rounded-md bg-slate-950 p-3 text-xs text-slate-100">
            {JSON.stringify(payload ?? {}, null, 2)}
          </pre>
        ) : null}
      </div>

      <div className="flex shrink-0 items-center justify-between border-t border-gray-200 px-4 py-3 dark:border-slate-800">
        <span className={`text-xs font-medium ${isValid ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
          {isValid ? 'Inputs valid' : 'Resolve input errors before running'}
        </span>
        <button
          type="button"
          disabled={!isValid || runStatus === 'running'}
          onClick={() => {
            const submitted = hasDeclaredInputs ? playground.submitInputs() : rawPayload
            if (submitted) {
              onRun(submitted)
            }
          }}
          className="flex items-center gap-2 rounded-md bg-sky-600 px-4 py-1.5 text-sm font-medium text-white transition-colors hover:bg-sky-700 disabled:cursor-not-allowed disabled:bg-sky-300 dark:disabled:bg-sky-900"
        >
          <Play className="h-4 w-4" />
          {runStatus === 'running' ? 'Running...' : 'Run'}
        </button>
      </div>
    </div>
  )
}
