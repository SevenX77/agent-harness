import { Bot, GitBranch, MessageSquare, Network, Sparkles } from 'lucide-react'
import type { SkillCreatorType } from '../../templates/skillMdGenerator'

interface TemplateCardProps {
  id: string
  name: string
  description: string
  type: SkillCreatorType
  selected: boolean
  onSelect: () => void
}

function iconFor(type: SkillCreatorType, id: string) {
  if (id.includes('reasoning')) {
    return GitBranch
  }
  if (type === 'graph') {
    return Network
  }
  if (type === 'persona') {
    return MessageSquare
  }
  if (id === 'empty-agent') {
    return Sparkles
  }
  return Bot
}

export function TemplateCard({ id, name, description, type, selected, onSelect }: TemplateCardProps) {
  const Icon = iconFor(type, id)

  return (
    <button
      type="button"
      onClick={onSelect}
      className={`flex min-h-32 flex-col rounded-md border p-4 text-left transition-colors ${
        selected
          ? 'border-sky-400 bg-sky-50 text-sky-900 dark:border-sky-500 dark:bg-sky-950/50 dark:text-sky-100'
          : 'border-gray-200 bg-white text-gray-800 hover:border-sky-200 hover:bg-sky-50/60 dark:border-slate-800 dark:bg-slate-900 dark:text-gray-200 dark:hover:border-sky-900 dark:hover:bg-slate-800'
      }`}
    >
      <div className="mb-3 flex items-center justify-between gap-3">
        <span className="flex h-8 w-8 items-center justify-center rounded bg-gray-100 text-sky-600 dark:bg-slate-800 dark:text-sky-400">
          <Icon className="h-4 w-4" />
        </span>
        <span className="rounded bg-gray-100 px-2 py-0.5 text-[11px] font-semibold uppercase text-gray-500 dark:bg-slate-800 dark:text-gray-400">
          {type}
        </span>
      </div>
      <div className="text-sm font-semibold">{name}</div>
      <p className="mt-2 line-clamp-3 text-xs leading-5 text-gray-500 dark:text-gray-400">{description}</p>
    </button>
  )
}

