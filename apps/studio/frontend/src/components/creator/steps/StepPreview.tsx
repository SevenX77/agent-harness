import type { WizardData } from '../../../templates/skillMdGenerator'

interface StepPreviewProps {
  data: WizardData
  preview: string
}

export function StepPreview({ data, preview }: StepPreviewProps) {
  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <div>
        <h2 className="text-lg font-bold text-gray-900 dark:text-gray-100">Preview SKILL.md</h2>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Creates <span className="font-mono">workspaces/default/skills/{data.skillId}/SKILL.md</span>.
        </p>
      </div>
      <pre className="min-h-0 flex-1 overflow-auto rounded-md border border-gray-200 bg-slate-950 p-4 text-xs leading-relaxed text-slate-100 dark:border-slate-800">
        {preview}
      </pre>
    </div>
  )
}
