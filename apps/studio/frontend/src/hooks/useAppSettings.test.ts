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
  community_sharing_choice: 'shared',
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
      community_sharing_choice: 'declined',
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
      community_sharing_choice: 'shared',
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
      community_sharing_choice: 'shared',
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
      community_sharing_choice: 'shared',
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

  /**
   * recovery-stops-when-it-succeeds (2026-08-24), fix point 4: a sidecar
   * restart is a legitimate SSOT truth-change trigger (AGENTS.md — a backend
   * process reset is exactly a "backend post-commit domain event," not a
   * mount/focus/poll). `apiClientConfigChangedEvent` already fires on a
   * restart (`config/runtime.ts::applySidecarConfig` calls
   * `configureApiBaseURL`/`configureApiToken`), but this hook used to only
   * recompute the BOOLEAN `authenticatedApiReady()` from it — and a restart
   * typically swaps the token/base URL WITHOUT ever making that boolean go
   * false in between, so the `[apiReady]`-keyed load effect never saw
   * anything change and settings stayed frozen on the pre-restart snapshot.
   */
  it('reloads settings from the backend after a sidecar restart, even though authenticatedApiReady stays true throughout', async () => {
    vi.mocked(getAppSettings)
      .mockResolvedValueOnce(serverSettings)
      .mockResolvedValueOnce({ ...serverSettings, user_id: 'restarted-sidecar-user' })
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

    expect(getAppSettings).toHaveBeenCalledTimes(1)
    expect(captured.current?.settings.user_id).toBe(serverSettings.user_id)

    // `authenticatedApiReady()` stays true before AND after — the event
    // itself is the only observable signal a restart happened.
    apiClientMocks.apiReady = true
    act(() => {
      window.dispatchEvent(new Event(apiClientMocks.configChangedEvent))
    })
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(getAppSettings).toHaveBeenCalledTimes(2)
    expect(captured.current?.settings.user_id).toBe('restarted-sidecar-user')

    act(() => root.unmount())
  })
})

describe('useAppSettings community sharing choice', () => {
  it('defaults to "unset" — the first-run consent dialog has not fired yet', () => {
    expect(DEFAULT_APP_SETTINGS.community_sharing_choice).toBe('unset')
  })

  it('treats the community sharing choice as a settings change (drives a save)', () => {
    const base: AppSettings = {
      user_id: 'alice',
      gitea_host: '',
      default_skills_directory: '/Skills',
      language: 'en',
      community_sharing_choice: 'shared',
      cli_sessions: { claude: { model: '', effort: '' }, codex: { model: '', effort: '' }, agents: {} },
    }
    const declined: AppSettings = { ...base, community_sharing_choice: 'declined' }

    expect(appSettingsEqual(base, base)).toBe(true)
    expect(appSettingsEqual(base, declined)).toBe(false)
  })
})

/**
 * J-01.H (real-machine repro, 2026-08-24): the resident Settings dialog is
 * forceMount-ed at boot, so its `useAppSettings()` instance exists BEFORE the
 * WelcomePage consent dialog saves `community_sharing_choice`. With
 * per-instance private state, the resident instance kept its boot snapshot —
 * the UI lied ("off" while the server said "shared") — and its next whole-object
 * autosave silently wrote the stale choice back over the user's consent. All
 * mounted instances must project the ONE shared snapshot (AGENTS.md SSOT: "a
 * successful write returning the canonical server snapshot" is a truth-change
 * trigger, and all consumers must share it).
 */
