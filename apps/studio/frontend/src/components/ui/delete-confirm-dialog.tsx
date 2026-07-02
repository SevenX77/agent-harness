import { useCallback, useState } from "react"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"

/**
 * R6-2 (PM 2026-07-02): destructive confirmation used to fire a sonner toast.
 * A toast renders in a body-level portal OUTSIDE the Settings dialog, so
 * clicking its action button counted as an interaction outside the dialog and
 * dismissed the whole Settings modal (点到了 modal 外面) — an anti-pattern.
 *
 * The confirmation is now a Radix AlertDialog rendered INSIDE the component
 * tree (a nested dismissable layer): confirming it no longer collapses the
 * parent dialog, and Escape / Cancel / the overlay only dismiss the confirm.
 */
export interface DeleteConfirmRequest {
  title: string
  description: string
  confirmLabel?: string
  cancelLabel?: string
  onConfirm: () => void | Promise<void>
}

/**
 * Controlled confirm dialog. `request` null = closed. Kept generic so every
 * Settings delete (provider / role / bundle / copilot role) shares one surface.
 */
export function DeleteConfirmDialog({
  request,
  onOpenChange,
}: {
  request: DeleteConfirmRequest | null
  onOpenChange: (open: boolean) => void
}) {
  return (
    <AlertDialog open={request !== null} onOpenChange={onOpenChange}>
      {request ? (
        <AlertDialogContent data-slot="delete-confirm-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>{request.title}</AlertDialogTitle>
            <AlertDialogDescription>{request.description}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{request.cancelLabel ?? "Cancel"}</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={() => {
                void request.onConfirm()
              }}
            >
              {request.confirmLabel ?? "Delete"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      ) : null}
    </AlertDialog>
  )
}

/**
 * Hook API mirroring the old imperative `requestDeleteConfirmationToast`: call
 * `confirm({...})` from an event handler, render `{dialog}` once in the
 * component. Confirming runs `onConfirm` then closes; Cancel/Escape close
 * without running it.
 */
export function useDeleteConfirm() {
  const [request, setRequest] = useState<DeleteConfirmRequest | null>(null)

  const confirm = useCallback((next: DeleteConfirmRequest) => {
    setRequest(next)
  }, [])

  const dialog = (
    <DeleteConfirmDialog
      request={request}
      onOpenChange={(open) => {
        if (!open) {
          setRequest(null)
        }
      }}
    />
  )

  return { confirm, dialog }
}
