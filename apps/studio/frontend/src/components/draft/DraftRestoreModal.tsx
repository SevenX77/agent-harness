import { AlertTriangle } from 'lucide-react'
import type { StoredDraft } from '../../hooks/useDraftPersist'
import { Alert, AlertDescription } from '../ui/alert'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogMedia,
  AlertDialogTitle,
} from '../ui/alert-dialog'

interface DraftRestoreModalProps {
  open: boolean
  skillId: string | null
  draft: StoredDraft | null
  baseHash: string
  onRestore: () => void
  onDiscard: () => void
  onCancel: () => void
}

function formatTime(timestamp: number): string {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(timestamp))
}

function lineCount(value: string): number {
  return value.split('\n').length
}

export function DraftRestoreModal({
  open,
  skillId,
  draft,
  baseHash,
  onRestore,
  onDiscard,
  onCancel,
}: DraftRestoreModalProps) {
  if (!open || !draft || !skillId) {
    return null
  }

  const baseChanged = draft.baseHash !== baseHash

  return (
    <AlertDialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen) {
          onCancel()
        }
      }}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogMedia>
            <AlertTriangle />
          </AlertDialogMedia>
          <AlertDialogTitle>Unsaved draft found</AlertDialogTitle>
          <AlertDialogDescription>
            Restore the local draft for {skillId}, or discard it and keep the saved file.
          </AlertDialogDescription>
        </AlertDialogHeader>

        <div className="grid gap-3 text-sm md:grid-cols-2">
          <DraftStat label="Saved" value={formatTime(draft.timestamp)} />
          <DraftStat label="Draft Size" value={`${lineCount(draft.content)} lines`} />
        </div>

        {baseChanged ? (
          <Alert>
            <AlertTriangle />
            <AlertDescription>
              The saved SKILL.md has changed since this draft was recorded. Review carefully after restoring.
            </AlertDescription>
          </Alert>
        ) : null}

        <AlertDialogFooter>
          <AlertDialogAction
            variant="destructive"
            onClick={(event) => {
              event.preventDefault()
              onDiscard()
            }}
          >
            Discard
          </AlertDialogAction>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            onClick={(event) => {
              event.preventDefault()
              onRestore()
            }}
          >
            Restore
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

function DraftStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border bg-muted/40 p-3">
      <div className="text-xs font-medium uppercase text-muted-foreground">{label}</div>
      <div className="mt-1 text-foreground">{value}</div>
    </div>
  )
}
