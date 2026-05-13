import { beforeEach, describe, expect, it, vi } from 'vitest'
import { toast } from 'sonner'
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
})
