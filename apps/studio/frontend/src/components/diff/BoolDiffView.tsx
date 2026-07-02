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
      <div className="rounded-md bg-muted/40 p-3">
        <div className="text-xs font-semibold uppercase text-muted-foreground">Golden</div>
        <div className="mt-1 font-mono text-foreground">{label(goldenValue)}</div>
      </div>
      <div className={`rounded-md p-3 ${changed ? 'bg-warning/10' : 'bg-success/10'}`}>
        <div className="text-xs font-semibold uppercase text-muted-foreground">Current</div>
        <div className="mt-1 font-mono text-foreground">{label(currentValue)}</div>
      </div>
    </div>
  )
}
