import { normalizeType } from '../../../hooks/useInputPlayground'
import type { FieldProps } from './types'
import { FieldWrapper } from './FieldWrapper'

export function NumberField({ input, value, error, onChange }: FieldProps) {
  const type = normalizeType(input.type)
  return (
    <FieldWrapper input={input} error={error}>
      <input
        type="number"
        step={type === 'int' ? 1 : 'any'}
        value={typeof value === 'number' ? String(value) : ''}
        onChange={(event) => {
          const raw = event.target.value
          onChange(raw.length === 0 ? null : Number(raw))
        }}
        className="w-full rounded-md border border-input bg-input/20 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring/50"
      />
    </FieldWrapper>
  )
}
