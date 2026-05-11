import { useCallback, useState } from 'react'

export function readRecentSkillIds() {
  if (typeof window === 'undefined') {
    return []
  }

  try {
    const parsed = JSON.parse(localStorage.getItem('recentSkills') || '[]') as unknown
    return Array.isArray(parsed) ? parsed.filter((id): id is string => typeof id === 'string') : []
  } catch {
    return []
  }
}

export function useRecentSkills(validSkillIds: string[] = []) {
  const [recentSkills, setRecentSkills] = useState<string[]>(() => {
    const ids = readRecentSkillIds()
    if (validSkillIds.length === 0) {
      return ids
    }
    const valid = new Set(validSkillIds)
    return ids.filter((id) => valid.has(id))
  })

  const rememberSkill = useCallback((skillId: string) => {
    setRecentSkills((previous) => {
      const next = [skillId, ...previous.filter((id) => id !== skillId)].slice(0, 10)
      localStorage.setItem('recentSkills', JSON.stringify(next))
      return next
    })
  }, [])

  return { recentSkills, rememberSkill }
}
