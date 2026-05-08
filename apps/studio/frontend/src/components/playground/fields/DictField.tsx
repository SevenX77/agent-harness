import { useEffect, useState } from 'react'
import type { JsonValue } from '../../../api/types'
import { isJsonObject } from '../../../utils/errors'
import type { FieldProps } from './types'
import { FieldWrapper } from './FieldWrapper'

function textFor(value: JsonValue | undefined): string {
  if (value === undefined || value === null) {
    return '{}'
  }
  return JSON.stringify(value, null, 2)
}

export function DictField({ input, value, error, onChange }: FieldProps) {
  const [raw, setRaw] = useState(textFor(value))
  const [parseError, setParseError] = useState<string | null>(null)

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setRaw(textFor(value))
  }, [value])

  return (
    <FieldWrapper input={input} error={parseError ?? error}>
      <textarea
        value={raw}
        onChange={(event) => {
          const next = event.target.value
          setRaw(next)
          try {
            const parsed: unknown = JSON.parse(next)
            if (!isJsonObject(parsed)) {
              setParseError('JSON must be an object.')
              return
            }
            setParseError(null)
            onChange(parsed)
          } catch {
            setParseError('Invalid JSON object.')
          }
        }}
        className="h-32 w-full resize-none rounded-md border border-gray-300 px-3 py-2 font-mono text-xs focus:outline-none focus:ring-2 focus:ring-sky-500 dark:border-slate-700 dark:bg-slate-800"
      />
    </FieldWrapper>
  )
}
