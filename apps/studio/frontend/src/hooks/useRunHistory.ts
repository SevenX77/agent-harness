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

/**
 * N6 #2 (history-auto-refresh) edge detector. A successful run autocommits a new
 * "Auto run" snapshot on the backend, so when a run reaches `run_ended` the Local
 * History list must be revalidated exactly once. This pure helper decides whether
 * the not-ended → ended transition warrants a refresh for the given skill/run,
 * given the key already refreshed last time. It owns the de-dupe rule so the
 * effect in Workspace stays a thin wrapper and the rule itself is unit-testable
 * under SSR (effects don't run during renderToStaticMarkup).
 *
 * Returns the new "refreshed" key when a refresh should fire (caller persists it
 * and calls refresh), or `null` when nothing should happen.
 */
export function nextLocalHistoryRefreshKey(args: {
  skillId: string | null
  completedRunId: string | null
  lastRefreshedKey: string | null
}): string | null {
  const { skillId, completedRunId, lastRefreshedKey } = args
  if (!skillId || !completedRunId) {
    return null
  }
  const key = `${skillId}::${completedRunId}`
  if (key === lastRefreshedKey) {
    return null
  }
  return key
}
