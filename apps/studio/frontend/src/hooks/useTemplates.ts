import useSWR from 'swr'
import { fetcher } from '../api/client'
import type { SkillTemplate } from '../api/types'

export function useTemplates() {
  const { data, error, isLoading, mutate } = useSWR<SkillTemplate[]>('/templates', fetcher)

  return {
    templates: data ?? [],
    templatesError: error,
    templatesLoading: isLoading,
    mutateTemplates: mutate,
  }
}

