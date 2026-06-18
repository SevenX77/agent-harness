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
  onOpenSettings?: () => void
}

// Publish preconditions that the user resolves in Settings — when these fail,
// the error toast offers a one-click shortcut to Settings (publish design §6).
const SETTINGS_FIXABLE_ERROR_CODES = new Set(['REGISTRY_NOT_CONFIGURED', 'APP_SETTINGS_INCOMPLETE'])

const DEFAULT_RESET_DELAY_MS = 200
export const ERROR_TOAST_MESSAGE = 'Release validation failed or the network is unavailable. The draft version is unchanged.'

function messageFromError(error: unknown): string {
  return error instanceof Error ? error.message : 'Publish failed'
}

function stringField(value: unknown, key: string): string | null {
  if (typeof value !== 'object' || value === null || !(key in value)) {
    return null
  }
  const field = (value as Record<string, unknown>)[key]
  return typeof field === 'string' && field.trim() ? field : null
}

function remoteSyncSummary(value: unknown): string | null {
  if (typeof value !== 'object' || value === null) {
    return null
  }
  const status = stringField(value, 'status')
  if (!status) {
    return null
  }
  const reason = stringField(value, 'reason') ?? stringField(value, 'error_type')
  return reason ? `remote sync ${status} (${reason})` : `remote sync ${status}`
}

function releaseSuccessMessage(result: PublishResult): string {
  const releaseVersion = stringField(result.extra, 'release_version')
  const artifactRef = typeof result.extra?.artifact_ref === 'object' ? result.extra.artifact_ref : null
  const artifactId = stringField(artifactRef, 'artifact_id')
  const contentHash =
    stringField(result.extra, 'content_hash') ?? stringField(artifactRef, 'content_hash')
  const manifestRef =
    stringField(result.extra, 'manifest_ref') ?? stringField(artifactRef, 'manifest_ref')
  const remoteSync = remoteSyncSummary(result.extra?.remote_sync)

  if (releaseVersion && artifactId && contentHash && manifestRef) {
    return [
      `Released ${releaseVersion}: ${artifactId}`,
      contentHash,
      manifestRef,
      remoteSync,
    ].filter(Boolean).join(', ')
  }

  return 'Released to production: artifact published'
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

function backendErrorCode(error: unknown): string | null {
  if (typeof error !== 'object' || error === null || !('response' in error)) {
    return null
  }
  const data = (error as { response?: { data?: unknown } }).response?.data
  if (typeof data !== 'object' || data === null || !('error_code' in data)) {
    return null
  }
  const code = (data as { error_code?: unknown }).error_code
  return typeof code === 'string' ? code : null
}

function settingsToastOptions(
  error: unknown,
  onOpenSettings: (() => void) | undefined,
): { action: { label: string; onClick: () => void } } | undefined {
  const code = backendErrorCode(error)
  if (!onOpenSettings || !code || !SETTINGS_FIXABLE_ERROR_CODES.has(code)) {
    return undefined
  }
  return { action: { label: 'Open Settings', onClick: onOpenSettings } }
}

export async function executePublishSkill({
  skillId,
  setStatus,
  setError,
  setLastResult,
  resetDelayMs = DEFAULT_RESET_DELAY_MS,
  scheduleReset = (callback, delayMs) => window.setTimeout(callback, delayMs),
  onOpenSettings,
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
      toast.success(releaseSuccessMessage(result))
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
    toast.error(backendMessage ?? ERROR_TOAST_MESSAGE, settingsToastOptions(error, onOpenSettings))
    return null
  }
}

export function usePublishSkill(
  skillId: string | null,
  onOpenSettings?: () => void,
): UsePublishSkillResult {
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
      onOpenSettings,
    })
  }, [scheduleReset, skillId, onOpenSettings])

  return { status, error, lastResult, publish }
}
