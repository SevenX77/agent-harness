import { FileText, Moon, Plus, Settings, Sun } from 'lucide-react'
import type { SkillSummary } from '../api/types'
import type { ActiveTab } from '../types/studio'
import { errorMessage } from '../utils/errors'
import { ForkButton } from './templates/ForkButton'

interface SkillSidebarProps {
  skills: SkillSummary[]
  selectedSkillId: string | null
  activeTab: ActiveTab
  skillListError: unknown
  isDarkMode: boolean
  onSelectSkill: (skillId: string) => void
  onToggleDarkMode: () => void
  onOpenCreator: () => void
  onOpenSettings: () => void
  onForkSkill: (sourceSkillId: string, newSkillId: string) => Promise<void>
}

export function SkillSidebar({
  skills,
  selectedSkillId,
  activeTab,
  skillListError,
  isDarkMode,
  onSelectSkill,
  onToggleDarkMode,
  onOpenCreator,
  onOpenSettings,
  onForkSkill,
}: SkillSidebarProps) {
  return (
    <nav
      role="navigation"
      aria-label="Skill List"
      className="z-10 flex w-64 shrink-0 flex-col border-r border-gray-200 dark:border-slate-800 bg-white dark:bg-slate-900"
    >
      <div className="flex items-center justify-between border-b border-gray-200 dark:border-slate-800 p-4 text-lg font-bold text-gray-800 dark:text-gray-100">
        <div className="flex items-center gap-2">
          <Settings className="h-5 w-5 text-sky-600 dark:text-sky-500" />
          Skill Studio
        </div>
        <button
          type="button"
          aria-label={isDarkMode ? 'Switch to light mode' : 'Switch to dark mode'}
          onClick={onToggleDarkMode}
          className="text-gray-500 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-100"
        >
          {isDarkMode ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-xs font-semibold uppercase text-gray-400 dark:text-gray-500">Project Skills</h3>
          <button
            type="button"
            aria-label="Create new skill"
            onClick={onOpenCreator}
            className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-sky-600 dark:text-gray-500 dark:hover:bg-slate-800 dark:hover:text-sky-400"
            title="New Skill"
          >
            <Plus className="h-4 w-4" />
          </button>
        </div>
        {skillListError ? (
          <div className="rounded border border-red-200 dark:border-red-900/50 bg-red-50 dark:bg-red-900/20 p-3 text-sm text-red-700 dark:text-red-400">{errorMessage(skillListError)}</div>
        ) : (
          <ul className="space-y-2">
            {skills.map((skill) => (
              <li key={skill.id}>
                <div
                  className={`group flex w-full items-center gap-2 rounded-md border p-2 text-left text-sm font-medium transition-colors ${
                    selectedSkillId === skill.id
                      ? 'border-sky-100 dark:border-sky-900/50 bg-sky-50 dark:bg-sky-900/30 text-sky-700 dark:text-sky-400'
                      : 'border-transparent text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-slate-800'
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => onSelectSkill(skill.id)}
                    className="flex min-w-0 flex-1 items-center gap-2 text-left"
                  >
                    <FileText className="h-4 w-4 shrink-0" />
                    <span className="truncate">{skill.name}</span>
                  </button>
                  <ForkButton skill={skill} onForkSkill={onForkSkill} />
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="border-t border-gray-200 dark:border-slate-800 p-4">
        <button
          type="button"
          aria-label="Open settings"
          onClick={onOpenSettings}
          className={`flex w-full items-center justify-center gap-2 rounded-md p-2 font-medium transition-colors ${
            activeTab === 'settings'
              ? 'bg-gray-200 dark:bg-slate-800 text-gray-800 dark:text-gray-200'
              : 'bg-gray-100 dark:bg-slate-800/50 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-slate-800'
          }`}
        >
          <Settings className="h-4 w-4" />
          Settings
        </button>
      </div>
    </nav>
  )
}
