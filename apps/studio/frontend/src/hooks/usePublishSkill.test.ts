import { beforeEach, describe, expect, it, vi } from 'vitest'
import { toast } from 'sonner'
import { publishSkill } from '../api/client'
import type { PublishResult } from '../api/types'
import { ERROR_TOAST_MESSAGE, executePublishSkill, type PublishSkillStatus } from './usePublishSkill'

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

function setupExecute() {
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
    expect(mockToast.success).toHaveBeenCalledWith('Released to production: artifact published')
    expect(mockToast.success).not.toHaveBeenCalledWith(expect.stringContaining('art-999'))
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

    expect(mockToast.success).toHaveBeenCalledWith('Released to production: artifact published')
    expect(mockToast.success).not.toHaveBeenCalledWith(expect.stringContaining('text-segmentation'))
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
    expect(mockToast.error).toHaveBeenCalledWith(
      'Release version 1.0.0 already exists',
      undefined,
    )
    expect(mockToast.error).not.toHaveBeenCalledWith(ERROR_TOAST_MESSAGE, undefined)
  })

  it('publish error toasts business-named error message', async () => {
    mockPublishSkill.mockRejectedValue(new Error('network failed'))
    const { execute, statusCalls, setError } = setupExecute()

    await execute()

    expect(statusCalls).toEqual(['publishing', 'error'])
    expect(setError).toHaveBeenCalledWith('network failed')
    expect(mockToast.error).toHaveBeenCalledWith(ERROR_TOAST_MESSAGE, undefined)
  })

  it('surfaces the backend typed error message (e.g. registry not configured)', async () => {
    mockPublishSkill.mockRejectedValue({
      response: { data: { error_code: 'REGISTRY_NOT_CONFIGURED', message: 'Artifact Registry Host 未配置' } },
    })
    const { execute, statusCalls, setError } = setupExecute()

    await execute()

    expect(statusCalls).toEqual(['publishing', 'error'])
    expect(setError).toHaveBeenCalledWith('Artifact Registry Host 未配置')
    // No onOpenSettings provided -> no Settings action.
    expect(mockToast.error).toHaveBeenCalledWith('Artifact Registry Host 未配置', undefined)
  })

  it('offers an Open Settings shortcut for settings-fixable publish errors (design §6)', async () => {
    mockPublishSkill.mockRejectedValue({
      response: { data: { error_code: 'REGISTRY_NOT_CONFIGURED', message: 'Artifact Registry Host 未配置' } },
    })
    const onOpenSettings = vi.fn()
    await executePublishSkill({
      skillId: 'skill-1',
      setStatus: vi.fn(),
      setError: vi.fn(),
      setLastResult: vi.fn(),
      scheduleReset: vi.fn((callback: () => void) => callback()),
      onOpenSettings,
    })

    expect(mockToast.error).toHaveBeenCalledWith('Artifact Registry Host 未配置', {
      action: { label: 'Open Settings', onClick: onOpenSettings },
    })
  })
})
