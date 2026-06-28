import { useEffect, useId, useState, type FormEvent } from "react"
import type { SkillDetail } from "@/api/types"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Field, FieldError, FieldGroup, FieldLabel, FieldSet } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { phaseNameError, type NewPhaseKind } from "./canvas-authoring"

interface PhaseNameDialogProps {
  open: boolean
  kind: NewPhaseKind | null
  initialName: string
  skillDetail?: SkillDetail
  onOpenChange: (open: boolean) => void
  onSubmit: (phaseId: string) => void
}

export function PhaseNameDialog({
  open,
  kind,
  initialName,
  skillDetail,
  onOpenChange,
  onSubmit,
}: PhaseNameDialogProps) {
  const inputId = useId()
  const [nameDraft, setNameDraft] = useState(initialName)
  const [submittedError, setSubmittedError] = useState<string | null>(null)

  useEffect(() => {
    if (open) {
      setNameDraft(initialName)
      setSubmittedError(null)
    }
  }, [initialName, open])

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const error = phaseNameError(nameDraft, skillDetail)
    if (error) {
      setSubmittedError(error)
      return
    }
    onSubmit(nameDraft.trim())
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent aria-describedby={undefined} className="sm:max-w-sm">
        <form className="grid gap-4" onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>{kind ? `Add ${phaseKindLabel(kind)}` : "Add phase node"}</DialogTitle>
          </DialogHeader>
          <FieldSet>
            <FieldGroup>
              <Field data-invalid={Boolean(submittedError)}>
                <FieldLabel htmlFor={inputId}>Node name</FieldLabel>
                <Input
                  id={inputId}
                  value={nameDraft}
                  onChange={(event) => {
                    setSubmittedError(null)
                    setNameDraft(event.target.value)
                  }}
                  aria-invalid={Boolean(submittedError)}
                  autoComplete="off"
                  autoCorrect="off"
                  autoCapitalize="none"
                  spellCheck={false}
                  autoFocus
                />
                <FieldError>{submittedError}</FieldError>
              </Field>
            </FieldGroup>
          </FieldSet>
          <DialogFooter>
            <DialogClose asChild>
              <Button type="button" variant="outline">
                Cancel
              </Button>
            </DialogClose>
            <Button type="submit">Create</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function phaseKindLabel(kind: NewPhaseKind): string {
  if (kind === "skill") {
    return "Agent Phase"
  }
  if (kind === "subgraph") {
    return "Subgraph Phase"
  }
  return "Logic Phase"
}
