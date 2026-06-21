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

// 读法 B (PM 2026-06-20): publish keeps the local-only safety net. When the
// registry/identity config is missing, the LOCAL release still succeeds and the
// remote sync leg is marked `skipped` with one of these reasons (backend
// skills.py:710-732). The FE surfaces a NON-blocking notice keyed on the reason —
// the backend never throws an error code for these, so there is no catch-path
// whitelist. This set MUST equal exactly the reasons the backend emits.
export const FE_HANDLED_SKIP_REASONS = new Set(['registry_not_configured', 'app_settings_incomplete'])

// app_settings_incomplete is fixable in General settings (author identity / user_id),
// so the success toast offers a one-click jump there. registry_not_configured has no
// Settings field yet → informational only.
const SETTINGS_FIXABLE_SKIP_REASON = 'app_settings_incomplete'

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

// The skip reason on an OK result whose remote sync was skipped — but only when it
// is one the FE knows how to surface (read法 B). Returns null otherwise.
function handledSkipReason(result: PublishResult): string | null {
  const remoteSync = result.extra?.remote_sync
  if (typeof remoteSync !== 'object' || remoteSync === null) {
    return null
  }
  if (stringField(remoteSync, 'status') !== 'skipped') {
    return null
  }
  const reason = stringField(remoteSync, 'reason')
  return reason && FE_HANDLED_SKIP_REASONS.has(reason) ? reason : null
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

  if (remoteSync) {
    return `Released to production: artifact published, ${remoteSync}`
  }

  return 'Released to production: artifact published'
}

// 读法 B: when the remote sync was skipped because the author identity is missing,
// the (still successful) toast offers a one-click jump to Settings to set it. Other
// skip reasons (registry_not_configured) have no Settings field yet → no action.
function successToastOptions(
  result: PublishResult,
  onOpenSettings: (() => void) | undefined,
): { action: { label: string; onClick: () => void } } | undefined {
  if (!onOpenSettings || handledSkipReason(result) !== SETTINGS_FIXABLE_SKIP_REASON) {
    return undefined
  }
  return { action: { label: 'Open Settings', onClick: onOpenSettings } }
}

// Surface the backend's clear, typed thrown error (e.g. a genuine PUBLISH_FAILED /
// PUBLISH_CONFLICT) instead of a generic toast. Returns null for plain network
// errors so the generic fallback still applies.
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
      toast.success(releaseSuccessMessage(result), successToastOptions(result, onOpenSettings))
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
