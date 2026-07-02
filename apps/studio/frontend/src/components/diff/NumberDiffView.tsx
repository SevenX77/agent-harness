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
      <div className="rounded-md bg-muted/40 p-3">
        <div className="text-xs font-semibold uppercase text-muted-foreground">Golden</div>
        <div className="mt-1 font-mono text-foreground">{golden ?? 'n/a'}</div>
      </div>
      <div className="rounded-md bg-muted/40 p-3">
        <div className="text-xs font-semibold uppercase text-muted-foreground">Current</div>
        <div className="mt-1 font-mono text-foreground">{current ?? 'n/a'}</div>
      </div>
      <div className={`rounded-md p-3 ${delta === 0 ? 'bg-success/10' : 'bg-warning/10'}`}>
        <div className="text-xs font-semibold uppercase text-muted-foreground">Delta</div>
        <div className="mt-1 font-mono text-foreground">
          {delta === null ? 'n/a' : `${delta > 0 ? '+' : ''}${delta}`}
        </div>
        {percent !== null ? (
          <div className="text-xs text-muted-foreground">
            {percent > 0 ? '+' : ''}{percent.toFixed(1)}%
          </div>
        ) : null}
      </div>
    </div>
  )
}
