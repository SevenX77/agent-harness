import type { JsonValue } from '../../../api/types'
import type { FieldProps } from './types'
import { FieldWrapper } from './FieldWrapper'

function optionKey(value: JsonValue): string {
  return JSON.stringify(value)
}

export function EnumField({ input, value, error, onChange }: FieldProps) {
  const options = input.enum ?? []
  return (
    <FieldWrapper input={input} error={error}>
      <select
        value={optionKey(value ?? '')}
        onChange={(event) => {
          const selected = options.find((option) => optionKey(option) === event.target.value)
          onChange(selected ?? '')
        }}
        className="w-full rounded-md border border-input bg-input/20 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring/50"
      >
        {options.map((option) => (
          <option key={optionKey(option)} value={optionKey(option)}>
            {String(option)}
          </option>
        ))}
      </select>
    </FieldWrapper>
  )
}
