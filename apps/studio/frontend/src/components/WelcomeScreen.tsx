import { FolderOpen } from 'lucide-react'
import type { SkillSummary } from '../api/types'

interface WelcomeScreenProps {
  skills: SkillSummary[]
  recentSkills: string[]
  onSelectSkill: (skillId: string) => void
  onImportSkill: () => void
}

export function WelcomeScreen({ skills, recentSkills, onSelectSkill, onImportSkill }: WelcomeScreenProps) {
  return (
    <div className="flex h-full flex-col items-center justify-center bg-gray-50 dark:bg-slate-950 text-slate-800 dark:text-slate-200">
      <h1 className="text-5xl font-extrabold mb-12 text-transparent bg-clip-text bg-gradient-to-r from-sky-400 to-violet-500">Skill Studio</h1>
      <div className="flex gap-16 max-w-4xl w-full px-8">
        <div className="flex flex-col gap-6 flex-1">
          <h2 className="text-xl font-bold border-b border-gray-200 dark:border-slate-800 pb-2">Start</h2>
          <button
            type="button"
            onClick={onImportSkill}
            className="flex items-center gap-3 text-sky-600 dark:text-sky-400 hover:text-sky-700 dark:hover:text-sky-300 font-medium transition-colors"
          >
            <FolderOpen className="h-6 w-6" /> Open / Import Skill Folder...
          </button>
        </div>
        <div className="flex flex-col gap-6 flex-1">
          <h2 className="text-xl font-bold border-b border-gray-200 dark:border-slate-800 pb-2">Recent</h2>
          {recentSkills.length > 0 ? (
            <ul className="flex flex-col gap-3">
              {recentSkills.map((id) => {
                const skill = skills.find((item) => item.id === id)
                return (
                  <li key={id}>
                    <button type="button" onClick={() => onSelectSkill(id)} className="text-gray-600 dark:text-gray-400 hover:text-sky-600 dark:hover:text-sky-400 font-medium transition-colors">
                      {skill ? skill.name : id}
                    </button>
                  </li>
                )
              })}
            </ul>
          ) : (
            <div className="text-sm text-gray-500 dark:text-gray-500">No recent skills</div>
          )}
        </div>
      </div>
    </div>
  )
}
