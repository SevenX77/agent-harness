import { Plus, Trash2 } from 'lucide-react'
import type { JsonValue } from '../../../api/types'
import type { FieldProps } from './types'
import { FieldWrapper } from './FieldWrapper'

function values(value: JsonValue | undefined): JsonValue[] {
  return Array.isArray(value) ? value : []
}

export function ListField({ input, value, error, onChange }: FieldProps) {
  const items = values(value)
  const setItem = (index: number, nextValue: string) => {
    onChange(items.map((item, itemIndex) => (itemIndex === index ? nextValue : item)))
  }

  return (
    <FieldWrapper input={input} error={error}>
      <div className="space-y-2">
        {items.map((item, index) => (
          <div key={index} className="flex items-center gap-2">
            <input
              value={typeof item === 'string' ? item : JSON.stringify(item)}
              onChange={(event) => setItem(index, event.target.value)}
              className="flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500 dark:border-slate-700 dark:bg-slate-800"
            />
            <button
              type="button"
              onClick={() => onChange(items.filter((_, itemIndex) => itemIndex !== index))}
              className="rounded p-2 text-gray-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-900/20 dark:hover:text-red-400"
            >
              <Trash2 className="h-4 w-4" />
            </button>
          </div>
        ))}
        <button
          type="button"
          onClick={() => onChange([...items, ''])}
          className="flex items-center gap-1 rounded-md border border-sky-200 bg-sky-50 px-2 py-1 text-sm font-medium text-sky-700 hover:bg-sky-100 dark:border-sky-800 dark:bg-sky-900/30 dark:text-sky-300"
        >
          <Plus className="h-4 w-4" />
          Item
        </button>
      </div>
    </FieldWrapper>
  )
}
