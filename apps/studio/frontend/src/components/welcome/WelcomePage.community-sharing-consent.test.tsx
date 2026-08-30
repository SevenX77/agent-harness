// @vitest-environment jsdom
/**
 * WelcomePage is Studio's actual first screen (shown before any skill is
 * selected — see App.tsx's `currentSkillId` starting at null), so it is where
 * the first-run community-sharing consent dialog (design:
 * docs/studio/mvp1/01_workflows/00_settings.md §3.0) has to fire. This file
 * locks the GATING logic specifically: open exactly once while
 * `community_sharing_choice === "unset"` and settings have finished loading;
 * stay closed once answered ("shared" or "declined"); and each button drives
 * the correct setter.
 */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { toast } from 'sonner'
import { WelcomePage } from './WelcomePage'
import type { AppSettings } from '../../api/types'

const appSettingsMocks = vi.hoisted(() => ({
  isLoading: false,
  communitySharingChoice: 'unset' as AppSettings['community_sharing_choice'],
  setCommunitySharingChoice: vi.fn(),
  // J-01.J: the confirmation toast must be driven by the flushed save's real
  // outcome (settings snapshot = landed, null = failed), never by the click.
  save: vi.fn(async (): Promise<AppSettings | null> => null),
  // J-02.A: a failed settings read must be distinguishable from a real
  // "unset" snapshot — see the dedicated describe block below.
  error: null as unknown,
}))

vi.mock('../../hooks/useAppSettings', () => ({
  useAppSettings: () => ({
    settings: {
      user_id: '',
      gitea_host: '',
      default_skills_directory: '',
      language: 'en',
      community_sharing_choice: appSettingsMocks.communitySharingChoice,
      cli_sessions: { claude: { model: '', effort: '' }, codex: { model: '', effort: '' }, agents: {} },
    },
    isLoading: appSettingsMocks.isLoading,
    saveStatus: 'idle',
    setUserId: vi.fn(),
    setGiteaHost: vi.fn(),
    setDefaultSkillsDirectory: vi.fn(),
    setLanguage: vi.fn(),
    setCommunitySharingChoice: appSettingsMocks.setCommunitySharingChoice,
    setCliSessions: vi.fn(),
    save: appSettingsMocks.save,
    error: appSettingsMocks.error,
    lastSaveError: null,
  }),
}))

vi.mock('../../hooks/useRecentSkills', () => ({
  useRecentSkills: () => ({
    recentWorkspaces: [],
    rememberWorkspace: vi.fn(),
    removeWorkspace: vi.fn(),
    isHydrating: false,
    recentError: null,
  }),
}))

vi.mock('../../api/client', () => ({
  api: { delete: vi.fn(), post: vi.fn() },
  apiClientConfigChangedEvent: 'studio-api-client-config-changed',
  authenticatedApiReady: vi.fn(() => true),
  getAppSettings: vi.fn(),
  updateAppSettings: vi.fn(),
}))

vi.mock('sonner', () => ({
  toast: Object.assign(vi.fn(), { dismiss: vi.fn(), error: vi.fn(), success: vi.fn() }),
}))

vi.mock('../../config/runtime', () => ({
  getRuntimeConfig: vi.fn(() => null),
}))

vi.mock('../../lib/tauri', () => ({
  revealInFileManager: vi.fn(),
  selectSkillDirectory: vi.fn(),
  ensureWorkspaceSupportDirs: vi.fn(),
  createSkillWorkspace: vi.fn(),
  openSkillWorkspace: vi.fn(),
}))

