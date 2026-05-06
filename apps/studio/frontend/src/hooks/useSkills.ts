import { useMemo } from 'react'
import useSWR from 'swr'
import { fetcher } from '../api/client'
import type { SkillDetail, SkillSummary } from '../api/types'

export function useSkills(selectedSkillId: string | null) {
  const { data: skillList, error: skillListError } = useSWR<SkillSummary[]>('/skills', fetcher)
  const skills = useMemo(() => skillList ?? [], [skillList])
  const {
    data: skillDetail,
    error: skillDetailError,
    mutate: mutateSkillDetail,
  } = useSWR<SkillDetail>(selectedSkillId ? `/skills/${selectedSkillId}` : null, fetcher)

  return {
    skills,
    skillListError,
    skillDetail,
    skillDetailError,
    mutateSkillDetail,
  }
}
