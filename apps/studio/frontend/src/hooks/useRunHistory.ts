import { useCallback } from 'react'
import useSWR from 'swr'
import { api, fetcher } from '../api/client'
import type { RunDetail, RunListResponse, RunMetadata } from '../api/types'

export function useRunHistory(skillId: string | null) {
  const {
    data,
    error,
    isLoading,
    mutate,
  } = useSWR<RunListResponse>(skillId ? `/skills/${skillId}/runs` : null, fetcher)

  const deleteRun = useCallback(async (runId: string) => {
    if (!skillId) {
      return
    }
    await api.delete(`/skills/${skillId}/runs/${runId}`)
    await mutate((current) => current
      ? {
        total: Math.max(0, current.total - 1),
        runs: current.runs.filter((run) => run.run_id !== runId),
      }
      : current, { revalidate: true })
  }, [mutate, skillId])

  const startOptimisticRun = useCallback(async (run: RunMetadata) => {
    await mutate((current) => ({
      total: current ? current.total + 1 : 1,
      runs: [run, ...(current?.runs ?? []).filter((item) => item.run_id !== run.run_id)],
    }), { revalidate: true })
  }, [mutate])

  const fetchRunDetail = useCallback(async (runId: string): Promise<RunDetail | null> => {
    if (!skillId) {
      return null
    }
    const response = await api.get<RunDetail>(`/skills/${skillId}/runs/${runId}`)
    return response.data
  }, [skillId])

  return {
    runs: data?.runs ?? [],
    total: data?.total ?? 0,
    error,
    isLoading,
    refresh: mutate,
    startOptimisticRun,
    deleteRun,
    fetchRunDetail,
  }
}

export function runTokenTotal(run: RunMetadata): number | null {
  return run.metrics?.total_tokens ?? null
}
