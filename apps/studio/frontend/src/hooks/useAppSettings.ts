import { useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { toast } from 'sonner'
import i18n from '../i18n'
import { apiClientConfigChangedEvent, authenticatedApiReady, getAppSettings, updateAppSettings } from '../api/client'
import type { AppLanguage, AppSettings, CliSessionSettings, CommunitySharingChoice } from '../api/types'
import type { SaveStatus } from './useDebouncedCredentialsSave'
import { runtimeDefaultSkillsDirectory } from '../utils/skill-paths'
import { errorMessage } from '../utils/errors'

/**
 * N0 i18n (#15.1): the persisted `app_settings.language` is the durable source
 * of truth for the UI language. When settings hydrate, reconcile the live
 * react-i18next language to the stored value so the backend choice wins over the
 * detector's localStorage cache (e.g. a value synced from another device).
 * Called once per store commit — not once per mounted hook instance — so a
 * multi-subscriber broadcast cannot fan out into duplicate changeLanguage
 * calls (belt and braces: the equality early-return below guards even that).
 */
function syncI18nLanguage(language: AppLanguage): void {
  if (i18n.language === language) return
  i18n.changeLanguage(language).catch((error) => {
    console.warn('phase=app-settings action=i18n-language-sync-failed language=%s error=%o', language, error)
  })
}

export const DEFAULT_CLI_SESSIONS: CliSessionSettings = {
  claude: { model: '', effort: '' },
  codex: { model: '', effort: '' },
  agents: {},
}

export const DEFAULT_APP_SETTINGS: AppSettings = {
  user_id: '',
  gitea_host: '',
  default_skills_directory: '',
  language: 'en',
  community_sharing_choice: 'unset',
  cli_sessions: DEFAULT_CLI_SESSIONS,
}

const APP_SETTINGS_SAVE_DELAY_MS = 300

function withRuntimeDefaults(settings: AppSettings): AppSettings {
  if (settings.default_skills_directory.trim()) {
    return settings
  }
  const defaultSkillsDirectory = runtimeDefaultSkillsDirectory()
  return defaultSkillsDirectory
    ? { ...settings, default_skills_directory: defaultSkillsDirectory }
    : settings
}

export function appSettingsEqual(left: AppSettings, right: AppSettings) {
  return left.user_id === right.user_id
    && left.gitea_host === right.gitea_host
    && left.default_skills_directory === right.default_skills_directory
    && left.language === right.language
    && left.community_sharing_choice === right.community_sharing_choice
    && JSON.stringify(left.cli_sessions) === JSON.stringify(right.cli_sessions)
}

/**
 * J-01.H (2026-08-24): app settings are ONE dataset with ONE authoritative
 * frontend replica. The previous design gave every `useAppSettings()` instance
 * a private useState copy of the module cache; instances were never notified of
 * each other's writes, so the forceMount-resident Settings dialog kept its boot
 * snapshot after the WelcomePage consent dialog saved — the UI lied, and the
 * resident instance's next whole-object autosave wrote the stale snapshot back
 * over the user's consent. That violates the AGENTS.md SSOT read rule: "a
 * successful write returning the canonical server snapshot" is a truth-change
 * trigger and "all consumers must share that in-flight request/result".
 *
 * The fix is a module-level reactive store shared by every hook instance.
 * Borrowed / rejected (per the "先看成熟工程怎么解" rule):
 * - BORROWED the React-docs `useSyncExternalStore` external-store shape — one
 *   module-level snapshot + a subscriber set; the hook is a pure projection and
 *   every mutation notifies all subscribers.
 * - BORROWED the shared-cache shape of SWR / TanStack Query: a single cache
 *   entry per dataset, one deduped in-flight request, and write-through updates
 *   broadcast to every consumer.
 * - REJECTED adding SWR/TanStack Query as a dependency: this is one endpoint
 *   with one cache key — a query library's key/GC/retry machinery buys nothing
 *   here (KISS/YAGNI), and the autosave supersede semantics below are custom
 *   either way.
 *
 * The autosave queue is module-level too (explicit single owner): the debounce
 * timer, in-flight promise, pending payload and save status belong to the
 * dataset, not to whichever component happened to render first. A queued save
 * therefore survives an instance unmounting (the old per-instance cleanup
 * silently dropped it — an edit made just before closing a surface was lost).
 */
interface AppSettingsStoreState {
  settings: AppSettings
  isLoading: boolean
  error: unknown
  saveStatus: SaveStatus
  lastSaveError: unknown
}

// Lazily initialized: `withRuntimeDefaults` reads the Tauri runtime config,
// which is applied during app bootstrap — at module-import time it may not be
// there yet, but by the first hook render (same moment the old per-instance
// useState initializer ran) it is.
let storeState: AppSettingsStoreState | null = null
const storeListeners = new Set<() => void>()

function initialStoreState(): AppSettingsStoreState {
  return {
    settings: withRuntimeDefaults(DEFAULT_APP_SETTINGS),
    isLoading: true,
    error: null,
    saveStatus: 'idle',
    lastSaveError: null,
  }
}

function getStoreState(): AppSettingsStoreState {
  if (!storeState) {
    storeState = initialStoreState()
  }
  return storeState
}

function commitStoreState(patch: Partial<AppSettingsStoreState>): void {
  storeState = { ...getStoreState(), ...patch }
  for (const listener of [...storeListeners]) {
    listener()
  }
}

function subscribeToStore(listener: () => void): () => void {
  storeListeners.add(listener)
  return () => {
    storeListeners.delete(listener)
  }
}

let appSettingsCache: AppSettings | null = null
let appSettingsRequest: Promise<AppSettings> | null = null
let appSettingsRequestForced = false

let saveTimer: ReturnType<typeof setTimeout> | null = null
let inflightSave: Promise<AppSettings | null> | null = null
let pendingPayload: AppSettings | null = null

function saveQueueBusy(): boolean {
  return saveTimer !== null || inflightSave !== null || pendingPayload !== null
}

export function resetAppSettingsCacheForTests(): void {
  appSettingsCache = null
  appSettingsRequest = null
  appSettingsRequestForced = false
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = null
  inflightSave = null
  pendingPayload = null
  storeState = null
}

export async function loadAppSettings(options: { force?: boolean } = {}): Promise<AppSettings> {
  if (!options.force && appSettingsCache) return appSettingsCache
  // A forced load joins an in-flight FORCED request (e.g. every mounted
  // instance reacting to the same sidecar-restart event shares one GET, per
  // the SSOT shared-in-flight rule) but must not be satisfied by an in-flight
  // ordinary read, whose response may predate the restart.
  if (appSettingsRequest && (!options.force || appSettingsRequestForced)) return appSettingsRequest

  const request = getAppSettings()
    .then((settings) => {
      const nextSettings = withRuntimeDefaults(settings)
      appSettingsCache = nextSettings
      return nextSettings
    })
    .catch((error) => {
      console.warn('Failed to load settings', error)
      return withRuntimeDefaults(DEFAULT_APP_SETTINGS)
    })
    .finally(() => {
      if (appSettingsRequest === request) {
        appSettingsRequest = null
      }
    })

  appSettingsRequest = request
  appSettingsRequestForced = options.force === true
  return request
}

/**
 * Commit a freshly loaded server snapshot into the shared store — unless local
 * edits are queued or in flight: a read result must never clobber a newer
 * draft (the save pipeline refreshes the snapshot from its own canonical
 * response instead).
 */
async function loadIntoStore(options: { force?: boolean } = {}): Promise<void> {
  commitStoreState({ isLoading: true })
  const nextSettings = await loadAppSettings(options)
  if (saveQueueBusy()) {
    commitStoreState({ isLoading: false })
    return
  }
  commitStoreState({ settings: nextSettings, isLoading: false, error: null })
  syncI18nLanguage(nextSettings.language)
}

export async function saveAppSettings(settings: AppSettings): Promise<AppSettings> {
  try {
    const saved = withRuntimeDefaults(await updateAppSettings(settings))
    appSettingsCache = saved
    if (!saveQueueBusy()) {
      commitStoreState({ settings: saved })
    }
    toast.success('Settings saved')
    return saved
  } catch (error) {
    toast.error('Failed to save settings')
    throw error
  }
}

async function performSave(nextSettings: AppSettings): Promise<AppSettings | null> {
  commitStoreState({ saveStatus: 'saving' })
  try {
    const saved = withRuntimeDefaults(await updateAppSettings(nextSettings))
    if (!pendingPayload) {
      commitStoreState({ saveStatus: 'saved', lastSaveError: null })
    }
    // Supersede rule (repo-wide autosave semantics): when a newer payload is
    // buffered, or the shared draft moved past what this request saved, the
    // stale server snapshot must not overwrite the latest local draft — and
    // the stale cache write is skipped for the same reason (the follow-up
    // save's canonical response refreshes both).
    if (!pendingPayload && appSettingsEqual(getStoreState().settings, nextSettings)) {
      appSettingsCache = saved
      commitStoreState({ settings: saved })
    }
    return saved
  } catch (saveError) {
    if (!pendingPayload) {
      commitStoreState({ saveStatus: 'error', lastSaveError: saveError })
      const message = errorMessage(saveError, 'Save failed')
      toast.error(`Settings save failed: ${message}`)
    }
    return null
  } finally {
    inflightSave = null
    const buffered = pendingPayload
    if (buffered) {
      pendingPayload = null
      inflightSave = performSave(buffered)
    }
  }
}

function queueSave(nextSettings: AppSettings): void {
  if (saveTimer) clearTimeout(saveTimer)
  commitStoreState({ saveStatus: 'pending' })
  if (inflightSave) {
    pendingPayload = nextSettings
    saveTimer = null
    return
  }
  saveTimer = setTimeout(() => {
    saveTimer = null
    if (inflightSave) {
      pendingPayload = nextSettings
      return
    }
    inflightSave = performSave(nextSettings)
  }, APP_SETTINGS_SAVE_DELAY_MS)
}

function updateSettings(patch: Partial<AppSettings>): void {
  const next = withRuntimeDefaults({ ...getStoreState().settings, ...patch })
  commitStoreState({ settings: next })
  queueSave(next)
}

function setUserId(userId: string): void {
  updateSettings({ user_id: userId })
}

function setGiteaHost(giteaHost: string): void {
  updateSettings({ gitea_host: giteaHost })
}

function setDefaultSkillsDirectory(defaultSkillsDirectory: string): void {
  updateSettings({ default_skills_directory: defaultSkillsDirectory })
}

function setLanguage(language: AppLanguage): void {
  updateSettings({ language })
}

function setCommunitySharingChoice(communitySharingChoice: CommunitySharingChoice): void {
  updateSettings({ community_sharing_choice: communitySharingChoice })
}

function setCliSessions(cliSessions: CliSessionSettings): void {
  updateSettings({ cli_sessions: cliSessions })
}

async function save(): Promise<AppSettings> {
  if (saveTimer) {
    clearTimeout(saveTimer)
    saveTimer = null
  }
  const saved = await performSave(getStoreState().settings)
  return saved ?? getStoreState().settings
}

/**
 * recovery-stops-when-it-succeeds (2026-08-24), fix point 4 — alongside the
 * ready boolean, also returns a `reloadNonce` that increments on EVERY
 * `apiClientConfigChangedEvent`, not just the ones that flip the boolean.
 *
 * A sidecar restart calls `configureApiBaseURL`/`configureApiToken` with a
 * NEW base URL/token (`config/runtime.ts::applySidecarConfig`), which fires
 * this same event — but `authenticatedApiReady()` was already true before the
 * restart and stays true after it (both values are replaced, never cleared
 * in between), so the boolean alone never signals that anything happened. The
 * nonce is the reload trigger `useAppSettings` needs to force a fresh fetch
 * on a restart while still loading from cache on ordinary re-renders.
 */
function useAuthenticatedSettingsApiReady(): { ready: boolean; reloadNonce: number } {
  const [ready, setReady] = useState(() => authenticatedApiReady())
  const [reloadNonce, setReloadNonce] = useState(0)

  useEffect(() => {
    if (typeof window === 'undefined') return undefined
    // Catch up once, synchronously, in case authenticatedApiReady() changed
    // between the initializer above and this effect mounting. This catch-up
    // is not itself a "something changed AFTER we started observing" signal
    // — it must not bump reloadNonce, or every single mount would force one
    // redundant reload of data that is already fresh.
    setReady(authenticatedApiReady())
    const handleConfigChange = () => {
      setReady(authenticatedApiReady())
      setReloadNonce((current) => current + 1)
    }
    window.addEventListener(apiClientConfigChangedEvent, handleConfigChange)
    return () => {
      window.removeEventListener(apiClientConfigChangedEvent, handleConfigChange)
    }
  }, [])

  return { ready, reloadNonce }
}

export function useAppSettings() {
  const { ready: apiReady, reloadNonce } = useAuthenticatedSettingsApiReady()
  // The third argument (server snapshot) serves renderToString-based tests;
  // it reads the same module store, so both render modes see one truth.
  const state = useSyncExternalStore(subscribeToStore, getStoreState, getStoreState)
  // recovery-stops-when-it-succeeds, fix point 4: false until this instance's
  // FIRST load completes. Only loads triggered by a LATER `reloadNonce` bump —
  // i.e. a real `apiClientConfigChangedEvent` after this hook already has data
  // — force-bypass the module cache. The initial load stays cache-aware (so a
  // second `useAppSettings()` consumer mounting around the same time still
  // shares the one in-flight request, per the SSOT read-through rule).
  const hasLoadedOnceRef = useRef(false)

  useEffect(() => {
    if (!apiReady) {
      commitStoreState({ isLoading: true })
      return
    }
    void loadIntoStore({ force: hasLoadedOnceRef.current }).then(() => {
      hasLoadedOnceRef.current = true
    })
  }, [apiReady, reloadNonce])

  return {
    settings: state.settings,
    setUserId,
    setGiteaHost,
    setDefaultSkillsDirectory,
    setLanguage,
    setCommunitySharingChoice,
    setCliSessions,
    save,
    isLoading: state.isLoading,
    error: state.error,
    saveStatus: state.saveStatus,
    lastSaveError: state.lastSaveError,
  }
}
