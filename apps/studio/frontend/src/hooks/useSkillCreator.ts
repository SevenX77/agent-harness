import { useMemo, useReducer } from 'react'
import type { SkillInputType, WizardData, WizardInput } from '../templates/skillMdGenerator'
import { generateSkillMd } from '../templates/skillMdGenerator'

export const SKILL_ID_PATTERN = /^[a-z][a-z0-9-]+$/
export const FIELD_ID_PATTERN = /^[a-z][a-z0-9_]*$/
const STEP_COUNT = 5

export interface SkillCreatorState {
  stepIndex: number
  data: WizardData
  errors: Record<string, string>
  submitting: boolean
}

type SkillCreatorAction =
  | { type: 'NEXT' }
  | { type: 'PREV' }
  | { type: 'SET_FIELD'; field: keyof WizardData; value: WizardData[keyof WizardData] }
  | { type: 'SET_INPUT_FIELD'; inputId: string; field: keyof WizardInput; value: string }
  | { type: 'ADD_INPUT' }
  | { type: 'REMOVE_INPUT'; inputId: string }
  | { type: 'SET_ERRORS'; errors: Record<string, string> }
  | { type: 'SET_SUBMITTING'; submitting: boolean }
  | { type: 'RESET' }

function newInput(): WizardInput {
  return {
    id: crypto.randomUUID(),
    name: 'input_text',
    type: 'str',
    defaultValue: '',
  }
}

export function initialWizardData(): WizardData {
  return {
    type: 'agent',
    skillId: '',
    name: '',
    description: '',
    tags: '',
    inputs: [newInput()],
    phaseId: 'draft',
    llmRole: 'analyst',
    prompt: 'Use {input_text} to complete the task.',
  }
}

function initialState(): SkillCreatorState {
  return {
    stepIndex: 0,
    data: initialWizardData(),
    errors: {},
    submitting: false,
  }
}

function reducer(state: SkillCreatorState, action: SkillCreatorAction): SkillCreatorState {
  switch (action.type) {
    case 'NEXT':
      return { ...state, stepIndex: Math.min(state.stepIndex + 1, STEP_COUNT - 1), errors: {} }
    case 'PREV':
      return { ...state, stepIndex: Math.max(state.stepIndex - 1, 0), errors: {} }
    case 'SET_FIELD':
      return { ...state, data: { ...state.data, [action.field]: action.value }, errors: {} }
    case 'SET_INPUT_FIELD':
      return {
        ...state,
        data: {
          ...state.data,
          inputs: state.data.inputs.map((input) => (
            input.id === action.inputId
              ? { ...input, [action.field]: action.field === 'type' ? action.value as SkillInputType : action.value }
              : input
          )),
        },
        errors: {},
      }
    case 'ADD_INPUT':
      return { ...state, data: { ...state.data, inputs: [...state.data.inputs, newInput()] }, errors: {} }
    case 'REMOVE_INPUT': {
      const inputs = state.data.inputs.filter((input) => input.id !== action.inputId)
      return { ...state, data: { ...state.data, inputs: inputs.length > 0 ? inputs : state.data.inputs }, errors: {} }
    }
    case 'SET_ERRORS':
      return { ...state, errors: action.errors }
    case 'SET_SUBMITTING':
      return { ...state, submitting: action.submitting }
    case 'RESET':
      return initialState()
    default:
      return state
  }
}

export function validateStep(data: WizardData, stepIndex: number): Record<string, string> {
  const errors: Record<string, string> = {}
  if (stepIndex === 0 && !data.type) {
    errors.type = 'Choose a skill type.'
  }
  if (stepIndex === 1) {
    if (!SKILL_ID_PATTERN.test(data.skillId)) {
      errors.skillId = 'Use lowercase letters, numbers, and hyphens. Start with a letter.'
    }
    if (!data.name.trim()) {
      errors.name = 'Name is required.'
    }
    if (!data.description.trim()) {
      errors.description = 'Description is required.'
    }
  }
  if (stepIndex === 2) {
    if (data.inputs.length === 0) {
      errors.inputs = 'Add at least one input.'
    }
    data.inputs.forEach((input, index) => {
      if (!FIELD_ID_PATTERN.test(input.name)) {
        errors[`input.${input.id}.name`] = `Input ${index + 1} must use snake_case.`
      }
    })
  }
  if (stepIndex === 3) {
    if (data.type !== 'persona' && !FIELD_ID_PATTERN.test(data.phaseId)) {
      errors.phaseId = 'Phase ID must use snake_case.'
    }
    if (data.type !== 'persona' && !data.llmRole.trim()) {
      errors.llmRole = 'LLM role is required.'
    }
    if (!data.prompt.trim()) {
      errors.prompt = data.type === 'persona' ? 'Persona profile is required.' : 'Initial prompt is required.'
    }
  }
  return errors
}

export function useSkillCreator() {
  const [state, dispatch] = useReducer(reducer, undefined, initialState)
  const currentErrors = useMemo(
    () => validateStep(state.data, state.stepIndex),
    [state.data, state.stepIndex],
  )
  const preview = useMemo(() => generateSkillMd(state.data), [state.data])
  const canNext = Object.keys(currentErrors).length === 0
  const isLastStep = state.stepIndex === STEP_COUNT - 1

  return {
    state,
    dispatch,
    preview,
    canNext,
    isLastStep,
    stepCount: STEP_COUNT,
    currentErrors: { ...currentErrors, ...state.errors },
  }
}
