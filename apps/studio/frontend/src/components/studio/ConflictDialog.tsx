import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import type { SaveConflict } from './WorkspaceContext'

interface ConflictDialogProps {
  conflict: SaveConflict | null
  onKeepLocal: () => void
  onUseRemote: () => void
  onViewDiff: () => void
}

export function ConflictDialog({ conflict, onKeepLocal, onUseRemote, onViewDiff }: ConflictDialogProps) {
  return (
    <Dialog open={Boolean(conflict)}>
      <DialogContent showCloseButton={false}>
        <DialogHeader>
          <DialogTitle>File changed remotely</DialogTitle>
          <DialogDescription>
            {conflict?.path ?? 'Open file'} changed outside this editor.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onViewDiff}>
            View Diff
          </Button>
          <Button type="button" variant="outline" onClick={onUseRemote}>
            Use Remote
          </Button>
          <Button type="button" onClick={onKeepLocal}>
            Keep Local
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
