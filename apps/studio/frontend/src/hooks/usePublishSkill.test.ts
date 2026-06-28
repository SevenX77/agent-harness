import { beforeEach, describe, expect, it, vi } from 'vitest'
import { toast } from 'sonner'
import { publishSkill } from '../api/client'
import type { PublishResult } from '../api/types'
import {
  ERROR_TOAST_MESSAGE,
  FE_HANDLED_SKIP_REASONS,
  executePublishSkill,
  type PublishSkillStatus,
} from './usePublishSkill'

vi.mock('../api/client', () => ({
  publishSkill: vi.fn(),
}))

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

const mockPublishSkill = vi.mocked(publishSkill)
const mockToast = vi.mocked(toast)

function setupExecute(onOpenSettings?: () => void) {
  const statusCalls: PublishSkillStatus[] = []
  const setError = vi.fn()
  const setLastResult = vi.fn()
  const scheduleReset = vi.fn((callback: () => void) => callback())

  const execute = () =>
    executePublishSkill({
      skillId: 'skill-1',
      setStatus: (status) => statusCalls.push(status),
      setError,
      setLastResult,
      scheduleReset,
      onOpenSettings,
    })

  return { execute, statusCalls, setError, setLastResult, scheduleReset }
}

describe('executePublishSkill', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('publish calls publishSkill action and uses generic success copy without committed release identity', async () => {
    const result: PublishResult = {
      status: 'ok',
      artifact_id: 'art-999',
      message: 'Published',
      extra: {},
    }
    mockPublishSkill.mockResolvedValue(result)
    const { execute, statusCalls, setLastResult, scheduleReset } = setupExecute()

    await execute()

    expect(mockPublishSkill).toHaveBeenCalledWith('skill-1')
    expect(statusCalls).toEqual(['publishing', 'success', 'idle'])
    expect(setLastResult).toHaveBeenCalledWith(result)
    expect(mockToast.success).toHaveBeenCalledWith('Released to production: artifact published', undefined)
    expect(mockToast.success).not.toHaveBeenCalledWith(expect.stringContaining('art-999'), expect.anything())
    expect(scheduleReset).toHaveBeenCalledWith(expect.any(Function), 200)
  })

  it('success toast includes release version, content hash, and manifest ref when backend returns them', async () => {
    const result: PublishResult = {
      status: 'ok',
      artifact_id: 'art-123',
      message: 'Published',
      extra: {
        release_version: '2026.06.11',
        artifact_ref: {
          artifact_id: 'text-segmentation',
          content_hash: `sha256:${'a'.repeat(64)}`,
          manifest_ref: 'manifests/text-segmentation.json',
          store: 'product',
        },
        remote_sync: {
          status: 'skipped',
          reason: 'registry_not_configured',
        },
      },
    }
    mockPublishSkill.mockResolvedValue(result)
    const { execute } = setupExecute()

    await execute()

    expect(mockToast.success).toHaveBeenCalledWith(
      `Released 2026.06.11: text-segmentation, sha256:${'a'.repeat(64)}, manifests/text-segmentation.json, remote sync skipped (registry_not_configured)`,
      undefined,
    )
  })

  it('uses generic success copy when release identity is missing content metadata', async () => {
    const result = {
      status: 'ok',
      artifact_id: 'art-123',
      message: 'Published',
      extra: {
        release_version: '2026.06.11',
        artifact_ref: {
          artifact_id: 'text-segmentation',
          store: 'product',
        },
      },
    } as unknown as PublishResult
    mockPublishSkill.mockResolvedValue(result)
    const { execute } = setupExecute()

    await execute()

    expect(mockToast.success).toHaveBeenCalledWith('Released to production: artifact published', undefined)
    expect(mockToast.success).not.toHaveBeenCalledWith(
      expect.stringContaining('text-segmentation'),
      expect.anything(),
    )
  })

  // 读法 B (PM 2026-06-20): local publish succeeds even when registry/identity
  // config is missing. The remote sync leg is marked skipped and the FE surfaces
  // a NON-blocking notice keyed on the skip reason — never a thrown error code.
  it('ok+skip surfaces the skip reason in the success message (registry_not_configured)', async () => {
    const result: PublishResult = {
      status: 'ok',
      artifact_id: 'art-1',
      message: 'Published',
      extra: {
        remote_sync: { status: 'skipped', reason: 'registry_not_configured' },
      },
    }
    mockPublishSkill.mockResolvedValue(result)
    const { execute, statusCalls } = setupExecute()

    await execute()

    expect(statusCalls).toEqual(['publishing', 'success', 'idle'])
    expect(mockToast.success).toHaveBeenCalledWith(
      expect.stringContaining('remote sync skipped (registry_not_configured)'),
      undefined,
    )
  })

  it('registry_not_configured skip is informational only — no Open Settings action', async () => {
    const result: PublishResult = {
      status: 'ok',
      artifact_id: 'art-1',
      message: 'Published',
      extra: {
        remote_sync: { status: 'skipped', reason: 'registry_not_configured' },
      },
    }
    mockPublishSkill.mockResolvedValue(result)
    const onOpenSettings = vi.fn()
    const { execute } = setupExecute(onOpenSettings)

    await execute()

    // No registry Settings field exists yet -> informational, no action button.
    expect(mockToast.success).toHaveBeenCalledWith(
      expect.stringContaining('remote sync skipped (registry_not_configured)'),
      undefined,
    )
    expect(onOpenSettings).not.toHaveBeenCalled()
  })

  it('app_settings_incomplete skip yields an Open Settings action on the success toast', async () => {
    const result: PublishResult = {
      status: 'ok',
      artifact_id: 'art-1',
      message: 'Published',
      extra: {
        remote_sync: { status: 'skipped', reason: 'app_settings_incomplete' },
      },
    }
    mockPublishSkill.mockResolvedValue(result)
    const onOpenSettings = vi.fn()
    const { execute, statusCalls } = setupExecute(onOpenSettings)

    await execute()

    // Still a SUCCESS toast (local publish succeeded), just non-blocking guidance.
    expect(statusCalls).toEqual(['publishing', 'success', 'idle'])
    expect(mockToast.success).toHaveBeenCalledWith(
      expect.stringContaining('remote sync skipped (app_settings_incomplete)'),
      { action: { label: 'Open Settings', onClick: onOpenSettings } },
    )
  })

  it('app_settings_incomplete skip stays informational when no onOpenSettings is wired', async () => {
    const result: PublishResult = {
      status: 'ok',
      artifact_id: 'art-1',
      message: 'Published',
      extra: {
        remote_sync: { status: 'skipped', reason: 'app_settings_incomplete' },
      },
    }
    mockPublishSkill.mockResolvedValue(result)
    const { execute } = setupExecute()

    await execute()

    expect(mockToast.success).toHaveBeenCalledWith(
      expect.stringContaining('remote sync skipped (app_settings_incomplete)'),
      undefined,
    )
  })

  // Consistency test (replaces the old error-code consistency claim, test#3):
  // the FE-handled skip-reason set must equal exactly the reasons the backend
  // emits on the ok+skip path (skills.py:710-732):
  //   registry_not_configured | app_settings_incomplete
  it('FE-handled skip reasons equal exactly the backend-emitted reasons', () => {
    const backendEmittedSkipReasons = new Set(['registry_not_configured', 'app_settings_incomplete'])

    expect(FE_HANDLED_SKIP_REASONS).toEqual(backendEmittedSkipReasons)
  })

  it('surfaces publish version conflicts without the generic network fallback', async () => {
    mockPublishSkill.mockRejectedValue({
      response: {
        status: 409,
        data: {
          error_code: 'PUBLISH_CONFLICT',
          message: 'Release version 1.0.0 already exists',
          details: {
            release_version: '1.0.0',
          },
        },
      },
    })
    const { execute, statusCalls, setError } = setupExecute()

    await execute()

    expect(statusCalls).toEqual(['publishing', 'error'])
    expect(setError).toHaveBeenCalledWith('Release version 1.0.0 already exists')
    expect(mockToast.error).toHaveBeenCalledWith('Release version 1.0.0 already exists')
    expect(mockToast.error).not.toHaveBeenCalledWith(ERROR_TOAST_MESSAGE)
  })

  it('publish error toasts business-named error message', async () => {
    mockPublishSkill.mockRejectedValue(new Error('network failed'))
    const { execute, statusCalls, setError } = setupExecute()

    await execute()

    expect(statusCalls).toEqual(['publishing', 'error'])
    expect(setError).toHaveBeenCalledWith('network failed')
    expect(mockToast.error).toHaveBeenCalledWith(ERROR_TOAST_MESSAGE)
  })

  it('surfaces a thrown backend typed error as a plain error toast (no Settings action)', async () => {
    // Under 读法 B publish never throws REGISTRY_NOT_CONFIGURED; a thrown typed
    // error (e.g. a genuine validation failure) is a plain error toast.
    mockPublishSkill.mockRejectedValue({
      response: { data: { error_code: 'PUBLISH_FAILED', message: 'Release pipeline failed' } },
    })
    const onOpenSettings = vi.fn()
    const { execute, statusCalls, setError } = setupExecute(onOpenSettings)

    await execute()

    expect(statusCalls).toEqual(['publishing', 'error'])
    expect(setError).toHaveBeenCalledWith('Release pipeline failed')
    expect(mockToast.error).toHaveBeenCalledWith('Release pipeline failed')
    expect(onOpenSettings).not.toHaveBeenCalled()
  })
})
