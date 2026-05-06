import { Plus, Trash2 } from 'lucide-react'
import type { SkillInputType, WizardInput } from '../../../templates/skillMdGenerator'

interface StepInputsProps {
  inputs: WizardInput[]
  errors: Record<string, string>
  onInputChange: (inputId: string, field: keyof WizardInput, value: string) => void
  onAddInput: () => void
  onRemoveInput: (inputId: string) => void
}

const inputTypes = ['str', 'int', 'float', 'bool', 'dict', 'list'] as const satisfies readonly SkillInputType[]

export function StepInputs({ inputs, errors, onInputChange, onAddInput, onRemoveInput }: StepInputsProps) {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold text-gray-900 dark:text-gray-100">Define Inputs</h2>
        <button
          type="button"
          onClick={onAddInput}
          className="flex items-center gap-1 rounded-md border border-sky-200 bg-sky-50 px-2 py-1 text-sm font-medium text-sky-700 hover:bg-sky-100 dark:border-sky-800 dark:bg-sky-900/30 dark:text-sky-300"
        >
          <Plus className="h-4 w-4" />
          Input
        </button>
      </div>
      {errors.inputs ? <div className="text-sm text-red-600 dark:text-red-400">{errors.inputs}</div> : null}
      <div className="space-y-3">
        {inputs.map((input) => (
          <div key={input.id} className="grid grid-cols-[1fr_7rem_1fr_auto] gap-2 rounded-md border border-gray-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900">
            <label>
              <span className="mb-1 block text-xs font-medium uppercase text-gray-500">Name</span>
              <input
                value={input.name}
                onChange={(event) => onInputChange(input.id, 'name', event.target.value)}
                className="w-full rounded border border-gray-300 px-2 py-1.5 font-mono text-sm dark:border-slate-700 dark:bg-slate-800"
              />
              {errors[`input.${input.id}.name`] ? <span className="mt-1 block text-xs text-red-600 dark:text-red-400">{errors[`input.${input.id}.name`]}</span> : null}
            </label>
            <label>
              <span className="mb-1 block text-xs font-medium uppercase text-gray-500">Type</span>
              <select
                value={input.type}
                onChange={(event) => onInputChange(input.id, 'type', event.target.value)}
                className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800"
              >
                {inputTypes.map((type) => <option key={type} value={type}>{type}</option>)}
              </select>
            </label>
            <label>
              <span className="mb-1 block text-xs font-medium uppercase text-gray-500">Default</span>
              <input
                value={input.defaultValue}
                onChange={(event) => onInputChange(input.id, 'defaultValue', event.target.value)}
                className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800"
                placeholder="optional"
              />
            </label>
            <button
              type="button"
              onClick={() => onRemoveInput(input.id)}
              className="mt-6 rounded p-2 text-gray-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-900/20 dark:hover:text-red-400"
            >
              <Trash2 className="h-4 w-4" />
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}
