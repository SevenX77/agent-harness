import { AxiosError } from 'axios'
import { X } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { api } from '../../api/client'
import type { SkillSummary } from '../../api/types'
import { useSkillCreator, validateStep } from '../../hooks/useSkillCreator'
import type { ToastKind } from '../../types/studio'
import { errorMessage } from '../../utils/errors'
import type { WizardData, WizardInput } from '../../templates/skillMdGenerator'
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
  const trapRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!open) {
      return undefined
    }
    const returnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose()
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    const focusTimer = window.setTimeout(() => trapRef.current?.querySelector<HTMLElement>('button, textarea, input, select, a[href]')?.focus(), 0)
    return () => {
      window.clearTimeout(focusTimer)
      document.removeEventListener('keydown', handleKeyDown)
      returnFocus?.focus()
    }
  }, [onClose, open])

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
      })
      pushToast(`Created skill: ${response.data.id}`, 'success')
      await onCreated(response.data.id)
      dispatch({ type: 'RESET' })
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

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-6 dark:bg-black/80">
      <div
        ref={trapRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="skill-creator-title"
        className="flex h-[82vh] w-full max-w-4xl flex-col overflow-hidden rounded-md border border-gray-200 bg-white shadow-2xl dark:border-slate-800 dark:bg-slate-900"
      >
        <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4 dark:border-slate-800">
          <div>
            <h1 id="skill-creator-title" className="text-xl font-bold text-gray-900 dark:text-gray-100">New Skill</h1>
            <p className="text-sm text-gray-500 dark:text-gray-400">Generate a valid SKILL.md from guided inputs.</p>
          </div>
          <button type="button" aria-label="Close skill creator" onClick={onClose} className="rounded p-1 text-gray-500 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-slate-800 dark:hover:text-gray-100">
            <X className="h-5 w-5" />
          </button>
        </div>

        <StepIndicator stepIndex={state.stepIndex} stepCount={stepCount} />

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
            <StepPreview data={state.data} preview={preview} />
          ) : null}
        </div>

        <div className="flex items-center justify-between border-t border-gray-200 px-6 py-4 dark:border-slate-800">
          <button
            type="button"
            onClick={() => dispatch({ type: 'PREV' })}
            disabled={state.stepIndex === 0 || state.submitting}
            className="rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:text-gray-300 dark:hover:bg-slate-800"
          >
            Prev
          </button>
          {isLastStep ? (
            <button
              type="button"
              onClick={() => void submit()}
              disabled={!canNext || state.submitting}
              className="rounded-md bg-sky-600 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-700 disabled:cursor-not-allowed disabled:bg-sky-300 dark:disabled:bg-sky-900"
            >
              {state.submitting ? 'Creating...' : 'Create Skill'}
            </button>
          ) : (
            <button
              type="button"
              onClick={next}
              disabled={!canNext || state.submitting}
              className="rounded-md bg-sky-600 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-700 disabled:cursor-not-allowed disabled:bg-sky-300 dark:disabled:bg-sky-900"
            >
              Next
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
