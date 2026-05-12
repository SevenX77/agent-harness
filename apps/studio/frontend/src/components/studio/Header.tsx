import { Layers, Sparkles } from 'lucide-react'

interface HeaderProps {
  skillId: string | null
  copilotOpen: boolean
  onCopilotToggle: () => void
}

export function Header({ skillId, copilotOpen, onCopilotToggle }: HeaderProps) {
  return (
    <header
      data-tauri-drag-region
      className="grid h-11 shrink-0 grid-cols-3 items-center border-b border-border bg-background px-3"
    >
      <div className="flex items-center gap-2">
        <div className="flex size-6 items-center justify-center rounded-md bg-foreground">
          <Layers className="size-3.5 text-background" strokeWidth={2} />
        </div>
        <span className="text-sm font-semibold tracking-tight text-foreground">
          GSkill Studio
        </span>
      </div>

      <div className="flex min-w-0 items-center justify-center gap-2">
        <span className="truncate text-sm text-muted-foreground">
          {skillId ? `Skill ${skillId}` : 'Studio Workspace'}
        </span>
        <span className="inline-flex h-5 w-fit shrink-0 items-center justify-center rounded-full border border-border bg-input/20 px-2 py-0.5 text-[0.625rem] font-medium uppercase text-foreground dark:bg-input/30">
          Draft
        </span>
      </div>

      <div className="flex items-center justify-end gap-1">
        <button
          type="button"
          aria-label={copilotOpen ? 'Hide Copilot' : 'Show Copilot'}
          aria-pressed={copilotOpen}
          title={copilotOpen ? 'Hide Copilot' : 'Show Copilot'}
          onClick={onCopilotToggle}
          className="inline-flex size-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          <Sparkles className="size-3.5" />
        </button>
      </div>
    </header>
  )
}
