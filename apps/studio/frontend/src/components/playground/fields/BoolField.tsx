import type { FieldProps } from './types'
import { FieldWrapper } from './FieldWrapper'

export function BoolField({ input, value, error, onChange }: FieldProps) {
  return (
    <FieldWrapper input={input} error={error}>
      <span className="flex items-center gap-3">
        <input
          type="checkbox"
          checked={value === true}
          onChange={(event) => onChange(event.target.checked)}
          className="h-4 w-4 rounded border-gray-300 text-sky-600 focus:ring-sky-500"
        />
        <span className="text-sm text-gray-600 dark:text-gray-400">{value === true ? 'true' : 'false'}</span>
      </span>
    </FieldWrapper>
  )
}
