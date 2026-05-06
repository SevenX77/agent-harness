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
    <div className="grid grid-cols-2 overflow-hidden rounded-md border border-slate-200 text-xs dark:border-slate-800">
      <div className="border-r border-slate-200 dark:border-slate-800">
        <div className="bg-slate-100 px-3 py-1 font-semibold text-slate-600 dark:bg-slate-800 dark:text-slate-300">
          Golden
        </div>
        {lines(goldenValue).map((line, index) => (
          <pre
            key={`golden-${index}`}
            className="min-h-6 whitespace-pre-wrap px-3 py-1 font-mono text-slate-600 dark:text-slate-300"
          >
            {line || ' '}
          </pre>
        ))}
      </div>
      <div>
        <div className="bg-slate-100 px-3 py-1 font-semibold text-slate-600 dark:bg-slate-800 dark:text-slate-300">
          Current
        </div>
        {rows.map((row) => (
          <pre
            key={`current-${row.index}`}
            className={`min-h-6 whitespace-pre-wrap px-3 py-1 font-mono ${
              row.changed
                ? 'bg-amber-50 text-amber-900 dark:bg-amber-950/40 dark:text-amber-200'
                : 'text-slate-600 dark:text-slate-300'
            }`}
          >
            {row.line || ' '}
          </pre>
        ))}
      </div>
    </div>
  )
}
