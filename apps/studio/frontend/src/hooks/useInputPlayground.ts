import { useCallback, useEffect, useMemo, useReducer } from 'react'
import { api } from '../api/client'
import type { IoInput, JsonObject, JsonValue } from '../api/types'
import { isJsonObject } from '../utils/errors'

export type PlaygroundFieldKind = 'string' | 'number' | 'bool' | 'enum' | 'list' | 'dict'

export interface PlaygroundInputSpec extends IoInput {
  description?: string | null
  enum?: JsonValue[] | null
  required?: boolean | null
}

interface PlaygroundState {
  values: JsonObject
  errors: Record<string, string>
  touched: Record<string, boolean>
}

type PlaygroundAction =
  | { type: 'RESET'; inputs: PlaygroundInputSpec[] }
  | { type: 'SET_VALUE'; path: string; value: JsonValue }
  | { type: 'SET_VALUES'; values: JsonObject }
  | { type: 'VALIDATE'; inputs: PlaygroundInputSpec[] }

function reducer(state: PlaygroundState, action: PlaygroundAction): PlaygroundState {
  switch (action.type) {
    case 'RESET':
      return {
        values: defaultValues(action.inputs),
        errors: validateValues(action.inputs, defaultValues(action.inputs)),
        touched: {},
      }
    case 'SET_VALUE': {
      const values = { ...state.values, [action.path]: action.value }
      return {
        values,
        errors: validateValues([], values),
        touched: { ...state.touched, [action.path]: true },
      }
    }
    case 'SET_VALUES':
      return { values: action.values, errors: {}, touched: {} }
    case 'VALIDATE':
      return { ...state, errors: validateValues(action.inputs, state.values) }
    default:
      return state
  }
}

export function fieldKind(input: PlaygroundInputSpec): PlaygroundFieldKind {
  const type = normalizeType(input.type)
  if (input.enum && input.enum.length > 0) {
    return 'enum'
  }
  if (type === 'int' || type === 'float' || type === 'number') {
    return 'number'
  }
  if (type === 'bool' || type === 'boolean') {
    return 'bool'
  }
  if (type.startsWith('list') || type.endsWith('[]') || type === 'array') {
    return 'list'
  }
  if (type === 'dict' || type === 'object' || type === 'json') {
    return 'dict'
  }
  return 'string'
}

export function normalizeType(type: string | null): string {
  return (type ?? 'str').trim().toLowerCase().replace(/\s+/g, '')
}

function defaultValue(input: PlaygroundInputSpec): JsonValue {
  if (input.default !== null && input.default !== undefined) {
    return input.default
  }
  switch (fieldKind(input)) {
    case 'number':
      return null
    case 'bool':
      return false
    case 'list':
      return []
    case 'dict':
      return {}
    case 'enum':
      return input.enum?.[0] ?? ''
    case 'string':
    default:
      return ''
  }
}

function defaultValues(inputs: PlaygroundInputSpec[]): JsonObject {
  return Object.fromEntries(inputs.map((input) => [input.name, defaultValue(input)]))
}

function isRequired(input: PlaygroundInputSpec): boolean {
  return input.required !== false
}

function validateValue(input: PlaygroundInputSpec, value: JsonValue | undefined): string | null {
  if (isRequired(input)) {
    if (value === undefined || value === null) {
      return 'Required.'
    }
    if (typeof value === 'string' && value.trim().length === 0) {
      return 'Required.'
    }
    if (Array.isArray(value) && value.length === 0) {
      return 'Add at least one item.'
    }
  }

  switch (fieldKind(input)) {
    case 'number':
      return typeof value === 'number' && Number.isFinite(value) ? null : 'Enter a valid number.'
    case 'bool':
      return typeof value === 'boolean' ? null : 'Choose true or false.'
    case 'list':
      return Array.isArray(value) ? null : 'Enter a list.'
    case 'dict':
      return isJsonObject(value) ? null : 'Enter a JSON object.'
    case 'enum':
      return input.enum?.some((item) => JSON.stringify(item) === JSON.stringify(value)) ? null : 'Choose a value.'
    case 'string':
    default:
      return typeof value === 'string' ? null : 'Enter text.'
  }
}

function validateValues(inputs: PlaygroundInputSpec[], values: JsonObject): Record<string, string> {
  if (inputs.length === 0) {
    return {}
  }
  return Object.fromEntries(
    inputs.flatMap((input) => {
      const error = validateValue(input, values[input.name])
      return error ? [[input.name, error]] : []
    }),
  )
}

export function useInputPlayground(inputs: PlaygroundInputSpec[]) {
  const [state, dispatch] = useReducer(reducer, inputs, (initialInputs) => ({
    values: defaultValues(initialInputs),
    errors: validateValues(initialInputs, defaultValues(initialInputs)),
    touched: {},
  }))

  useEffect(() => {
    dispatch({ type: 'RESET', inputs })
  }, [inputs])

  const setValue = useCallback((path: string, value: JsonValue) => {
    dispatch({ type: 'SET_VALUE', path, value })
  }, [])

  const setValues = useCallback((values: JsonObject) => {
    dispatch({ type: 'SET_VALUES', values })
    dispatch({ type: 'VALIDATE', inputs })
  }, [inputs])

  const reset = useCallback(() => {
    dispatch({ type: 'RESET', inputs })
  }, [inputs])

  const errors = useMemo(() => validateValues(inputs, state.values), [inputs, state.values])
  const isValid = Object.keys(errors).length === 0

  const submitInputs = useCallback((): JsonObject | null => {
    const currentErrors = validateValues(inputs, state.values)
    dispatch({ type: 'VALIDATE', inputs })
    return Object.keys(currentErrors).length === 0 ? state.values : null
  }, [inputs, state.values])

  const validateRemote = useCallback(async (skillId: string, values: JsonObject) => {
    await api.post(`/skills/${skillId}/validate_input`, values)
  }, [])

  return {
    values: state.values,
    errors,
    touched: state.touched,
    isValid,
    setValue,
    setValues,
    reset,
    validateRemote,
    submitInputs,
  }
}
