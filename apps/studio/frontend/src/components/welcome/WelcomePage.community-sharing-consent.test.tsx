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
import { WelcomePage } from './WelcomePage'
import type { AppSettings } from '../../api/types'

const appSettingsMocks = vi.hoisted(() => ({
  isLoading: false,
  communitySharingChoice: 'unset' as AppSettings['community_sharing_choice'],
  setCommunitySharingChoice: vi.fn(),
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
    save: vi.fn(),
    error: null,
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
