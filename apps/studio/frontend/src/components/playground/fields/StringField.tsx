import type { FieldProps } from './types'
import { FieldWrapper } from './FieldWrapper'

export function StringField({ input, value, error, onChange }: FieldProps) {
  return (
    <FieldWrapper input={input} error={error}>
      <input
        type="text"
        value={typeof value === 'string' ? value : ''}
        onChange={(event) => onChange(event.target.value)}
        className="w-full rounded-md border border-input bg-input/20 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring/50"
        placeholder={typeof input.default === 'string' ? input.default : ''}
      />
    </FieldWrapper>
  )
}