describe('useAppSettings shares one truth across hook instances (J-01.H)', () => {
  beforeEach(() => {
    apiClientMocks.apiReady = true
    vi.mocked(getAppSettings).mockReset()
    vi.mocked(updateAppSettings).mockReset()
    vi.mocked(toast.error).mockReset()
    vi.mocked(toast.success).mockReset()
    resetAppSettingsCacheForTests()
  })

  function makeHarness(capture: { current: ReturnType<typeof useAppSettings> | null }) {
    return function Harness() {
      const result = useAppSettings()
      useEffect(() => {
        capture.current = result
      })
      return null
    }
  }

  it('projects a change made through one instance into every other mounted instance immediately', async () => {
    vi.useFakeTimers()
    vi.mocked(getAppSettings).mockResolvedValue({ ...serverSettings, community_sharing_choice: 'unset' })
    vi.mocked(updateAppSettings).mockImplementation((next: AppSettings) => Promise.resolve(next))
    // Mount order mirrors the real app: the resident Settings dialog instance
    // exists first, the WelcomePage consent instance second.
    const residentDialog = { current: null as ReturnType<typeof useAppSettings> | null }
    const welcomeConsent = { current: null as ReturnType<typeof useAppSettings> | null }
    const ResidentHarness = makeHarness(residentDialog)
    const WelcomeHarness = makeHarness(welcomeConsent)

    const { root } = renderJsx(createElement(
      'div',
      null,
      createElement(ResidentHarness),
      createElement(WelcomeHarness),
    ))
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
      await Promise.resolve()
    })
    expect(residentDialog.current?.settings.community_sharing_choice).toBe('unset')
    expect(welcomeConsent.current?.settings.community_sharing_choice).toBe('unset')

    act(() => {
      welcomeConsent.current?.setCommunitySharingChoice('shared')
    })

    // The resident instance must see the new value from the shared snapshot at
    // once — before the debounced PUT even fires, and without any refetch.
    expect(getAppSettings).toHaveBeenCalledOnce()
    expect(residentDialog.current?.settings.community_sharing_choice).toBe('shared')

    await act(async () => {
      vi.advanceTimersByTime(300)
      await Promise.resolve()
      await Promise.resolve()
    })
    expect(vi.mocked(updateAppSettings).mock.calls.at(-1)?.[0].community_sharing_choice).toBe('shared')
    expect(residentDialog.current?.settings.community_sharing_choice).toBe('shared')

    act(() => root.unmount())
  })

  it('never lets an earlier-mounted instance autosave a stale snapshot over another instance\'s saved choice', async () => {
    vi.useFakeTimers()
    vi.mocked(getAppSettings).mockResolvedValue({ ...serverSettings, community_sharing_choice: 'unset' })
    vi.mocked(updateAppSettings).mockImplementation((next: AppSettings) => Promise.resolve(next))
    const residentDialog = { current: null as ReturnType<typeof useAppSettings> | null }
    const welcomeConsent = { current: null as ReturnType<typeof useAppSettings> | null }
    const ResidentHarness = makeHarness(residentDialog)
    const WelcomeHarness = makeHarness(welcomeConsent)

    const { root } = renderJsx(createElement(
      'div',
      null,
      createElement(ResidentHarness),
      createElement(WelcomeHarness),
    ))
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
      await Promise.resolve()
    })

    // Step 1 of the repro: the consent dialog records the user's consent.
    act(() => {
      welcomeConsent.current?.setCommunitySharingChoice('shared')
    })
    await act(async () => {
      vi.advanceTimersByTime(300)
      await Promise.resolve()
      await Promise.resolve()
    })
    expect(vi.mocked(updateAppSettings).mock.calls.at(-1)?.[0].community_sharing_choice).toBe('shared')

    // Step 2: the user edits an unrelated field through the resident Settings
    // instance. Its whole-object autosave must carry the consent, not eat it.
    act(() => {
      residentDialog.current?.setUserId('renamed-user')
    })
    await act(async () => {
      vi.advanceTimersByTime(300)
      await Promise.resolve()
      await Promise.resolve()
    })

    const lastPayload = vi.mocked(updateAppSettings).mock.calls.at(-1)?.[0]
    expect(lastPayload?.user_id).toBe('renamed-user')
    expect(lastPayload?.community_sharing_choice).toBe('shared')

    act(() => root.unmount())
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
