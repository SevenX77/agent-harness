import { useEffect, useId, useState, type FormEvent, type ReactNode } from "react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Field, FieldError, FieldGroup, FieldLabel, FieldSet } from "@/components/ui/field"
import { Input } from "@/components/ui/input"

export function RoleNameDialog({
  title,
  initialName,
  existingNames,
  trigger,
  submitLabel = "Apply",
  fieldLabel = "Role name",
  open: controlledOpen,
  onOpenChange,
  onSubmit,
}: {
  title: string
  initialName: string
  existingNames: string[]
  trigger?: ReactNode
  submitLabel?: string
  fieldLabel?: string
  open?: boolean
  onOpenChange?: (open: boolean) => void
  onSubmit: (roleName: string) => void
}) {
  const inputId = useId()
  const [open, setOpen] = useState(false)
  const [nameDraft, setNameDraft] = useState(initialName)
  const [submittedError, setSubmittedError] = useState<string | null>(null)
  const isOpen = controlledOpen ?? open

  useEffect(() => {
    if (isOpen) {
      setNameDraft(initialName)
      setSubmittedError(null)
    }
  }, [initialName, isOpen])

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const error = roleNameError(nameDraft, existingNames, initialName)
    if (error) {
      setSubmittedError(error)
      return
    }
    onSubmit(nameDraft.trim())
    if (controlledOpen === undefined) setOpen(false)
    onOpenChange?.(false)
  }

  return (
    <Dialog
      open={isOpen}
      onOpenChange={(nextOpen) => {
        if (controlledOpen === undefined) setOpen(nextOpen)
        onOpenChange?.(nextOpen)
      }}
    >
      {trigger ? <DialogTrigger asChild>{trigger}</DialogTrigger> : null}
      <DialogContent aria-describedby={undefined} className="sm:max-w-sm">
        <form className="grid gap-4" onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
          </DialogHeader>
          <RoleNameFields
            inputId={inputId}
            label={fieldLabel}
            nameDraft={nameDraft}
            error={submittedError}
            onNameChange={(value) => {
              setSubmittedError(null)
              setNameDraft(value)
            }}
          />
          <DialogFooter>
            <DialogClose asChild>
              <Button type="button" variant="outline">
                Cancel
              </Button>
            </DialogClose>
            <Button type="submit">{submitLabel}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export function RoleNameFields({
  inputId,
  label = "Role name",
  nameDraft,
  error,
  onNameChange,
}: {
  inputId: string
  label?: string
  nameDraft: string
  error: string | null
  onNameChange: (value: string) => void
}) {
  return (
    <FieldSet>
      <FieldGroup>
        <Field data-invalid={Boolean(error)}>
          <FieldLabel htmlFor={inputId}>{label}</FieldLabel>
          <Input
            id={inputId}
            value={nameDraft}
            onChange={(event) => onNameChange(event.target.value)}
            aria-invalid={Boolean(error)}
            autoComplete="new-password"
            autoCorrect="off"
            autoCapitalize="none"
            spellCheck={false}
          />
          <FieldError>{error}</FieldError>
        </Field>
      </FieldGroup>
    </FieldSet>
  )
}

export function roleNameDisplayError(
  roleName: string,
  existingNames: string[],
  currentName: string,
  hasSubmitted: boolean,
): string | null {
  if (!hasSubmitted) return null
  return roleNameError(roleName, existingNames, currentName)
}

function roleNameError(roleName: string, existingNames: string[], currentName: string): string | null {
  const trimmedRoleName = roleName.trim()
  if (!trimmedRoleName) return "Role name is required."
  const normalizedRoleName = trimmedRoleName.toLowerCase()
  if (
    trimmedRoleName !== currentName &&
    existingNames.some((existingName) => (
      existingName !== currentName && existingName.trim().toLowerCase() === normalizedRoleName
    ))
  ) {
    return "Role name already exists."
  }
  return null
}
