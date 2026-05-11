import { AlertTriangle, CheckCircle2, Loader2 } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useDebouncedLint } from '../../hooks/useDebouncedLint'

interface CompilationWidgetProps {
  skillId: string
  markdown: string
}

export function CompilationWidget({ skillId, markdown }: CompilationWidgetProps) {
  const { status, result, message } = useDebouncedLint(skillId, markdown)
  const locked = status === 'checking' || status === 'failed'
  const statusLabel = status === 'checking' ? 'Linting' : status === 'passed' ? 'Passed' : status === 'failed' ? 'Failed' : 'Idle'

  return (
    <section className="flex min-h-0 items-center justify-between gap-4 border-t border-border bg-card px-3 py-2">
      <div className="min-w-0">
        <div className="flex items-center gap-2 text-sm font-medium text-foreground">
          {status === 'checking' ? <Loader2 className="size-4 animate-spin text-primary" /> : null}
          {status === 'passed' ? <CheckCircle2 className="size-4 text-emerald-600 dark:text-emerald-400" /> : null}
          {status === 'failed' ? <AlertTriangle className="size-4 text-destructive" /> : null}
          <span>Compile guard: {statusLabel}</span>
        </div>
        <p className="mt-1 truncate text-xs text-muted-foreground">
          {message ?? result?.errors[0]?.message ?? 'POST /skills/{id}/lint after 800ms idle'}
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        {(['predict', 'run'] as const).map((target) => (
          locked ? (
            <span
              key={target}
              aria-disabled="true"
              className="inline-flex h-8 items-center rounded-md border border-border bg-muted px-3 text-xs font-medium text-muted-foreground opacity-60"
            >
              {target}
            </span>
          ) : (
            <Link
              key={target}
              to={`/skill/${skillId}/${target}`}
              className="inline-flex h-8 items-center rounded-md border border-border bg-background px-3 text-xs font-medium text-foreground hover:bg-accent"
            >
              {target}
            </Link>
          )
        ))}
      </div>
    </section>
  )
}
