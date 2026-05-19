import { ChevronDown, Layers, Loader2, Sparkles } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { isTauriRuntime } from "@/config/runtime"
import { usePublishSkill } from "@/hooks/usePublishSkill"
import { useSkillSync } from "@/hooks/useSkillSync"
import type { CollaborateResult } from "@/api/types"

interface HeaderProps {
  skillId: string | null
  navStack?: string[]
  copilotOpen: boolean
  onCopilotToggle: () => void
  onHome: () => void
  onBreadcrumbClick?: (index: number) => void
  onSyncSuccess?: (result: CollaborateResult) => void
}

export function Header({
  skillId,
  navStack = skillId ? [skillId] : [],
  copilotOpen,
  onCopilotToggle,
  onHome,
  onBreadcrumbClick,
  onSyncSuccess,
}: HeaderProps) {
  const skillSync = useSkillSync(skillId, { onSyncSuccess })
  const publish = usePublishSkill(skillId)
  const isSaving = skillSync.status === "saving"
  const isSyncing = skillSync.status === "syncing"
  const isSubmitting = skillSync.status === "submitting"
  const isPublishing = publish.status === "publishing"
  const isBusy = isSaving || isSyncing || isSubmitting

  const handleSubmitForReview = () => {
    if (!skillId) return
    const devBranch = window.prompt("Dev branch", `review/${skillId}`)
    if (!devBranch) return
    const prTitle = window.prompt("PR title", `Review ${skillId}`)
    if (!prTitle) return
    void skillSync.submit(devBranch, prTitle)
  }

  return (
    <header
      data-tauri-drag-region
      className="grid h-11 shrink-0 grid-cols-3 items-center border-b border-border bg-background px-3"
    >
      <div className="flex items-center gap-2">
        {isTauriRuntime() ? (
          <div className="flex size-6 items-center justify-center rounded-md bg-foreground">
            <Layers className="size-3.5 text-background" strokeWidth={2} />
          </div>
        ) : (
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                onClick={onHome}
                aria-label="Back to Home"
                className="flex size-6 items-center justify-center rounded-md bg-foreground transition-opacity hover:opacity-80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
              >
                <Layers className="size-3.5 text-background" strokeWidth={2} />
              </button>
            </TooltipTrigger>
            <TooltipContent>Back to Home</TooltipContent>
          </Tooltip>
        )}
        <span className="text-sm font-semibold tracking-tight text-foreground">
          GSkill Studio
        </span>
      </div>

      <div className="flex min-w-0 items-center justify-center gap-2">
        {navStack.length > 0 ? (
          <nav className="flex min-w-0 items-center gap-1 text-sm font-medium text-foreground">
            {navStack.map((item, index) => (
              <span key={`${item}-${index}`} className="flex min-w-0 items-center gap-1">
                {index > 0 ? <span className="text-muted-foreground">/</span> : null}
                <button
                  type="button"
                  onClick={() => onBreadcrumbClick?.(index)}
                  className="truncate rounded-sm px-1 hover:bg-accent"
                >
                  {item}
                </button>
              </span>
            ))}
          </nav>
        ) : (
          <span className="truncate text-sm font-medium text-foreground">Studio Workspace</span>
        )}
        <Badge variant="outline" className="uppercase">
          Draft
        </Badge>
      </div>

      <div className="flex items-center justify-end gap-1.5">
        {skillId ? (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm" className="h-7 gap-1 text-xs" disabled={isBusy || isPublishing}>
                {(isBusy || isPublishing) ? <Loader2 className="size-3 animate-spin" /> : null}
                Team
                <ChevronDown className="size-3" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="min-w-44">
              <DropdownMenuItem disabled={isBusy} onClick={() => void skillSync.save()}>
                {isSaving ? <Loader2 className="size-3 animate-spin" /> : null}
                Save to Team
              </DropdownMenuItem>
              <DropdownMenuItem disabled={isBusy} onClick={() => void skillSync.sync()}>
                {isSyncing ? <Loader2 className="size-3 animate-spin" /> : null}
                Sync from Team
              </DropdownMenuItem>
              <DropdownMenuItem disabled={isBusy} onClick={handleSubmitForReview}>
                {isSubmitting ? <Loader2 className="size-3 animate-spin" /> : null}
                Submit for Review
              </DropdownMenuItem>
              <DropdownMenuItem disabled={isPublishing} onClick={() => void publish.publish()}>
                {isPublishing ? <Loader2 className="size-3 animate-spin" /> : null}
                Release
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        ) : null}
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              onClick={onCopilotToggle}
              aria-label={copilotOpen ? "Hide Copilot" : "Show Copilot"}
              aria-pressed={copilotOpen}
            >
              <Sparkles />
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            {copilotOpen ? "Hide Copilot" : "Show Copilot"}
          </TooltipContent>
        </Tooltip>
      </div>
    </header>
  )
}
