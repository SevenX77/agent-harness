import type { JsonValue } from '../../api/types'

interface NumberDiffViewProps {
  currentValue: JsonValue
  goldenValue: JsonValue
}

function numberValue(value: JsonValue): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

export function NumberDiffView({ currentValue, goldenValue }: NumberDiffViewProps) {
  const current = numberValue(currentValue)
  const golden = numberValue(goldenValue)
  const delta = current !== null && golden !== null ? current - golden : null
  const percent = delta !== null && golden !== null && golden !== 0 ? (delta / golden) * 100 : null

  return (
    <div className="grid grid-cols-3 gap-2 text-sm">
      <div className="rounded-md bg-slate-100 p-3 dark:bg-slate-800">
        <div className="text-xs font-semibold uppercase text-slate-500 dark:text-slate-400">Golden</div>
        <div className="mt-1 font-mono text-slate-800 dark:text-slate-100">{golden ?? 'n/a'}</div>
      </div>
      <div className="rounded-md bg-slate-100 p-3 dark:bg-slate-800">
        <div className="text-xs font-semibold uppercase text-slate-500 dark:text-slate-400">Current</div>
        <div className="mt-1 font-mono text-slate-800 dark:text-slate-100">{current ?? 'n/a'}</div>
      </div>
      <div className={`rounded-md p-3 ${delta === 0 ? 'bg-green-50 dark:bg-green-950/40' : 'bg-amber-50 dark:bg-amber-950/40'}`}>
        <div className="text-xs font-semibold uppercase text-slate-500 dark:text-slate-400">Delta</div>
        <div className="mt-1 font-mono text-slate-800 dark:text-slate-100">
          {delta === null ? 'n/a' : `${delta > 0 ? '+' : ''}${delta}`}
        </div>
        {percent !== null ? (
          <div className="text-xs text-slate-500 dark:text-slate-400">
            {percent > 0 ? '+' : ''}{percent.toFixed(1)}%
          </div>
        ) : null}
      </div>
    </div>
  )
}
