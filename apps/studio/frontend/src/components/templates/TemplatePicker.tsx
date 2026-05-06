import type { SkillTemplate } from '../../api/types'
import { initialWizardData } from '../../hooks/useSkillCreator'
import { useTemplates } from '../../hooks/useTemplates'
import type { SkillCreatorType, WizardData } from '../../templates/skillMdGenerator'
import { wizardDataFromSkillMd } from '../../templates/skillMdGenerator'
import { errorMessage } from '../../utils/errors'
import { TemplateCard } from './TemplateCard'

interface TemplatePickerProps {
  selectedTemplateId: string | null
  onSelect: (data: WizardData) => void
}

const emptyStarters: Array<{
  id: string
  type: SkillCreatorType
  name: string
  description: string
}> = [
  {
    id: 'empty-agent',
    type: 'agent',
    name: 'Empty Agent',
    description: 'Start with a single-step agent and define the task from scratch.',
  },
  {
    id: 'empty-graph',
    type: 'graph',
    name: 'Empty Graph',
    description: 'Start with a minimal graph and add phases, inputs, and outputs.',
  },
  {
    id: 'empty-persona',
    type: 'persona',
    name: 'Empty Persona',
    description: 'Start with a pure persona profile for reuse by other skills.',
  },
]

function starterData(type: SkillCreatorType): WizardData {
  return {
    ...initialWizardData(),
    templateId: `empty-${type}`,
    type,
  }
}

function safeTemplateType(template: SkillTemplate): SkillCreatorType {
  return template.type === 'graph' || template.type === 'persona' ? template.type : 'agent'
}

export function TemplatePicker({ selectedTemplateId, onSelect }: TemplatePickerProps) {
  const { templates, templatesError, templatesLoading } = useTemplates()

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Choose a starting point</h2>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Start empty or use a built-in template. You can adjust basics, inputs, and the first phase next.
        </p>
      </div>

      <div>
        <h3 className="mb-3 text-xs font-semibold uppercase text-gray-400 dark:text-gray-500">Blank starters</h3>
        <div className="grid gap-3 md:grid-cols-3">
          {emptyStarters.map((starter) => (
            <TemplateCard
              key={starter.id}
              id={starter.id}
              name={starter.name}
              description={starter.description}
              type={starter.type}
              selected={selectedTemplateId === starter.id}
              onSelect={() => onSelect(starterData(starter.type))}
            />
          ))}
        </div>
      </div>

      <div>
        <h3 className="mb-3 text-xs font-semibold uppercase text-gray-400 dark:text-gray-500">Template library</h3>
        {templatesLoading ? (
          <div className="rounded-md border border-gray-200 bg-gray-50 p-4 text-sm text-gray-500 dark:border-slate-800 dark:bg-slate-900 dark:text-gray-400">
            Loading templates...
          </div>
        ) : null}
        {templatesError ? (
          <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900/50 dark:bg-red-950/40 dark:text-red-300">
            {errorMessage(templatesError)}
          </div>
        ) : null}
        <div className="grid gap-3 md:grid-cols-2">
          {templates.map((template) => (
            <TemplateCard
              key={template.id}
              id={template.id}
              name={template.name}
              description={template.description}
              type={safeTemplateType(template)}
              selected={selectedTemplateId === template.id}
              onSelect={() => onSelect(wizardDataFromSkillMd(template.content, template.id))}
            />
          ))}
        </div>
      </div>
    </div>
  )
}
