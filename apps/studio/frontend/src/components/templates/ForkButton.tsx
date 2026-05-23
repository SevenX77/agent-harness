import { Copy } from 'lucide-react'
import { useMemo, useState } from 'react'
import type { SkillSummary } from '../../api/types'
import { SKILL_ID_PATTERN } from '../../hooks/useSkillCreator'
import { errorMessage } from '../../utils/errors'
import { Alert, AlertDescription } from '../ui/alert'
import { Button } from '../ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '../ui/dialog'
import { Input } from '../ui/input'
import { Label } from '../ui/label'

interface ForkButtonProps {
  skill: SkillSummary
  onForkSkill: (sourceSkillId: string, newSkillId: string) => Promise<void>
}

function defaultForkId(skillId: string): string {
  return `${skillId}-copy`
}

export function ForkButton({ skill, onForkSkill }: ForkButtonProps) {
  const [open, setOpen] = useState(false)
  const [newSkillId, setNewSkillId] = useState(defaultForkId(skill.id))
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const valid = useMemo(() => SKILL_ID_PATTERN.test(newSkillId), [newSkillId])

  const openDialog = () => {
    setNewSkillId(defaultForkId(skill.id))
    setError(null)
    setOpen(true)
  }

  const submit = async () => {
    if (!valid || submitting) {
      setError('Use lowercase letters, numbers, and hyphens. Start with a letter.')
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      await onForkSkill(skill.id, newSkillId)
      setOpen(false)
    } catch (forkError) {
      setError(errorMessage(forkError))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <>
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        onClick={(event) => {
          event.stopPropagation()
          openDialog()
        }}
        className="opacity-0 transition group-hover:opacity-100 hover:text-primary"
        title={`Fork ${skill.name}`}
      >
        <Copy />
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Fork Skill</DialogTitle>
            <DialogDescription>Clone {skill.id} into your workspace.</DialogDescription>
          </DialogHeader>

          <div className="space-y-2">
            <Label htmlFor={`fork-${skill.id}`}>New skill ID</Label>
            <Input
              id={`fork-${skill.id}`}
              value={newSkillId}
              autoCorrect="off"
              autoCapitalize="none"
              spellCheck={false}
              onChange={(event) => {
                setNewSkillId(event.target.value)
                setError(null)
              }}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  void submit()
                }
              }}
            />
            <p className="text-xs text-muted-foreground">
              Lowercase letters, numbers, and hyphens only.
            </p>
          </div>

          {error ? (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="button" disabled={!valid || submitting} onClick={() => void submit()}>
              {submitting ? 'Forking...' : 'Fork'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
