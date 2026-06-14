import { useCallback, useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { publishSkill } from '../api/client'
import type { PublishResult } from '../api/types'

export type PublishSkillStatus = 'idle' | 'publishing' | 'success' | 'error'

interface UsePublishSkillResult {
  status: PublishSkillStatus
  error: string | null
  lastResult: PublishResult | null
  publish: () => Promise<void>
}

interface ExecutePublishSkillOptions {
  skillId: string | null
  setStatus: (status: PublishSkillStatus) => void
  setError: (error: string | null) => void
  setLastResult: (result: PublishResult | null) => void
  resetDelayMs?: number
  scheduleReset?: (callback: () => void, delayMs: number) => unknown
}

const DEFAULT_RESET_DELAY_MS = 200
export const ERROR_TOAST_MESSAGE = 'Release validation failed or the network is unavailable. The draft version is unchanged.'

function messageFromError(error: unknown): string {
  return error instanceof Error ? error.message : 'Publish failed'
}

// Surface the backend's clear, typed error (e.g. REGISTRY_NOT_CONFIGURED —
// "Artifact Registry Host 未配置") instead of a generic toast, per publish
// design F2 ("missing settings gives a clear error"). Returns null for plain
// network errors so the generic fallback still applies.
function backendErrorMessage(error: unknown): string | null {
  if (typeof error !== 'object' || error === null || !('response' in error)) {
    return null
  }
  const data = (error as { response?: { data?: unknown } }).response?.data
  if (typeof data !== 'object' || data === null || !('message' in data)) {
    return null
  }
  const message = (data as { message?: unknown }).message
  return typeof message === 'string' && message.trim() ? message : null
}

export async function executePublishSkill({
  skillId,
  setStatus,
  setError,
  setLastResult,
  resetDelayMs = DEFAULT_RESET_DELAY_MS,
  scheduleReset = (callback, delayMs) => window.setTimeout(callback, delayMs),
}: ExecutePublishSkillOptions): Promise<PublishResult | null> {
  if (!skillId) {
    console.warn('Cannot publish without a selected skillId')
    return null
  }

  setStatus('publishing')
  setError(null)

  try {
    const result = await publishSkill(skillId)
    setLastResult(result)
    if (result.status === 'ok') {
      setStatus('success')
      toast.success(`Released to production: ${result.artifact_id ?? 'artifact published'}`)
      scheduleReset(() => setStatus('idle'), resetDelayMs)
      return result
    }

    setStatus('error')
    setError(result.message)
    toast.error(result.message?.trim() ? result.message : ERROR_TOAST_MESSAGE)
    return result
  } catch (error) {
    const backendMessage = backendErrorMessage(error)
    setStatus('error')
    setError(backendMessage ?? messageFromError(error))
    toast.error(backendMessage ?? ERROR_TOAST_MESSAGE)
    return null
  }
}

export function usePublishSkill(skillId: string | null): UsePublishSkillResult {
  const [status, setStatus] = useState<PublishSkillStatus>('idle')
  const [error, setError] = useState<string | null>(null)
  const [lastResult, setLastResult] = useState<PublishResult | null>(null)
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

  const publish = useCallback(async () => {
    await executePublishSkill({
      skillId,
      setStatus,
      setError,
      setLastResult,
      scheduleReset,
    })
  }, [scheduleReset, skillId])

  return { status, error, lastResult, publish }
}
