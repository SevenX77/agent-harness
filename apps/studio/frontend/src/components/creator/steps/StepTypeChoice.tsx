import { Bot, GitBranch, UserRound } from 'lucide-react'
import type { SkillCreatorType } from '../../../templates/skillMdGenerator'

interface StepTypeChoiceProps {
  value: SkillCreatorType
  onChange: (type: SkillCreatorType) => void
}

const choices = [
  ['agent', Bot, 'Agent', 'Single-loop LLM skill for one focused task.'],
  ['graph', GitBranch, 'Graph', 'Multi-phase workflow with runtime inputs and outputs.'],
  ['persona', UserRound, 'Persona', 'Reusable role profile for other skills.'],
] as const

export function StepTypeChoice({ value, onChange }: StepTypeChoiceProps) {
  return (
    <div className="space-y-4">
      <h2 className="text-lg font-bold text-gray-900 dark:text-gray-100">Choose Skill Type</h2>
      <div className="grid gap-3">
        {choices.map(([type, Icon, label, description]) => (
          <button
            key={type}
            type="button"
            onClick={() => onChange(type)}
            className={`flex items-start gap-3 rounded-md border p-4 text-left transition-colors ${
              value === type
                ? 'border-sky-300 bg-sky-50 text-sky-800 dark:border-sky-700 dark:bg-sky-900/30 dark:text-sky-200'
                : 'border-gray-200 bg-white text-gray-700 hover:bg-gray-50 dark:border-slate-800 dark:bg-slate-900 dark:text-gray-300 dark:hover:bg-slate-800'
            }`}
          >
            <Icon className="mt-0.5 h-5 w-5 shrink-0" />
            <span>
              <span className="block font-semibold">{label}</span>
              <span className="mt-1 block text-sm text-gray-500 dark:text-gray-400">{description}</span>
            </span>
          </button>
        ))}
      </div>
    </div>
  )
}
