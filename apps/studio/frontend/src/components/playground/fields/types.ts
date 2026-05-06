import type { JsonValue } from '../../../api/types'
import type { PlaygroundInputSpec } from '../../../hooks/useInputPlayground'

export interface FieldProps {
  input: PlaygroundInputSpec
  value: JsonValue | undefined
  error?: string
  onChange: (value: JsonValue) => void
}
