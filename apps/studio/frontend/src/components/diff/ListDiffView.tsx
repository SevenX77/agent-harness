import type { ReactNode } from 'react'
import type { JsonValue } from '../../api/types'

interface ListDiffViewProps {
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

export function ListDiffView({
  currentValue,
  goldenValue,
  fieldPath,
  depth,
  renderChild,
}: ListDiffViewProps) {
  const current = Array.isArray(currentValue) ? currentValue : []
  const golden = Array.isArray(goldenValue) ? goldenValue : []
  const count = Math.max(current.length, golden.length)

  if (count === 0) {
    return <div className="text-xs text-slate-500 dark:text-slate-400">Empty list.</div>
  }

  return (
    <div className="space-y-2">
      {Array.from({ length: count }, (_, index) => (
        <div key={index} className="rounded-md border border-slate-200 p-2 dark:border-slate-800">
          {renderChild(
            `${fieldPath}[${index}]`,
            current[index] ?? null,
            golden[index] ?? null,
            depth + 1,
          )}
        </div>
      ))}
    </div>
  )
}
