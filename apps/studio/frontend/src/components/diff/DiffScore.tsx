interface DiffScoreProps {
  score: number
  compact?: boolean
}

function scoreColor(score: number): string {
  if (score >= 90) {
    return '#16a34a'
  }
  if (score >= 70) {
    return '#ca8a04'
  }
  return '#dc2626'
}

export function DiffScore({ score, compact = false }: DiffScoreProps) {
  const clamped = Math.max(0, Math.min(100, score))
  const sizeClass = compact ? 'h-12 w-12 text-xs' : 'h-20 w-20 text-sm'
  const color = scoreColor(clamped)

  return (
    <div
      className={`${sizeClass} grid shrink-0 place-items-center rounded-full font-bold text-slate-900 shadow-sm dark:text-slate-100`}
      style={{
        background: `conic-gradient(${color} ${clamped}%, rgb(226 232 240) ${clamped}% 100%)`,
      }}
      title={`Diff score ${clamped.toFixed(1)}%`}
    >
      <div className="grid h-[76%] w-[76%] place-items-center rounded-full bg-white dark:bg-slate-900">
        {Math.round(clamped)}%
      </div>
    </div>
  )
}
