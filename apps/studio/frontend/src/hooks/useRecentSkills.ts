import { useCallback, useState } from 'react'

export function useRecentSkills() {
  const [recentSkills, setRecentSkills] = useState<string[]>(() => {
    if (typeof window !== 'undefined') {
      try {
        return JSON.parse(localStorage.getItem('recentSkills') || '[]') as string[]
      } catch {
        return []
      }
    }
    return []
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
