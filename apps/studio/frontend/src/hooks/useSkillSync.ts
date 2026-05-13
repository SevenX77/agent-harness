import { useCallback, useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { syncSkill } from '../api/client'
import type { CollaborateResult, SyncSkillReq } from '../api/types'

export type SkillSyncStatus =
  | 'idle'
  | 'saving'
  | 'syncing'
  | 'submitting'
  | 'success'
  | 'error'
  | 'requires_review'

interface UseSkillSyncResult {
  status: SkillSyncStatus
  error: string | null
  lastResult: CollaborateResult | null
  save: () => Promise<void>
  sync: () => Promise<void>
  submit: (devBranch: string, prTitle: string) => Promise<void>
}

interface UseSkillSyncOptions {
  onSyncSuccess?: (result: CollaborateResult) => void
}

interface ExecuteSkillSyncOptions {
  skillId: string | null
  request: SyncSkillReq
  pendingStatus: SkillSyncStatus
  successMessage: (result: CollaborateResult) => string
  onSuccess?: (result: CollaborateResult) => void
  setStatus: (status: SkillSyncStatus) => void
  setError: (error: string | null) => void
  setLastResult: (result: CollaborateResult | null) => void
  resetDelayMs?: number
  scheduleReset?: (callback: () => void, delayMs: number) => unknown
}

const DEFAULT_RESET_DELAY_MS = 200

function messageFromError(error: unknown): string {
  return error instanceof Error ? error.message : 'Sync failed'
}

export async function executeSkillSync({
  skillId,
  request,
  pendingStatus,
  successMessage,
  onSuccess,
  setStatus,
  setError,
  setLastResult,
  resetDelayMs = DEFAULT_RESET_DELAY_MS,
  scheduleReset = (callback, delayMs) => window.setTimeout(callback, delayMs),
}: ExecuteSkillSyncOptions): Promise<CollaborateResult | null> {
  if (!skillId) {
    console.warn('Cannot sync skill without a selected skillId')
    return null
  }

  setStatus(pendingStatus)
  setError(null)

  try {
    const result = await syncSkill(skillId, request)
    setLastResult(result)

    if (result.status === 'ok') {
      setStatus('success')
      onSuccess?.(result)
      toast.success(successMessage(result))
      scheduleReset(() => setStatus('idle'), resetDelayMs)
      return result
    }

    if (result.status === 'requires_review') {
      setStatus('requires_review')
      toast.success(`Main branch protected. Opened PR for review: ${result.pr_url ?? 'review required'}`)
      return result
    }

    setStatus('error')
    setError(result.message)
    toast.error(result.message)
    return result
  } catch (error) {
    const message = messageFromError(error)
    setStatus('error')
    setError(message)
    toast.error(message)
    return null
  }
}

export function useSkillSync(skillId: string | null, options?: UseSkillSyncOptions): UseSkillSyncResult {
  const [status, setStatus] = useState<SkillSyncStatus>('idle')
  const [error, setError] = useState<string | null>(null)
  const [lastResult, setLastResult] = useState<CollaborateResult | null>(null)
  const resetTimerRef = useRef<number | null>(null)

  useEffect(() => {
    return () => {
      if (resetTimerRef.current !== null) {
        window.clearTimeout(resetTimerRef.current)
      }
    }
  }, [])

  const scheduleReset = useCallback((callback: () => void, delayMs: number) => {
    if (resetTimerRef.current !== null) {
      window.clearTimeout(resetTimerRef.current)
    }
    resetTimerRef.current = window.setTimeout(callback, delayMs)
  }, [])

  const run = useCallback(
    async (
      request: SyncSkillReq,
      pendingStatus: SkillSyncStatus,
      successMessage: (result: CollaborateResult) => string,
      onSuccess?: (result: CollaborateResult) => void,
    ) => {
      await executeSkillSync({
        skillId,
        request,
        pendingStatus,
        successMessage,
        onSuccess,
        setStatus,
        setError,
        setLastResult,
        scheduleReset,
      })
    },
    [scheduleReset, skillId],
  )

  const save = useCallback(async () => {
    await run({ action: 'save_to_team' }, 'saving', () => 'Saved to team')
  }, [run])

  const sync = useCallback(async () => {
    await run(
      { action: 'sync_from_team' },
      'syncing',
      (result) =>
        result.extra?.latest_restored === true ? 'Synced from team — latest snapshot restored' : 'Synced from team',
      options?.onSyncSuccess,
    )
  }, [options?.onSyncSuccess, run])

  const submit = useCallback(
    async (devBranch: string, prTitle: string) => {
      await run(
        { action: 'submit_for_review', dev_branch: devBranch, pr_title: prTitle },
        'submitting',
        (result) => `PR opened: ${result.pr_url ?? 'review created'}`,
      )
    },
    [run],
  )

  return { status, error, lastResult, save, sync, submit }
}
