import type { JsonValue } from '../../api/types'

interface BoolDiffViewProps {
  currentValue: JsonValue
  goldenValue: JsonValue
}

function label(value: JsonValue): string {
  return typeof value === 'boolean' ? String(value) : 'n/a'
}

export function BoolDiffView({ currentValue, goldenValue }: BoolDiffViewProps) {
  const changed = currentValue !== goldenValue
  return (
    <div className="grid grid-cols-2 gap-2 text-sm">
      <div className="rounded-md bg-slate-100 p-3 dark:bg-slate-800">
        <div className="text-xs font-semibold uppercase text-slate-500 dark:text-slate-400">Golden</div>
        <div className="mt-1 font-mono text-slate-800 dark:text-slate-100">{label(goldenValue)}</div>
      </div>
      <div className={`rounded-md p-3 ${changed ? 'bg-amber-50 dark:bg-amber-950/40' : 'bg-green-50 dark:bg-green-950/40'}`}>
        <div className="text-xs font-semibold uppercase text-slate-500 dark:text-slate-400">Current</div>
        <div className="mt-1 font-mono text-slate-800 dark:text-slate-100">{label(currentValue)}</div>
      </div>
    </div>
  )
}
