import type { SkillSummary } from '../../api/types'

export function formatLastRun(value: string | null) {
  if (!value) {
    return 'No runs yet'
  }

  try {
    return new Intl.DateTimeFormat(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    }).format(new Date(value))
  } catch {
    return value
  }
}

export function sortRecent(skills: SkillSummary[], recentSkillIds: string[]) {
  const byId = new Map(skills.map((skill) => [skill.id, skill]))
  const recent = recentSkillIds.map((id) => byId.get(id)).filter((skill): skill is SkillSummary => Boolean(skill))
  const remaining = skills
    .filter((skill) => !recentSkillIds.includes(skill.id))
    .sort((a, b) => (b.last_run_at ?? '').localeCompare(a.last_run_at ?? ''))

  return [...recent, ...remaining]
}

export function skillIdFromPath(path: string) {
  const name = path.split(/[\\/]/).filter(Boolean).pop() ?? 'imported-skill'
  const normalized = name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')
  const withLetter = /^[a-z]/.test(normalized) ? normalized : `skill-${normalized}`
  return withLetter || 'imported-skill'
}

export function normalizeSkillId(value: string) {
  const normalized = value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')
  const withLetter = /^[a-z]/.test(normalized) ? normalized : `skill-${normalized}`
  return withLetter || 'new-skill'
}

export function shortPath(path: string | null) {
  if (!path) {
    return 'AgentStudio/Skills'
  }
  const parts = path.split(/[\\/]/).filter(Boolean)
  return parts.length > 3 ? `.../${parts.slice(-3).join('/')}` : path
}
