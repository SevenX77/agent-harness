import { ArrowLeft, Circle, Code2, SquareTerminal, WandSparkles } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { openInCodex, openInCursor, openInTerminal } from '../../lib/tauri'

export function Header() {
  const { skillId } = useParams()
  const skillPath = skillId ?? ''

  return (
    <header
      data-tauri-drag-region
      className="grid h-11 shrink-0 grid-cols-3 items-center border-b border-border bg-background px-3"
    >
      <div className="flex items-center">
        <Link
          to="/"
          className="inline-flex h-8 items-center gap-1.5 rounded-md px-2 text-xs font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          aria-label="Back to Home"
        >
          <ArrowLeft className="size-3.5" />
          Back to Home
        </Link>
      </div>

      <div className="flex min-w-0 items-center justify-center gap-2">
        <span className="truncate text-sm font-medium text-foreground">
          {skillId ? `Skill ${skillId}` : 'Studio Workspace'}
        </span>
        <span className="inline-flex h-5 items-center gap-1 rounded-full bg-secondary px-2 text-[0.625rem] font-medium uppercase text-secondary-foreground">
          <Circle className="size-2 fill-current" />
          Draft
        </span>
      </div>

      <div className="flex items-center justify-end gap-1">
        <button
          type="button"
          aria-label="Open in Cursor"
          title="Open in Cursor"
          onClick={() => void openInCursor(skillPath)}
          className="inline-flex min-h-8 min-w-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
        >
          <Code2 className="size-4" />
        </button>
        <button
          type="button"
          aria-label="Open in Terminal"
          title="Open in Terminal"
          onClick={() => void openInTerminal(skillPath)}
          className="inline-flex min-h-8 min-w-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
        >
          <SquareTerminal className="size-4" />
        </button>
        <button
          type="button"
          aria-label="Open in Codex"
          title="Open in Codex"
          onClick={() => void openInCodex(skillPath)}
          className="inline-flex min-h-8 min-w-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
        >
          <WandSparkles className="size-4" />
        </button>
      </div>
    </header>
  )
}
