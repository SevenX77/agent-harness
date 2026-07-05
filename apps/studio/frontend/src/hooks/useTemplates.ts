import useSWR from 'swr'
import { fetcher } from '../api/client'
import type { SkillTemplate } from '../api/types'
import { STUDIO_TRUTH_SWR_CONFIG } from './studio-swr-policy'

export function useTemplates() {
  const { data, error, isLoading, mutate } = useSWR<SkillTemplate[]>('/templates', fetcher, STUDIO_TRUTH_SWR_CONFIG)

  return {
    templates: data ?? [],
    templatesError: error,
    templatesLoading: isLoading,
    mutateTemplates: mutate,
  }
}
