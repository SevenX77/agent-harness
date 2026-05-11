import { useMemo } from 'react'
import useSWR from 'swr'
import { fetcher } from '../api/client'
import type { SkillDetail, SkillSummary } from '../api/types'

export function useSkills(selectedSkillId: string | null, initialSkills: SkillSummary[] = []) {
  const { data: skillList, error: skillListError, mutate: mutateSkills } = useSWR<SkillSummary[]>('/skills', fetcher, {
    fallbackData: initialSkills.length > 0 ? initialSkills : undefined,
  })
  const skills = useMemo(() => skillList ?? [], [skillList])
  const {
    data: skillDetail,
    error: skillDetailError,
    mutate: mutateSkillDetail,
  } = useSWR<SkillDetail>(selectedSkillId ? `/skills/${selectedSkillId}` : null, fetcher)

  return {
    skills,
    skillListError,
    mutateSkills,
    skillDetail,
    skillDetailError,
    mutateSkillDetail,
  }
}
