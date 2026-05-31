import { toast } from "sonner"

export const DELETE_CONFIRM_TOAST_ACTION_CLASSNAME = "!bg-destructive !text-destructive-foreground hover:!bg-destructive/90 focus-visible:!ring-destructive/40"

export function requestDeleteConfirmationToast({
  cancelLabel = "Cancel",
  confirmLabel = "Delete",
  description,
  id,
  onConfirm,
  title,
}: {
  cancelLabel?: string
  confirmLabel?: string
  description: string
  id: string
  onConfirm: () => void | Promise<void>
  title: string
}) {
  toast(title, {
    id,
    description,
    duration: Infinity,
    action: {
      label: confirmLabel,
      onClick: () => {
        toast.dismiss(id)
        void onConfirm()
      },
    },
    cancel: {
      label: cancelLabel,
      onClick: () => {
        toast.dismiss(id)
      },
    },
    classNames: {
      actionButton: DELETE_CONFIRM_TOAST_ACTION_CLASSNAME,
    },
  })
}
