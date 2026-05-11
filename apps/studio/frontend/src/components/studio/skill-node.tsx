import { AlertTriangle, Lock, Pause, RotateCw } from 'lucide-react'

export type DebugNodeState = 'paused' | 'error'

interface SkillNodeProps {
  name: string
  state: DebugNodeState
  summary: string
  resumeDisabled?: boolean
  onResume: () => void
}

export function SkillNode({ name, state, summary, resumeDisabled = false, onResume }: SkillNodeProps) {
  const Icon = state === 'paused' ? Pause : AlertTriangle

  return (
    <div className="rounded-md border border-amber-400 bg-amber-500/10 p-4 text-foreground shadow-sm ring-2 ring-amber-300/50 dark:border-amber-700 dark:ring-amber-700/40">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <div className="flex size-9 shrink-0 items-center justify-center rounded-md bg-amber-500/15 text-amber-700 dark:text-amber-300">
            <Icon className="size-4" />
          </div>
          <div className="min-w-0">
            <h3 className="truncate text-sm font-semibold text-foreground">{name}</h3>
            <p className="mt-1 text-xs text-muted-foreground">{summary}</p>
          </div>
        </div>
        <span className="inline-flex items-center gap-1 rounded-md border border-amber-400/40 bg-background px-2 py-1 text-xs font-medium text-amber-700 dark:text-amber-300">
          <Lock className="size-3.5" />
          {state}
        </span>
      </div>
      <button
        type="button"
        disabled={resumeDisabled}
        onClick={onResume}
        className="mt-4 inline-flex h-8 items-center gap-2 rounded-md border border-amber-400/50 bg-background px-3 text-xs font-medium text-foreground hover:bg-accent disabled:cursor-not-allowed disabled:opacity-45"
      >
        <RotateCw className="size-3.5" />
        Resume
      </button>
    </div>
  )
}
