import type { ReactNode } from 'react'
import type { JsonObject, JsonValue } from '../../api/types'
import { isJsonObject } from '../../utils/errors'

interface DictDiffViewProps {
  currentValue: JsonValue
  goldenValue: JsonValue
  fieldPath: string
  depth: number
  renderChild: (
    fieldPath: string,
    currentValue: JsonValue,
    goldenValue: JsonValue,
    depth: number,
  ) => ReactNode
}

function objectValue(value: JsonValue): JsonObject {
  return isJsonObject(value) ? value : {}
}

export function DictDiffView({
  currentValue,
  goldenValue,
  fieldPath,
  depth,
  renderChild,
}: DictDiffViewProps) {
  const current = objectValue(currentValue)
  const golden = objectValue(goldenValue)
  const keys = Array.from(new Set([...Object.keys(current), ...Object.keys(golden)])).sort()

  if (keys.length === 0) {
    return <div className="text-xs text-muted-foreground">Empty object.</div>
  }

  return (
    <div className="space-y-2">
      {keys.map((key) => (
        <div key={key} className="rounded-md border border-border p-2">
          {renderChild(`${fieldPath}.${key}`, current[key] ?? null, golden[key] ?? null, depth + 1)}
        </div>
      ))}
    </div>
  )
}
