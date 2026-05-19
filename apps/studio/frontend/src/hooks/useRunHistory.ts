import { useCallback } from 'react'
import { useSWRConfig } from 'swr'
import useSWR from 'swr'
import { api, fetcher, getLocalHistory, revertSkill } from '../api/client'
import type { GitHistoryItem, RunDetail, RunListResponse, RunMetadata } from '../api/types'

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

export function useLocalHistory(skillId: string | null) {
  const { mutate: mutateGlobal } = useSWRConfig()
  const {
    data,
    error,
    isLoading,
    mutate,
  } = useSWR<GitHistoryItem[]>(skillId ? `/skills/${skillId}/history` : null, () => {
    if (!skillId) {
      return Promise.resolve([])
    }
    return getLocalHistory(skillId)
  })

  const revert = useCallback(async (sha: string) => {
    if (!skillId) {
      throw new Error('Select a skill before reverting.')
    }
    const detail = await revertSkill(skillId, sha)
    await Promise.all([
      mutate(undefined, { revalidate: true }),
      mutateGlobal(`/skills/${skillId}`, detail, { revalidate: true }),
    ])
    return detail
  }, [mutate, mutateGlobal, skillId])

  return {
    history: data ?? [],
    isLoading,
    error,
    refresh: mutate,
    revert,
  }
}

export function runTokenTotal(run: RunMetadata): number | null {
  return run.metrics?.total_tokens ?? null
}
