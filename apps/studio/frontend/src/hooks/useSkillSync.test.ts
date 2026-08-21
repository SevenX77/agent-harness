import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AxiosError, AxiosHeaders, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios'
import { toast } from 'sonner'
import i18n from '../i18n'
import { syncSkill } from '../api/client'
import type { CollaborateResult, SyncSkillReq } from '../api/types'
import { executeSkillSync, type SkillSyncStatus } from './useSkillSync'

vi.mock('../api/client', () => ({
  syncSkill: vi.fn(),
}))

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

const mockSyncSkill = vi.mocked(syncSkill)
const mockToast = vi.mocked(toast)

function setupExecute(request: SyncSkillReq, pendingStatus: SkillSyncStatus) {
  const statusCalls: SkillSyncStatus[] = []
  const setError = vi.fn()
  const setLastResult = vi.fn()
  const scheduleReset = vi.fn()
  const onSuccess = vi.fn()

  const execute = () =>
    executeSkillSync({
      skillId: 'skill-1',
      request,
      pendingStatus,
      successMessage: (result) => {
        if (request.action === 'save_to_team') return 'Saved to team'
        if (request.action === 'sync_from_team') {
          return result.extra?.latest_restored === true
            ? 'Synced from team — latest snapshot restored'
            : 'Synced from team'
        }
        return `PR opened: ${result.pr_url ?? 'review created'}`
      },
      onSuccess: request.action === 'sync_from_team' ? onSuccess : undefined,
      setStatus: (status) => statusCalls.push(status),
      setError,
      setLastResult,
      scheduleReset,
    })

  return { execute, statusCalls, setError, setLastResult, scheduleReset, onSuccess }
}

describe('executeSkillSync', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(async () => {
    await i18n.changeLanguage('en')
  })

  it('save calls save_to_team, marks success, and shows success toast', async () => {
    const result: CollaborateResult = { status: 'ok', message: 'saved' }
    mockSyncSkill.mockResolvedValue(result)
    const { execute, statusCalls, setLastResult, scheduleReset } = setupExecute({ action: 'save_to_team' }, 'saving')

    await execute()

    expect(mockSyncSkill).toHaveBeenCalledWith('skill-1', { action: 'save_to_team' })
    expect(statusCalls).toEqual(['saving', 'success'])
    expect(setLastResult).toHaveBeenCalledWith(result)
    expect(mockToast.success).toHaveBeenCalledWith('Saved to team')
    expect(scheduleReset).toHaveBeenCalledWith(expect.any(Function), 200)
  })

  it('sync calls sync_from_team', async () => {
    mockSyncSkill.mockResolvedValue({ status: 'ok', message: 'synced' })
    const { execute } = setupExecute({ action: 'sync_from_team' }, 'syncing')

    await execute()

    expect(mockSyncSkill).toHaveBeenCalledWith('skill-1', { action: 'sync_from_team' })
    expect(mockToast.success).toHaveBeenCalledWith('Synced from team')
  })

  it('sync calls onSyncSuccess with result', async () => {
    const result: CollaborateResult = { status: 'ok', message: 'synced', extra: { latest_restored: true } }
    mockSyncSkill.mockResolvedValue(result)
    const { execute, onSuccess } = setupExecute({ action: 'sync_from_team' }, 'syncing')

    await execute()

    expect(onSuccess).toHaveBeenCalledTimes(1)
    expect(onSuccess).toHaveBeenCalledWith(result)
  })

  it('sync toast mentions latest snapshot when latest_restored is true', async () => {
    mockSyncSkill.mockResolvedValue({ status: 'ok', message: 'synced', extra: { latest_restored: true } })
    const { execute } = setupExecute({ action: 'sync_from_team' }, 'syncing')

    await execute()

    expect(mockToast.success).toHaveBeenCalledWith('Synced from team — latest snapshot restored')
  })

  it('submit calls submit_for_review with dev_branch and pr_title', async () => {
    mockSyncSkill.mockResolvedValue({ status: 'ok', message: 'opened', pr_url: 'https://gitea.local/pr/1' })
    const request: SyncSkillReq = {
      action: 'submit_for_review',
      dev_branch: 'feature/skill-1',
      pr_title: 'Review skill-1',
    }
    const { execute } = setupExecute(request, 'submitting')

    await execute()

    expect(mockSyncSkill).toHaveBeenCalledWith('skill-1', request)
    expect(mockToast.success).toHaveBeenCalledWith('PR opened: https://gitea.local/pr/1')
  })

  it('shows requires_review toast with pr_url', async () => {
    mockSyncSkill.mockResolvedValue({
      status: 'requires_review',
      message: 'main protected',
      pr_url: 'https://gitea.local/pr/2',
    })
    const { execute, statusCalls, scheduleReset } = setupExecute({ action: 'save_to_team' }, 'saving')

    await execute()

    expect(statusCalls).toEqual(['saving', 'requires_review'])
    expect(mockToast.success).toHaveBeenCalledWith(
      'Main branch protected. Opened PR for review: https://gitea.local/pr/2',
    )
    expect(scheduleReset).not.toHaveBeenCalled()
  })
  it('reads a typed backend refusal in the reader language, not the server one', async () => {
    // The server states the fact (a code plus the field it is about); which
    // language that becomes belongs to whoever is reading. Going through the one
    // exit is what makes that true here — a hand-rolled `error.message` on this
    // path showed the raw axios line instead (ledger K4a, overturned on the real
    // app 2026-08-21).
    const config: InternalAxiosRequestConfig = {
      baseURL: 'http://127.0.0.1:8787/api',
      url: '/skills/skill-1/sync',
      method: 'post',
      headers: new AxiosHeaders(),
    }
    const response: AxiosResponse = {
      config,
      data: {
        error_code: 'APP_SETTINGS_INCOMPLETE',
        http_status: 400,
        message: 'app settings incomplete: gitea_host is not set',
        details: { field: 'gitea_host' },
      },
      headers: {},
      status: 400,
      statusText: 'Bad Request',
    }
    mockSyncSkill.mockRejectedValue(
      new AxiosError('Request failed with status code 400', 'ERR_BAD_REQUEST', config, {}, response),
    )

    await i18n.changeLanguage('en')
    const english = setupExecute({ action: 'save_to_team' }, 'saving')
    await english.execute()
    expect(mockToast.error).toHaveBeenLastCalledWith(
      'Settings are incomplete: gitea_host is not set. Open Settings to set it.',
    )

    await i18n.changeLanguage('zh-CN')
    const chinese = setupExecute({ action: 'save_to_team' }, 'saving')
    await chinese.execute()
    expect(mockToast.error).toHaveBeenLastCalledWith('设置没填完:gitea_host 还没配。到 Settings 里填上。')
  })

  it('still says what it was doing when the rejection carries nothing readable', async () => {
    mockSyncSkill.mockRejectedValue({ unexpected: true })
    const { execute, setError } = setupExecute({ action: 'save_to_team' }, 'saving')

    await execute()

    expect(setError).toHaveBeenCalledWith('Sync failed')
    expect(mockToast.error).toHaveBeenCalledWith('Sync failed')
  })
})