describe('WelcomePage community-sharing consent gating', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    appSettingsMocks.isLoading = false
    appSettingsMocks.communitySharingChoice = 'unset'
    appSettingsMocks.error = null
    appSettingsMocks.setCommunitySharingChoice.mockReset()
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
    document.body.innerHTML = ''
  })

  function renderWelcome() {
    act(() => {
      root.render(<WelcomePage onSelectSkill={vi.fn()} />)
    })
  }

  function buttonNamed(pattern: RegExp): HTMLButtonElement | undefined {
    return [...document.querySelectorAll('button')].find((button) =>
      pattern.test(button.textContent ?? ''),
    ) as HTMLButtonElement | undefined
  }

  it('fires once when the choice is "unset" and settings have loaded', () => {
    renderWelcome()

    expect(document.body.textContent).toContain('Share provider parameters with the community?')
  })

  it('never fires while settings are still loading, even if the cached default reads "unset"', () => {
    appSettingsMocks.isLoading = true
    renderWelcome()

    expect(document.body.textContent).not.toContain('Share provider parameters with the community?')
  })

  /**
   * J-02.A: before the fix, a failed settings read committed
   * `withRuntimeDefaults(DEFAULT_APP_SETTINGS)` into the shared store with
   * `isLoading: false, error: null` — indistinguishable from a real "unset"
   * snapshot. For an install that had already answered ("shared" or
   * "declined") but hit a transient read failure (e.g. sidecar unreachable
   * at boot), this fired the dialog again; a "Not now" click there overwrites
   * the real choice with "declined" — silent data loss from a network blip.
   * The dialog must stay closed until a real server snapshot says "unset".
   */
  it('never fires when the settings read failed, even though the untrustworthy cached default reads "unset"', () => {
    appSettingsMocks.error = new Error('sidecar unreachable')
    renderWelcome()

    expect(document.body.textContent).not.toContain('Share provider parameters with the community?')
  })

  it('does not fire again once the user already answered "shared"', () => {
    appSettingsMocks.communitySharingChoice = 'shared'
    renderWelcome()

    expect(document.body.textContent).not.toContain('Share provider parameters with the community?')
  })

  it('does not fire again once the user already answered "declined"', () => {
    appSettingsMocks.communitySharingChoice = 'declined'
    renderWelcome()

    expect(document.body.textContent).not.toContain('Share provider parameters with the community?')
  })

  it('"Turn on sharing" records the choice as "shared"', () => {
    renderWelcome()

    act(() => {
      buttonNamed(/^Turn on sharing$/)?.click()
    })

    expect(appSettingsMocks.setCommunitySharingChoice).toHaveBeenCalledWith('shared')
  })

  it('"Not now" records the choice as "declined" — a valid, final answer', () => {
    renderWelcome()

    act(() => {
      buttonNamed(/^Not now$/)?.click()
    })

    expect(appSettingsMocks.setCommunitySharingChoice).toHaveBeenCalledWith('declined')
  })
})

/**
 * J-01.J: answering the consent dialog was the one durable choice in the app
 * with zero feedback — probe, compile and save all toast, this didn't. The
 * confirmation may only fire after the FLUSHED save lands (save() resolves a
 * settings snapshot); a failed save (null) already error-toasts inside
 * performSave and must not also claim success here.
 */
describe('WelcomePage community-sharing consent confirmation (J-01.J)', () => {
  let container: HTMLDivElement
  let root: Root

  const savedSnapshot = { community_sharing_choice: 'shared' } as AppSettings

  beforeEach(() => {
    appSettingsMocks.isLoading = false
    appSettingsMocks.communitySharingChoice = 'unset'
    appSettingsMocks.error = null
    appSettingsMocks.setCommunitySharingChoice.mockReset()
    appSettingsMocks.save.mockReset()
    appSettingsMocks.save.mockResolvedValue(savedSnapshot)
    vi.mocked(toast.success).mockReset()
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
    document.body.innerHTML = ''
  })

  function buttonNamed(pattern: RegExp): HTMLButtonElement | undefined {
    return [...document.querySelectorAll('button')].find((button) =>
      pattern.test(button.textContent ?? ''),
    ) as HTMLButtonElement | undefined
  }

  async function renderAndAnswer(pattern: RegExp) {
    act(() => {
      root.render(<WelcomePage onSelectSkill={vi.fn()} />)
    })
    await act(async () => {
      buttonNamed(pattern)?.click()
    })
  }

  it('"Turn on sharing" flushes the save and confirms with a toast', async () => {
    await renderAndAnswer(/^Turn on sharing$/)

    expect(appSettingsMocks.save).toHaveBeenCalledTimes(1)
    expect(toast.success).toHaveBeenCalledWith('Community sharing is on')
  })

  it('"Not now" flushes the save and confirms with its own toast', async () => {
    await renderAndAnswer(/^Not now$/)

    expect(appSettingsMocks.save).toHaveBeenCalledTimes(1)
    expect(toast.success).toHaveBeenCalledWith(
      'Sharing stays off — you can turn it on anytime in Settings → General',
    )
  })

  it('a failed save (null) never claims success', async () => {
    appSettingsMocks.save.mockResolvedValue(null)

    await renderAndAnswer(/^Turn on sharing$/)

    expect(toast.success).not.toHaveBeenCalled()
  })
})
