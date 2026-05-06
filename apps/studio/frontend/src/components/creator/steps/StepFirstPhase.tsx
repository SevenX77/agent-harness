import type { WizardData } from '../../../templates/skillMdGenerator'

interface StepFirstPhaseProps {
  data: WizardData
  errors: Record<string, string>
  onChange: (field: keyof WizardData, value: string) => void
}

export function StepFirstPhase({ data, errors, onChange }: StepFirstPhaseProps) {
  const isPersona = data.type === 'persona'

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-bold text-gray-900 dark:text-gray-100">
        {isPersona ? 'Persona Profile' : 'First Phase'}
      </h2>
      {!isPersona ? (
        <div className="grid grid-cols-2 gap-3">
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Phase ID</span>
            <input
              value={data.phaseId}
              onChange={(event) => onChange('phaseId', event.target.value)}
              className="w-full rounded-md border border-gray-300 px-3 py-2 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-sky-500 dark:border-slate-700 dark:bg-slate-800"
              placeholder="draft"
            />
            {errors.phaseId ? <span className="mt-1 block text-xs text-red-600 dark:text-red-400">{errors.phaseId}</span> : null}
          </label>
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">LLM Role</span>
            <input
              value={data.llmRole}
              onChange={(event) => onChange('llmRole', event.target.value)}
              className="w-full rounded-md border border-gray-300 px-3 py-2 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-sky-500 dark:border-slate-700 dark:bg-slate-800"
              placeholder="analyst"
            />
            {errors.llmRole ? <span className="mt-1 block text-xs text-red-600 dark:text-red-400">{errors.llmRole}</span> : null}
          </label>
        </div>
      ) : null}

      <label className="block">
        <span className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
          {isPersona ? 'Role Profile' : 'Initial Prompt'}
        </span>
        <textarea
          value={data.prompt}
          onChange={(event) => onChange('prompt', event.target.value)}
          className="h-56 w-full resize-none rounded-md border border-gray-300 px-3 py-2 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-sky-500 dark:border-slate-700 dark:bg-slate-800"
          placeholder={isPersona ? 'Describe the reusable viewpoint, style, and decision rules.' : 'Use {input_text} to complete the task.'}
        />
        {errors.prompt ? <span className="mt-1 block text-xs text-red-600 dark:text-red-400">{errors.prompt}</span> : null}
      </label>
    </div>
  )
}
