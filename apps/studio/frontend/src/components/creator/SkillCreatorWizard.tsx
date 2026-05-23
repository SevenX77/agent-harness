import { AxiosError } from 'axios'
import { FolderOpen } from 'lucide-react'
import { useState } from 'react'
import { api } from '../../api/client'
import type { SkillSummary } from '../../api/types'
import { useSkillCreator, validateStep } from '../../hooks/useSkillCreator'
import { selectSkillDirectory } from '../../lib/tauri'
import type { ToastKind } from '../../types/studio'
import { errorMessage } from '../../utils/errors'
import type { WizardData, WizardInput } from '../../templates/skillMdGenerator'
import { Button } from '../ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '../ui/dialog'
import { TemplatePicker } from '../templates/TemplatePicker'
import { StepIndicator } from './StepIndicator'
import { StepBasics } from './steps/StepBasics'
import { StepFirstPhase } from './steps/StepFirstPhase'
import { StepInputs } from './steps/StepInputs'
import { StepPreview } from './steps/StepPreview'

interface SkillCreatorWizardProps {
  open: boolean
  onClose: () => void
  onCreated: (skillId: string) => Promise<void> | void
  pushToast: (message: string, kind?: ToastKind) => void
}

export function SkillCreatorWizard({ open, onClose, onCreated, pushToast }: SkillCreatorWizardProps) {
  const { state, dispatch, preview, canNext, isLastStep, stepCount, currentErrors } = useSkillCreator()
  const [directoryPath, setDirectoryPath] = useState<string | null>(null)

  if (!open) {
    return null
  }

  const setField = (field: keyof WizardData, value: string) => {
    dispatch({ type: 'SET_FIELD', field, value })
  }

  const next = () => {
    const errors = validateStep(state.data, state.stepIndex)
    if (Object.keys(errors).length > 0) {
      dispatch({ type: 'SET_ERRORS', errors })
      return
    }
    dispatch({ type: 'NEXT' })
  }

  const submit = async () => {
    dispatch({ type: 'SET_SUBMITTING', submitting: true })
    dispatch({ type: 'SET_ERRORS', errors: {} })
    try {
      const response = await api.post<SkillSummary>('/skills', {
        skill_id: state.data.skillId,
        content: preview,
        directory_path: directoryPath,
      })
      pushToast(`Created skill: ${response.data.id}`, 'success')
      await onCreated(response.data.id)
      dispatch({ type: 'RESET' })
      setDirectoryPath(null)
      onClose()
    } catch (error) {
      if (error instanceof AxiosError && error.response?.status === 409) {
        dispatch({ type: 'GO_TO_STEP', stepIndex: 1 })
        dispatch({ type: 'SET_ERRORS', errors: { skillId: 'Skill ID is already in use.' } })
      }
      pushToast(errorMessage(error), 'error')
    } finally {
      dispatch({ type: 'SET_SUBMITTING', submitting: false })
    }
  }

  const chooseDirectory = async () => {
    const selected = await selectSkillDirectory()
    if (selected) {
      setDirectoryPath(selected)
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen) {
          onClose()
        }
      }}
    >
      <DialogContent className="flex h-[82vh] max-w-4xl flex-col overflow-hidden p-0 sm:max-w-4xl">
        <DialogHeader className="border-b border-border px-6 py-4">
          <DialogTitle>New Skill</DialogTitle>
          <DialogDescription>
            Generate a valid SKILL.md from guided inputs.
          </DialogDescription>
        </DialogHeader>

        <StepIndicator stepIndex={state.stepIndex} stepCount={stepCount} />

        <div className="border-b border-border px-6 py-3">
          <Button
            type="button"
            variant="outline"
            onClick={() => void chooseDirectory()}
          >
            <FolderOpen />
            Choose folder
          </Button>
          <span className="ms-3 align-middle text-xs text-muted-foreground">
            {directoryPath ?? 'Default: AgentStudio/Skills'}
          </span>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto p-6">
          {state.stepIndex === 0 ? (
            <TemplatePicker
              selectedTemplateId={state.data.templateId}
              onSelect={(data) => dispatch({ type: 'APPLY_TEMPLATE', data })}
            />
          ) : null}
          {state.stepIndex === 1 ? (
            <StepBasics data={state.data} errors={currentErrors} onChange={setField} />
          ) : null}
          {state.stepIndex === 2 ? (
            <StepInputs
              inputs={state.data.inputs}
              errors={currentErrors}
              onInputChange={(inputId: string, field: keyof WizardInput, value: string) => dispatch({ type: 'SET_INPUT_FIELD', inputId, field, value })}
              onAddInput={() => dispatch({ type: 'ADD_INPUT' })}
              onRemoveInput={(inputId: string) => dispatch({ type: 'REMOVE_INPUT', inputId })}
            />
          ) : null}
          {state.stepIndex === 3 ? (
            <StepFirstPhase data={state.data} errors={currentErrors} onChange={setField} />
          ) : null}
          {state.stepIndex === 4 ? (
            <StepPreview data={state.data} preview={preview} directoryPath={directoryPath} />
          ) : null}
        </div>

        <DialogFooter className="border-t border-border px-6 py-4 sm:justify-between">
          <Button
            type="button"
            variant="outline"
            onClick={() => dispatch({ type: 'PREV' })}
            disabled={state.stepIndex === 0 || state.submitting}
          >
            Prev
          </Button>
          {isLastStep ? (
            <Button
              type="button"
              onClick={() => void submit()}
              disabled={!canNext || state.submitting}
            >
              {state.submitting ? 'Creating...' : 'Create Skill'}
            </Button>
          ) : (
            <Button
              type="button"
              onClick={next}
              disabled={!canNext || state.submitting}
            >
              Next
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
