import type { FormEvent } from 'react'
import { FolderOpen } from 'lucide-react'
import { Button } from '../ui/button'
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '../ui/dialog'
import { Input } from '../ui/input'
import { Label } from '../ui/label'
import { normalizeSkillId } from './utils'

interface NewSkillDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  newSkillName: string
  onNewSkillNameChange: (value: string) => void
  parentDirectory: string | null
  selectingParentDirectory: boolean
  onChooseParentDirectory: () => void
  newSkillError: string | null
  creating: boolean
  onSubmit: (event?: FormEvent) => void
}

export function NewSkillDialog({
  open,
  onOpenChange,
  newSkillName,
  onNewSkillNameChange,
  parentDirectory,
  selectingParentDirectory,
  onChooseParentDirectory,
  newSkillError,
  creating,
  onSubmit,
}: NewSkillDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[min(calc(100vw-2rem),28rem)] rounded-md border border-border bg-popover p-4 shadow-xl ring-0 sm:max-w-md">
        <form onSubmit={(event) => void onSubmit(event)}>
          <DialogHeader>
            <DialogTitle>New skill</DialogTitle>
            <DialogDescription>
              Creates a local skill folder with starter files.
            </DialogDescription>
          </DialogHeader>
          <div className="my-4 space-y-4">
            <div className="space-y-2">
              <Label htmlFor="new-skill-name">Skill name</Label>
              <Input
                id="new-skill-name"
                autoFocus
                value={newSkillName}
                onChange={(event) => onNewSkillNameChange(event.target.value)}
                placeholder="my-new-skill"
                aria-invalid={Boolean(newSkillError)}
                disabled={creating}
              />
              {newSkillError ? (
                <p className="rounded-md border border-destructive/30 bg-destructive/10 px-2 py-1.5 text-xs text-destructive">
                  {newSkillError}
                </p>
              ) : (
                <p className="text-xs text-muted-foreground">
                  Folder name: <span className="font-mono">{normalizeSkillId(newSkillName || 'new-skill')}</span>
                </p>
              )}
            </div>
            <div className="space-y-2">
              <Label>Parent folder</Label>
              <div className="grid gap-2 sm:grid-cols-[auto_minmax(0,1fr)] sm:items-center">
                <Button
                  type="button"
                  variant="outline"
                  onClick={onChooseParentDirectory}
                  disabled={creating || selectingParentDirectory}
                >
                  <FolderOpen />
                  {selectingParentDirectory ? 'Choosing' : 'Choose folder'}
                </Button>
                <p
                  title={parentDirectory ?? undefined}
                  className="min-w-0 truncate rounded-md border border-border bg-muted/30 px-2 py-1.5 text-xs text-muted-foreground"
                >
                  {parentDirectory ?? 'Default: AgentStudio/Skills'}
                </p>
              </div>
            </div>
          </div>
          <DialogFooter>
            <DialogClose asChild>
              <Button type="button" variant="outline" disabled={creating}>
                Cancel
              </Button>
            </DialogClose>
            <Button type="submit" disabled={creating || !newSkillName.trim()}>
              {creating ? 'Creating' : 'Create'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
