import { AlertTriangle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { CONFLICT_ICON_CLASS, CONFLICT_TITLE, CONFLICT_VERB } from './conflict-vocabulary'
import type { SaveConflict } from './WorkspaceContext'

interface ConflictDialogProps {
  conflict: SaveConflict | null
  onCancel: () => void
  onUseRemote: () => void
  onViewDiff: () => void
  onOverwriteRetry: () => void
}

export function ConflictDialog({ conflict, onCancel, onUseRemote, onViewDiff, onOverwriteRetry }: ConflictDialogProps) {
  return (
    <Dialog open={Boolean(conflict)}>
      <DialogContent showCloseButton={false}>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <AlertTriangle className={CONFLICT_ICON_CLASS} aria-hidden />
            {CONFLICT_TITLE.fileSave}
          </DialogTitle>
          <DialogDescription>
            {conflict?.path ?? 'Open file'} changed outside this editor. Saving now replaces those changes.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button type="button" variant="ghost" onClick={onCancel}>
            {CONFLICT_VERB.cancel}
          </Button>
          <Button type="button" variant="outline" onClick={onViewDiff}>
            {CONFLICT_VERB.viewDiff}
          </Button>
          <Button type="button" variant="outline" onClick={onUseRemote}>
            {CONFLICT_VERB.useRemote}
          </Button>
          <Button type="button" variant="warning" onClick={onOverwriteRetry}>
            {CONFLICT_VERB.overwrite}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
