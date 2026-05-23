import { FileJson, Loader2 } from 'lucide-react'
import { useMemo, useState, type ChangeEvent } from 'react'
import type { JsonObject } from '../../api/types'
import { useInputPlayground, type PlaygroundInputSpec } from '../../hooks/useInputPlayground'
import { inferJsonSchema } from '../../lib/schema-infer'
import { errorMessage, isJsonObject } from '../../utils/errors'
import { Alert, AlertDescription } from '../ui/alert'
import { Button } from '../ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '../ui/dialog'
import { Textarea } from '../ui/textarea'

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
    <Dialog
      open
      onOpenChange={(nextOpen) => {
        if (!nextOpen) {
          onClose()
        }
      }}
    >
      <DialogContent className="flex max-h-[82vh] max-w-2xl flex-col overflow-hidden p-0 sm:max-w-2xl">
        <DialogHeader className="border-b border-border px-4 py-3">
          <DialogTitle>Predict input</DialogTitle>
          <DialogDescription>{inputs.length || 'Raw'} declared input fields</DialogDescription>
        </DialogHeader>

        <div className="grid min-h-0 flex-1 gap-4 overflow-auto p-4 md:grid-cols-2">
          <label className="min-h-0">
            <span className="mb-2 block text-xs font-medium uppercase text-muted-foreground">
              JSON payload
            </span>
            <Textarea
              value={rawJson}
              onChange={(event) => {
                setRawJson(event.target.value)
                setError(null)
              }}
              className="h-72 font-mono text-xs"
              spellCheck={false}
            />
          </label>
          <div className="min-h-0">
            <div className="mb-2 flex items-center justify-between gap-2">
              <span className="text-xs font-medium uppercase text-muted-foreground">
                Inferred schema
              </span>
              <Button variant="outline" size="sm" asChild>
                <label>
                  <FileJson />
                  File
                  <input type="file" accept="application/json,.json" onChange={handleFile} className="sr-only" />
                </label>
              </Button>
            </div>
            <pre className="h-72 overflow-auto rounded-md border border-border bg-muted/40 p-3 text-xs text-foreground">
              {schema ? JSON.stringify(schema, null, 2) : 'Invalid JSON object'}
            </pre>
          </div>
        </div>

        {error ? (
          <Alert variant="destructive" className="mx-4">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : null}

        <DialogFooter className="border-t border-border px-4 py-3">
          <Button type="button" variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="button" disabled={!parsed || validating} onClick={() => void validateAndSubmit()}>
            {validating ? <Loader2 className="animate-spin" /> : null}
            Validate input
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
