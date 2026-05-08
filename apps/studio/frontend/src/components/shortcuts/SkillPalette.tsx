import { Search, X } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import type { SkillSummary } from '../../api/types'

interface SkillPaletteProps {
  open: boolean
  skills: SkillSummary[]
  selectedSkillId: string | null
  onSelect: (skillId: string) => void
  onClose: () => void
}

function scoreSkill(skill: SkillSummary, query: string): number {
  const haystack = `${skill.id} ${skill.name} ${skill.description}`.toLowerCase()
  const index = haystack.indexOf(query.toLowerCase())
  return index < 0 ? Number.POSITIVE_INFINITY : index
}

export function SkillPalette({
  open,
  skills,
  selectedSkillId,
  onSelect,
  onClose,
}: SkillPaletteProps) {
  const [query, setQuery] = useState('')
  const [activeIndex, setActiveIndex] = useState(0)
  const inputRef = useRef<HTMLInputElement | null>(null)

  const filteredSkills = useMemo(() => {
    const trimmed = query.trim()
    const candidates = trimmed
      ? skills.filter((skill) => scoreSkill(skill, trimmed) < Number.POSITIVE_INFINITY)
      : skills
    return [...candidates].sort((left, right) => scoreSkill(left, trimmed) - scoreSkill(right, trimmed))
  }, [query, skills])

  useEffect(() => {
    if (!open) {
      return
    }
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setQuery('')
    setActiveIndex(0)
    window.setTimeout(() => inputRef.current?.focus(), 0)
  }, [open])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setActiveIndex(0)
  }, [query])

  if (!open) {
    return null
  }

  const activeSkill = filteredSkills[activeIndex]

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-slate-950/40 px-4 pt-[14vh]">
      <div className="w-full max-w-xl overflow-hidden rounded-md border border-slate-200 bg-white shadow-2xl dark:border-slate-800 dark:bg-slate-950">
        <div className="flex items-center gap-3 border-b border-slate-200 px-4 py-3 dark:border-slate-800">
          <Search className="h-4 w-4 text-slate-400" />
          <input
            ref={inputRef}
            data-shortcut-input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Escape') {
                onClose()
              } else if (event.key === 'ArrowDown') {
                event.preventDefault()
                setActiveIndex((index) => Math.min(filteredSkills.length - 1, index + 1))
              } else if (event.key === 'ArrowUp') {
                event.preventDefault()
                setActiveIndex((index) => Math.max(0, index - 1))
              } else if (event.key === 'Enter' && activeSkill) {
                onSelect(activeSkill.id)
                onClose()
              }
            }}
            placeholder="Search skills"
            className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-slate-400 dark:text-slate-100"
          />
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
            title="Close skill palette"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="max-h-[24rem] overflow-y-auto p-2">
          {filteredSkills.length === 0 ? (
            <div className="px-3 py-8 text-center text-sm text-slate-500 dark:text-slate-400">
              No skills found.
            </div>
          ) : null}
          {filteredSkills.map((skill, index) => (
            <button
              key={skill.id}
              type="button"
              onMouseEnter={() => setActiveIndex(index)}
              onClick={() => {
                onSelect(skill.id)
                onClose()
              }}
              className={`block w-full rounded-md px-3 py-2 text-left ${
                index === activeIndex
                  ? 'bg-sky-50 dark:bg-sky-950/40'
                  : 'hover:bg-slate-50 dark:hover:bg-slate-900'
              }`}
            >
              <div className="flex items-center justify-between gap-3">
                <span className="min-w-0">
                  <span className="block truncate text-sm font-semibold text-slate-800 dark:text-slate-100">
                    {skill.name}
                  </span>
                  <span className="block truncate text-xs text-slate-500 dark:text-slate-400">
                    {skill.description}
                  </span>
                </span>
                {skill.id === selectedSkillId ? (
                  <span className="rounded-full bg-sky-100 px-2 py-0.5 text-xs font-semibold text-sky-700 dark:bg-sky-950 dark:text-sky-300">
                    Current
                  </span>
                ) : null}
              </div>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
