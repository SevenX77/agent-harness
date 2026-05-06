import type { WizardData } from '../../../templates/skillMdGenerator'

interface StepBasicsProps {
  data: WizardData
  errors: Record<string, string>
  onChange: (field: keyof WizardData, value: string) => void
}

export function StepBasics({ data, errors, onChange }: StepBasicsProps) {
  return (
    <div className="space-y-4">
      <h2 className="text-lg font-bold text-gray-900 dark:text-gray-100">Basic Information</h2>
      <label className="block">
        <span className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Skill ID</span>
        <input
          value={data.skillId}
          onChange={(event) => onChange('skillId', event.target.value)}
          className="w-full rounded-md border border-gray-300 px-3 py-2 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-sky-500 dark:border-slate-700 dark:bg-slate-800"
          placeholder="story-generator"
        />
        <span className={`mt-1 block text-xs ${errors.skillId ? 'text-red-600 dark:text-red-400' : 'text-gray-500 dark:text-gray-400'}`}>
          {errors.skillId ?? 'Lowercase letters, numbers, and hyphens. Must start with a letter.'}
        </span>
      </label>

      <label className="block">
        <span className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Name</span>
        <input
          value={data.name}
          onChange={(event) => onChange('name', event.target.value)}
          className="w-full rounded-md border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-sky-500 dark:border-slate-700 dark:bg-slate-800"
          placeholder="Story Generator"
        />
        {errors.name ? <span className="mt-1 block text-xs text-red-600 dark:text-red-400">{errors.name}</span> : null}
      </label>

      <label className="block">
        <span className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Description</span>
        <textarea
          value={data.description}
          onChange={(event) => onChange('description', event.target.value)}
          className="h-20 w-full resize-none rounded-md border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-sky-500 dark:border-slate-700 dark:bg-slate-800"
          placeholder="Describe when this skill should be used."
        />
        {errors.description ? <span className="mt-1 block text-xs text-red-600 dark:text-red-400">{errors.description}</span> : null}
      </label>

      <label className="block">
        <span className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Tags</span>
        <input
          value={data.tags}
          onChange={(event) => onChange('tags', event.target.value)}
          className="w-full rounded-md border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-sky-500 dark:border-slate-700 dark:bg-slate-800"
          placeholder="drafting, analysis"
        />
      </label>
    </div>
  )
}
