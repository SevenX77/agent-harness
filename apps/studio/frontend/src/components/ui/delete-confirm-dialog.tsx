import type { ReactNode } from "react"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog"

export function DeleteConfirmDialog({
  description = "This action cannot be undone.",
  itemName,
  onConfirm,
  onOpenChange,
  open,
  title,
  trigger,
}: {
  description?: ReactNode
  itemName: string
  onConfirm: () => void
  onOpenChange?: (open: boolean) => void
  open?: boolean
  title?: string
  trigger?: ReactNode
}) {
  const dialogTitle = title ?? `Delete ${itemName}?`

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      {trigger ? <AlertDialogTrigger asChild>{trigger}</AlertDialogTrigger> : null}
      <AlertDialogContent forceMount size="sm" data-delete-confirm-dialog="true">
        <AlertDialogHeader>
          <AlertDialogTitle>{dialogTitle}</AlertDialogTitle>
          <AlertDialogDescription>{description}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            variant="destructive"
            data-delete-confirm-action="true"
            onClick={onConfirm}
          >
            Delete
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
