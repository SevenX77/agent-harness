import { Copy, X } from 'lucide-react'
import { useMemo, useState } from 'react'
import type { SkillSummary } from '../../api/types'
import { SKILL_ID_PATTERN } from '../../hooks/useSkillCreator'
import { errorMessage } from '../../utils/errors'

interface ForkButtonProps {
  skill: SkillSummary
  onForkSkill: (sourceSkillId: string, newSkillId: string) => Promise<void>
}

function defaultForkId(skillId: string): string {
  return `${skillId}-copy`
}

export function ForkButton({ skill, onForkSkill }: ForkButtonProps) {
  const [open, setOpen] = useState(false)
  const [newSkillId, setNewSkillId] = useState(defaultForkId(skill.id))
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const valid = useMemo(() => SKILL_ID_PATTERN.test(newSkillId), [newSkillId])

  const openModal = () => {
    setNewSkillId(defaultForkId(skill.id))
    setError(null)
    setOpen(true)
  }

  const submit = async () => {
    if (!valid || submitting) {
      setError('Use lowercase letters, numbers, and hyphens. Start with a letter.')
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      await onForkSkill(skill.id, newSkillId)
      setOpen(false)
    } catch (forkError) {
      setError(errorMessage(forkError))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={(event) => {
          event.stopPropagation()
          openModal()
        }}
        className="rounded p-1 text-gray-400 opacity-0 transition hover:bg-gray-200 hover:text-sky-600 group-hover:opacity-100 dark:text-gray-500 dark:hover:bg-slate-700 dark:hover:text-sky-400"
        title={`Fork ${skill.name}`}
      >
        <Copy className="h-4 w-4" />
      </button>
      {open ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-6 dark:bg-black/80">
          <div className="w-full max-w-md rounded-md border border-gray-200 bg-white shadow-2xl dark:border-slate-800 dark:bg-slate-900">
            <div className="flex items-center justify-between border-b border-gray-200 px-5 py-4 dark:border-slate-800">
              <div>
                <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100">Fork Skill</h2>
                <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">Clone {skill.id} into your workspace.</p>
              </div>
              <button type="button" onClick={() => setOpen(false)} className="rounded p-1 text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-slate-800">
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="space-y-3 p-5">
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300" htmlFor={`fork-${skill.id}`}>
                New skill ID
              </label>
              <input
                id={`fork-${skill.id}`}
                value={newSkillId}
                onChange={(event) => {
                  setNewSkillId(event.target.value)
                  setError(null)
                }}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    void submit()
                  }
                  if (event.key === 'Escape') {
                    setOpen(false)
                  }
                }}
                className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 outline-none focus:border-sky-500 focus:ring-2 focus:ring-sky-200 dark:border-slate-700 dark:bg-slate-950 dark:text-gray-100 dark:focus:ring-sky-900"
              />
              <p className="text-xs text-gray-500 dark:text-gray-400">Lowercase letters, numbers, and hyphens only.</p>
              {error ? <p className="text-sm text-red-600 dark:text-red-400">{error}</p> : null}
            </div>
            <div className="flex items-center justify-end gap-2 border-t border-gray-200 px-5 py-4 dark:border-slate-800">
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 dark:border-slate-700 dark:text-gray-300 dark:hover:bg-slate-800"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => void submit()}
                disabled={!valid || submitting}
                className="rounded-md bg-sky-600 px-4 py-2 text-sm font-semibold text-white hover:bg-sky-700 disabled:cursor-not-allowed disabled:bg-sky-300 dark:disabled:bg-sky-900"
              >
                {submitting ? 'Forking...' : 'Fork'}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  )
}

