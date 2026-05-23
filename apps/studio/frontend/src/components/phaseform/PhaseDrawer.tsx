import { RotateCcw, Save } from 'lucide-react'
import type { PhaseFormData } from '../../hooks/usePhaseForm'
import { phaseFormErrors } from '../../hooks/usePhaseForm'
import { Button } from '../ui/button'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from '../ui/sheet'
import { PhaseFormBody } from './PhaseFormBody'

interface PhaseDrawerProps {
  open: boolean
  phaseId: string | null
  data: PhaseFormData
  availableTools: string[]
  dirty: boolean
  onChange: <Key extends keyof PhaseFormData>(field: Key, value: PhaseFormData[Key]) => void
  onApply: () => void
  onReset: () => void
  onClose: () => void
}

export function PhaseDrawer({
  open,
  phaseId,
  data,
  availableTools,
  dirty,
  onChange,
  onApply,
  onReset,
  onClose,
}: PhaseDrawerProps) {
  const errors = phaseFormErrors(data)
  const canApply = Object.keys(errors).length === 0

  if (!open) {
    return null
  }

  return (
    <Sheet open={open} onOpenChange={(nextOpen) => !nextOpen && onClose()}>
      <SheetContent
        className="w-[min(92vw,42rem)] max-w-none p-0 sm:max-w-none md:min-w-[32rem]"
        side="right"
      >
        <SheetHeader className="border-b border-border bg-background px-5 py-4">
          <SheetDescription className="font-semibold uppercase tracking-wide text-primary">
            Phase form
          </SheetDescription>
          <SheetTitle className="text-lg font-bold">
            {phaseId ?? 'Unknown phase'}
          </SheetTitle>
          <SheetDescription>
            Changes apply only after pressing Apply.
          </SheetDescription>
        </SheetHeader>

        <div className="min-h-0 flex-1 overflow-y-auto p-5">
          <PhaseFormBody data={data} availableTools={availableTools} onChange={onChange} />
        </div>

        <SheetFooter className="flex-row items-center justify-between border-t border-border bg-background px-5 py-4">
          <span className={`text-xs font-medium ${dirty ? 'text-primary' : 'text-muted-foreground'}`}>
            {dirty ? 'Unsaved form edits' : 'Synced with SKILL.md'}
          </span>
          <div className="flex items-center gap-2">
            <Button
              type="button"
              onClick={onReset}
              variant="outline"
            >
              <RotateCcw className="h-4 w-4" />
              Reset
            </Button>
            <Button
              type="button"
              disabled={!canApply}
              onClick={onApply}
            >
              <Save className="h-4 w-4" />
              Apply
            </Button>
          </div>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  )
}
