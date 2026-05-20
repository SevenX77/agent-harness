import type { FormEvent } from 'react'
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
  newSkillError: string | null
  creating: boolean
  onSubmit: (event?: FormEvent) => void
}

export function NewSkillDialog({
  open,
  onOpenChange,
  newSkillName,
  onNewSkillNameChange,
  newSkillError,
  creating,
  onSubmit,
}: NewSkillDialogProps) {
  return (
          <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent>
              <form onSubmit={(event) => void onSubmit(event)}>
                <DialogHeader>
                  <DialogTitle>New skill</DialogTitle>
                  <DialogDescription>
                    A folder will be created under AgentStudio/Skills with a starter SKILL.md.
                  </DialogDescription>
                </DialogHeader>
                <div className="my-4 space-y-2">
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
                    <p className="text-xs text-destructive">{newSkillError}</p>
                  ) : (
                    <p className="text-xs text-muted-foreground">
                      Will be normalized to <span className="font-mono">{normalizeSkillId(newSkillName || 'new-skill')}</span>
                    </p>
                  )}
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
