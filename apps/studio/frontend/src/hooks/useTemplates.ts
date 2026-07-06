import useSWR from 'swr'
import { fetcher } from '../api/client'
import type { SkillTemplate } from '../api/types'
import { STUDIO_TRUTH_SWR_CONFIG } from './studio-swr-policy'

interface UseTemplatesOptions {
  enabled?: boolean
}

export function useTemplates({ enabled = true }: UseTemplatesOptions = {}) {
  const { data, error, isLoading, mutate } = useSWR<SkillTemplate[]>(
    enabled ? '/templates' : null,
    fetcher,
    STUDIO_TRUTH_SWR_CONFIG,
  )

  return {
    templates: data ?? [],
    templatesError: error,
    templatesLoading: isLoading,
    mutateTemplates: mutate,
  }
}
