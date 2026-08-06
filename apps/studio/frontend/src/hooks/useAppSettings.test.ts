// @vitest-environment jsdom
import { act, createElement, useEffect, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { AppSettings } from '../api/types'
import { appSettingsEqual, DEFAULT_APP_SETTINGS, loadAppSettings, resetAppSettingsCacheForTests, saveAppSettings, useAppSettings } from './useAppSettings'
import { getAppSettings, updateAppSettings } from '../api/client'
import { toast } from 'sonner'

const apiClientMocks = vi.hoisted(() => ({
  apiReady: true,
  configChangedEvent: 'studio-api-client-config-changed',
  getAppSettings: vi.fn(),
  updateAppSettings: vi.fn(),
}))

vi.mock('../api/client', () => ({
  apiClientConfigChangedEvent: apiClientMocks.configChangedEvent,
  authenticatedApiReady: () => apiClientMocks.apiReady,
  getAppSettings: apiClientMocks.getAppSettings,
  updateAppSettings: apiClientMocks.updateAppSettings,
}))

vi.mock('sonner', () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn(),
  },
}))

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const serverSettings: AppSettings = {
  user_id: 'alice',
  gitea_host: 'https://gitea.example.com',
  default_skills_directory: '/Users/alice/AgentStudio/Skills',
  language: 'zh-CN',
  remote_model_catalog_enabled: true,
  cli_sessions: { claude: { model: '', effort: '' }, codex: { model: '', effort: '' }, agents: {} },
}

