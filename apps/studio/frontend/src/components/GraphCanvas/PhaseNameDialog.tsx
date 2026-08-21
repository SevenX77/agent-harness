import { useEffect, useId, useState, type FormEvent } from "react"
import { useTranslation } from "react-i18next"
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
import { phaseNameProblem, type NewPhaseKind, type PhaseNameProblem } from "./canvas-authoring"
import { graphEditProblemMessage } from "./graph-edit-problem-message"

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
  const { t } = useTranslation("canvas")
  const inputId = useId()
  const [nameDraft, setNameDraft] = useState(initialName)
  const [submittedProblem, setSubmittedProblem] = useState<PhaseNameProblem | null>(null)

  useEffect(() => {
    if (open) {
      setNameDraft(initialName)
      setSubmittedProblem(null)
    }
  }, [initialName, open])

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const problem = phaseNameProblem(nameDraft, skillDetail)
    if (problem) {
      setSubmittedProblem(problem)
      return
    }
    onSubmit(nameDraft.trim())
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent aria-describedby={undefined} className="sm:max-w-sm">
        <form className="grid gap-4" onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>
              {kind
                ? t("nameDialog.titleForKind", { kind: t(`phaseKind.${kind}`) })
                : t("nameDialog.titleGeneric")}
            </DialogTitle>
          </DialogHeader>
          <FieldSet>
            <FieldGroup>
              <Field data-invalid={Boolean(submittedProblem)}>
                <FieldLabel htmlFor={inputId}>{t("nameDialog.nodeName")}</FieldLabel>
                <Input
                  id={inputId}
                  value={nameDraft}
                  onChange={(event) => {
                    setSubmittedProblem(null)
                    setNameDraft(event.target.value)
                  }}
                  aria-invalid={Boolean(submittedProblem)}
                  autoComplete="off"
                  autoCorrect="off"
                  autoCapitalize="none"
                  spellCheck={false}
                  autoFocus
                />
                <FieldError>{submittedProblem ? graphEditProblemMessage(submittedProblem) : null}</FieldError>
              </Field>
            </FieldGroup>
          </FieldSet>
          <DialogFooter>
            <DialogClose asChild>
              <Button type="button" variant="outline">
                {t("nameDialog.cancel")}
              </Button>
            </DialogClose>
            <Button type="submit">{t("nameDialog.create")}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
