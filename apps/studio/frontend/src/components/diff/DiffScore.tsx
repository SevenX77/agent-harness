import { Tooltip, TooltipContent, TooltipTrigger } from '../ui/tooltip'

interface DiffScoreProps {
  score: number
  compact?: boolean
}

function scoreColorVar(score: number): string {
  if (score >= 90) {
    return 'var(--success)'
  }
  if (score >= 70) {
    return 'var(--warning)'
  }
  return 'var(--destructive)'
}

export function DiffScore({ score, compact = false }: DiffScoreProps) {
  const clamped = Math.max(0, Math.min(100, score))
  const sizeClass = compact ? 'h-12 w-12 text-xs' : 'h-20 w-20 text-sm'
  const color = scoreColorVar(clamped)

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div
          aria-label={`Diff score ${clamped.toFixed(1)}%`}
          className={`${sizeClass} grid shrink-0 place-items-center rounded-full font-bold text-foreground shadow-sm`}
          style={{
            background: `conic-gradient(${color} ${clamped}%, var(--muted) ${clamped}% 100%)`,
          }}
        >
          <div className="grid h-[76%] w-[76%] place-items-center rounded-full bg-card">
            {Math.round(clamped)}%
          </div>
        </div>
      </TooltipTrigger>
      <TooltipContent>Diff score {clamped.toFixed(1)}%</TooltipContent>
    </Tooltip>
  )
}