function renderJsx(node: ReactNode): { container: HTMLDivElement; root: Root } {
  const container = document.createElement('div')
  document.body.appendChild(container)
  const root = createRoot(container)
  act(() => {
    root.render(node)
  })
  return { container, root }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

afterEach(() => {
  vi.useRealTimers()
  document.body.innerHTML = ''
})

describe('useAppSettings helpers', () => {
  beforeEach(() => {
    apiClientMocks.apiReady = true
    vi.mocked(getAppSettings).mockReset()
    vi.mocked(updateAppSettings).mockReset()
    vi.mocked(toast.error).mockReset()
    vi.mocked(toast.success).mockReset()
    resetAppSettingsCacheForTests()
  })

  it('loads app settings from the backend', async () => {
    vi.mocked(getAppSettings).mockResolvedValue(serverSettings)

    await expect(loadAppSettings()).resolves.toEqual(serverSettings)

    expect(getAppSettings).toHaveBeenCalledOnce()
  })

  it('dedupes concurrent app settings loads', async () => {
    vi.mocked(getAppSettings).mockResolvedValue(serverSettings)

    await expect(Promise.all([loadAppSettings(), loadAppSettings()])).resolves.toEqual([
      serverSettings,
      serverSettings,
    ])

    expect(getAppSettings).toHaveBeenCalledOnce()
  })

  it('reuses the cached app settings after a successful load', async () => {
    vi.mocked(getAppSettings).mockResolvedValue(serverSettings)

    await loadAppSettings()
    await loadAppSettings()

    expect(getAppSettings).toHaveBeenCalledOnce()
  })

  it('does not cache the default fallback after a failed load', async () => {
    vi.mocked(getAppSettings)
      .mockRejectedValueOnce(new Error('401'))
      .mockResolvedValueOnce(serverSettings)

    await expect(loadAppSettings()).resolves.toEqual(DEFAULT_APP_SETTINGS)
    await expect(loadAppSettings()).resolves.toEqual(serverSettings)

    expect(getAppSettings).toHaveBeenCalledTimes(2)
  })

  it('saves edited user id and gitea host', async () => {
    const draft: AppSettings = {
      user_id: 'bob',
      gitea_host: 'https://git.internal.example',
      default_skills_directory: '/Users/bob/Skills',
      language: 'en',
      remote_model_catalog_enabled: false,
      cli_sessions: { claude: { model: '', effort: '' }, codex: { model: '', effort: '' }, agents: {} },
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
      default_skills_directory: '/Users/bob/Skills',
      language: 'en',
      remote_model_catalog_enabled: true,
      cli_sessions: { claude: { model: '', effort: '' }, codex: { model: '', effort: '' }, agents: {} },
    }
    vi.mocked(updateAppSettings).mockRejectedValue(new Error('write failed'))

    await expect(saveAppSettings(draft)).rejects.toThrow('write failed')

    expect(toast.error).toHaveBeenCalledWith('Failed to save settings')
  })

  it('round-trips the selected UI language through the settings store', async () => {
    const draft: AppSettings = {
      user_id: 'bob',
      gitea_host: '',
      default_skills_directory: '/Users/bob/Skills',
      language: 'zh-CN',
      remote_model_catalog_enabled: true,
      cli_sessions: { claude: { model: '', effort: '' }, codex: { model: '', effort: '' }, agents: {} },
    }
    vi.mocked(updateAppSettings).mockResolvedValue(draft)

    const saved = await saveAppSettings(draft)

    expect(updateAppSettings).toHaveBeenCalledWith(draft)
    expect(saved.language).toBe('zh-CN')
  })
})

describe('useAppSettings language field', () => {
  it('defaults the UI language to English', () => {
    expect(DEFAULT_APP_SETTINGS.language).toBe('en')
  })

  it('treats a language change as a settings change (drives a save)', () => {
    const base: AppSettings = {
      user_id: 'alice',
      gitea_host: '',
      default_skills_directory: '/Skills',
      language: 'en',
      remote_model_catalog_enabled: true,
      cli_sessions: { claude: { model: '', effort: '' }, codex: { model: '', effort: '' }, agents: {} },
    }
    const switched: AppSettings = { ...base, language: 'zh-CN' }

    expect(appSettingsEqual(base, base)).toBe(true)
    expect(appSettingsEqual(base, switched)).toBe(false)
  })
})

describe('useAppSettings API readiness', () => {
  beforeEach(() => {
    apiClientMocks.apiReady = true
    vi.mocked(getAppSettings).mockReset()
    vi.mocked(updateAppSettings).mockReset()
    resetAppSettingsCacheForTests()
  })

  it('waits for authenticated API readiness before loading settings', async () => {
    apiClientMocks.apiReady = false
    vi.mocked(getAppSettings).mockResolvedValue(serverSettings)
    const captured = { current: null as ReturnType<typeof useAppSettings> | null }

    function Harness() {
      const result = useAppSettings()
      useEffect(() => {
        captured.current = result
      })
      return null
    }

    const { root } = renderJsx(createElement(Harness))
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(getAppSettings).not.toHaveBeenCalled()
    expect(captured.current?.isLoading).toBe(true)

    apiClientMocks.apiReady = true
    act(() => {
      window.dispatchEvent(new Event(apiClientMocks.configChangedEvent))
    })
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(getAppSettings).toHaveBeenCalledOnce()
    expect(captured.current?.settings).toEqual(serverSettings)

    act(() => root.unmount())
  })
})

describe('useAppSettings remote model catalog flag', () => {
  it('defaults automatic remote model catalog reads to enabled', () => {
    expect(DEFAULT_APP_SETTINGS.remote_model_catalog_enabled).toBe(true)
  })

  it('treats the remote catalog toggle as a settings change (drives a save)', () => {
    const base: AppSettings = {
      user_id: 'alice',
      gitea_host: '',
      default_skills_directory: '/Skills',
      language: 'en',
      remote_model_catalog_enabled: true,
      cli_sessions: { claude: { model: '', effort: '' }, codex: { model: '', effort: '' }, agents: {} },
    }
    const disabled: AppSettings = { ...base, remote_model_catalog_enabled: false }

    expect(appSettingsEqual(base, base)).toBe(true)
    expect(appSettingsEqual(base, disabled)).toBe(false)
  })
})

describe('useAppSettings autosave queue', () => {
  beforeEach(() => {
    apiClientMocks.apiReady = true
    vi.mocked(getAppSettings).mockReset()
    vi.mocked(updateAppSettings).mockReset()
    vi.mocked(toast.error).mockReset()
    vi.mocked(toast.success).mockReset()
  })

  it('keeps only the newest queued app settings payload while an older save is in flight', async () => {
    vi.useFakeTimers()
    vi.mocked(getAppSettings).mockResolvedValue(serverSettings)
    const first = deferred<AppSettings>()
    const second = deferred<AppSettings>()
    vi.mocked(updateAppSettings)
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise)
    let hook: ReturnType<typeof useAppSettings> | null = null
    const renderedUserIds: string[] = []

    function Harness() {
      const result = useAppSettings()
      renderedUserIds.push(result.settings.user_id)
      useEffect(() => {
        hook = result
      })
      return null
    }

    const { root } = renderJsx(createElement(Harness))
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
      await Promise.resolve()
    })

    act(() => {
      hook?.setUserId('first')
    })
    act(() => {
      vi.advanceTimersByTime(300)
    })
    expect(updateAppSettings).toHaveBeenCalledTimes(1)
    expect(vi.mocked(updateAppSettings).mock.calls[0]?.[0].user_id).toBe('first')

    act(() => {
      hook?.setUserId('stale-second')
      hook?.setUserId('latest-second')
    })
    expect(updateAppSettings).toHaveBeenCalledTimes(1)

    await act(async () => {
      first.resolve({ ...serverSettings, user_id: 'first' })
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(updateAppSettings).toHaveBeenCalledTimes(2)
    expect(vi.mocked(updateAppSettings).mock.calls[1]?.[0].user_id).toBe('latest-second')

    await act(async () => {
      second.resolve({ ...serverSettings, user_id: 'latest-second' })
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(renderedUserIds.at(-1)).toBe('latest-second')

    act(() => root.unmount())
  })
})
