import type { JsonValue } from '../../api/types'

interface TextDiffViewProps {
  currentValue: JsonValue
  goldenValue: JsonValue
}

interface TextLine {
  line: string
  index: number
  changed: boolean
}

function lines(value: JsonValue): string[] {
  return String(value ?? '').split('\n')
}

function compareLines(currentValue: JsonValue, goldenValue: JsonValue): TextLine[] {
  const current = lines(currentValue)
  const golden = lines(goldenValue)
  const max = Math.max(current.length, golden.length)
  return Array.from({ length: max }, (_, index) => ({
    line: current[index] ?? '',
    index,
    changed: (current[index] ?? '') !== (golden[index] ?? ''),
  }))
}

export function TextDiffView({ currentValue, goldenValue }: TextDiffViewProps) {
  const rows = compareLines(currentValue, goldenValue)

  return (
    <div className="grid grid-cols-2 overflow-hidden rounded-md border border-border text-xs">
      <div className="border-r border-border">
        <div className="bg-muted px-3 py-1 font-semibold text-muted-foreground">
          Golden
        </div>
        {lines(goldenValue).map((line, index) => (
          <pre
            key={`golden-${index}`}
            className="min-h-6 whitespace-pre-wrap px-3 py-1 font-mono text-muted-foreground"
          >
            {line || ' '}
          </pre>
        ))}
      </div>
      <div>
        <div className="bg-muted px-3 py-1 font-semibold text-muted-foreground">
          Current
        </div>
        {rows.map((row) => (
          <pre
            key={`current-${row.index}`}
            className={`min-h-6 whitespace-pre-wrap px-3 py-1 font-mono ${
              row.changed
                ? 'bg-warning-background text-warning-foreground'
                : 'text-muted-foreground'
            }`}
          >
            {row.line || ' '}
          </pre>
        ))}
      </div>
    </div>
  )
}
