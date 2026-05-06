import type { FieldProps } from './types'
import { FieldWrapper } from './FieldWrapper'

export function StringField({ input, value, error, onChange }: FieldProps) {
  return (
    <FieldWrapper input={input} error={error}>
      <input
        type="text"
        value={typeof value === 'string' ? value : ''}
        onChange={(event) => onChange(event.target.value)}
        className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500 dark:border-slate-700 dark:bg-slate-800"
        placeholder={typeof input.default === 'string' ? input.default : ''}
      />
    </FieldWrapper>
  )
}
