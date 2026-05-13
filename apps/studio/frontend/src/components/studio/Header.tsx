import { Layers, Loader2, Sparkles } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { useSkillSync } from "@/hooks/useSkillSync"

interface HeaderProps {
  skillId: string | null
  copilotOpen: boolean
  onCopilotToggle: () => void
}

export function Header({ skillId, copilotOpen, onCopilotToggle }: HeaderProps) {
  const skillSync = useSkillSync(skillId)
  const isSaving = skillSync.status === "saving"
  const isSyncing = skillSync.status === "syncing"
  const isSubmitting = skillSync.status === "submitting"
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
        <div className="flex size-6 items-center justify-center rounded-md bg-foreground">
          <Layers className="size-3.5 text-background" strokeWidth={2} />
        </div>
        <span className="text-sm font-semibold tracking-tight text-foreground">
          GSkill Studio
        </span>
      </div>

      <div className="flex min-w-0 items-center justify-center gap-2">
        <span className="truncate text-sm font-medium text-foreground">
          {skillId ? `Skill ${skillId}` : "Studio Workspace"}
        </span>
        <Badge variant="outline" className="uppercase">
          Draft
        </Badge>
      </div>

      <div className="flex items-center justify-end gap-1.5">
        {skillId ? (
          <>
            <Button
              variant="outline"
              size="sm"
              className="h-7 text-xs"
              onClick={() => void skillSync.save()}
              disabled={isBusy}
              aria-label="Save to Team"
            >
              {isSaving ? <Loader2 className="mr-1 size-3 animate-spin" /> : null}
              {isSaving ? "Saving" : "Save to Team"}
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="h-7 text-xs"
              onClick={() => void skillSync.sync()}
              disabled={isBusy}
              aria-label="Sync from Team"
            >
              {isSyncing ? <Loader2 className="mr-1 size-3 animate-spin" /> : null}
              {isSyncing ? "Syncing" : "Sync from Team"}
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="h-7 text-xs"
              onClick={handleSubmitForReview}
              disabled={isBusy}
              aria-label="Submit for Review"
            >
              {isSubmitting ? <Loader2 className="mr-1 size-3 animate-spin" /> : null}
              {isSubmitting ? "Submitting" : "Submit for Review"}
            </Button>
          </>
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
