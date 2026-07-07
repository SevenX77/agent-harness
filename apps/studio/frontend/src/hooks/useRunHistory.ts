import { useCallback } from 'react'
import { useSWRConfig } from 'swr'
import useSWR from 'swr'
import { api, fetcher, getLocalHistory, revertSkill } from '../api/client'
import type { GitHistoryItem, RunListResponse, RunMetadata } from '../api/types'
import { STUDIO_TRUTH_SWR_CONFIG } from './studio-swr-policy'

const runHistoryKey = (skillId: string) => `/skills/${skillId}/runs`

function projectDeletedRun(current: RunListResponse | undefined, runId: string): RunListResponse | undefined {
  if (!current) {
    return current
  }
  const runs = current.runs.filter((run) => run.run_id !== runId)
  const removed = current.runs.length - runs.length
  if (removed === 0) {
    return current
  }
  return {
    total: Math.max(0, current.total - removed),
    runs,
  }
}

function projectRunMetadata(current: RunListResponse | undefined, run: RunMetadata): RunListResponse {
  const previousRuns = current?.runs ?? []
  const existed = previousRuns.some((item) => item.run_id === run.run_id)
  return {
    total: current ? current.total + (existed ? 0 : 1) : 1,
    runs: [run, ...previousRuns.filter((item) => item.run_id !== run.run_id)],
  }
}

export function useRunHistory(skillId: string | null) {
  const {
    data,
    error,
    isLoading,
    mutate,
  } = useSWR<RunListResponse>(skillId ? `/skills/${skillId}/runs` : null, fetcher, STUDIO_TRUTH_SWR_CONFIG)

  const deleteRun = useCallback(async (runId: string) => {
    if (!skillId) {
      return
    }
    await api.delete(`/skills/${skillId}/runs/${runId}`)
    await mutate((current) => projectDeletedRun(current, runId), { revalidate: false })
  }, [mutate, skillId])

  const startOptimisticRun = useCallback(async (run: RunMetadata) => {
    await mutate((current) => projectRunMetadata(current, run), { revalidate: false })
  }, [mutate])

  return {
    runs: data?.runs ?? [],
    total: data?.total ?? 0,
    error,
    isLoading,
    refresh: mutate,
    startOptimisticRun,
    deleteRun,
  }
}

export function useRunHistoryProjection(skillId: string | null) {
  const { mutate } = useSWRConfig()
  const projectRun = useCallback(async (run: RunMetadata) => {
    if (!skillId) {
      return
    }
    await mutate<RunListResponse>(
      runHistoryKey(skillId),
      (current) => projectRunMetadata(current, run),
      { revalidate: false },
    )
  }, [mutate, skillId])

  return { projectRun }
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
  }, STUDIO_TRUTH_SWR_CONFIG)

  const revert = useCallback(async (sha: string) => {
    if (!skillId) {
      throw new Error('Select a skill before reverting.')
    }
    const detail = await revertSkill(skillId, sha)
    await Promise.all([
      mutate(undefined, { revalidate: true }),
      mutateGlobal(`/skills/${skillId}`, detail, { revalidate: false }),
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

export type ArchiveFeedbackVariant = 'success' | 'warning'

export interface ArchiveFeedback {
  variant: ArchiveFeedbackVariant
  message: string
}

/**
 * N6 #1 (autocommit-feedback) read projection. After a successful run the backend
 * autocommits a local "Auto run" snapshot and records the outcome on the run
 * metadata's `git_status` (committed / locked / failed / no_git — see
 * RunMetadata in api/types). The `run_ended` stream event carries no metadata,
 * so Workspace must re-fetch the run detail (GET /skills/{id}/runs/{run_id}) and
 * pass the resulting `git_status` here. This pure mapping decides the user-facing
 * archive feedback so the rule is unit-testable under SSR; the effect in Workspace
 * stays a thin wrapper that fetches then toasts.
 *
 * Returns `null` for a still-running / unknown status (e.g. metadata not yet
 * backfilled) so the caller stays silent rather than claiming an outcome.
 */
export function archiveFeedbackForGitStatus(
  gitStatus: RunMetadata['git_status'] | undefined,
): ArchiveFeedback | null {
  switch (gitStatus) {
    case 'committed':
      return { variant: 'success', message: 'Auto-archived — revert from Local History.' }
    case 'no_git':
      return {
        variant: 'success',
        message: 'Run archived (this skill has no git repo, so no revertable snapshot).',
      }
    case 'locked':
      return { variant: 'warning', message: 'Run not archived (git index was locked).' }
    case 'failed':
      return { variant: 'warning', message: 'Run not archived (auto-commit failed).' }
    default:
      return null
  }
}
