import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { AppSettings } from '../api/types'
import { loadAppSettings, saveAppSettings } from './useAppSettings'
import { getAppSettings, updateAppSettings } from '../api/client'
import { toast } from 'sonner'

vi.mock('../api/client', () => ({
  getAppSettings: vi.fn(),
  updateAppSettings: vi.fn(),
}))

vi.mock('sonner', () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn(),
  },
}))

const serverSettings: AppSettings = {
  user_id: 'alice',
  gitea_host: 'https://gitea.example.com',
}

describe('useAppSettings helpers', () => {
  beforeEach(() => {
    vi.mocked(getAppSettings).mockReset()
    vi.mocked(updateAppSettings).mockReset()
    vi.mocked(toast.error).mockReset()
    vi.mocked(toast.success).mockReset()
  })

  it('loads app settings from the backend', async () => {
    vi.mocked(getAppSettings).mockResolvedValue(serverSettings)

    await expect(loadAppSettings()).resolves.toEqual(serverSettings)

    expect(getAppSettings).toHaveBeenCalledOnce()
  })

  it('saves edited user id and gitea host', async () => {
    const draft: AppSettings = {
      user_id: 'bob',
      gitea_host: 'https://git.internal.example',
    }
    vi.mocked(updateAppSettings).mockResolvedValue(draft)

    await expect(saveAppSettings(draft)).resolves.toEqual(draft)

    expect(updateAppSettings).toHaveBeenCalledWith(draft)
    expect(toast.success).toHaveBeenCalledWith('Settings saved')
  })

  it('shows a toast when saving app settings fails', async () => {
    const draft: AppSettings = {
      user_id: 'bob',
      gitea_host: 'https://git.internal.example',
    }
    vi.mocked(updateAppSettings).mockRejectedValue(new Error('write failed'))

    await expect(saveAppSettings(draft)).rejects.toThrow('write failed')

    expect(toast.error).toHaveBeenCalledWith('Failed to save settings')
  })
})
