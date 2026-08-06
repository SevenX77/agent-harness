import { useCallback, useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import i18n from '../i18n'
import { apiClientConfigChangedEvent, authenticatedApiReady, getAppSettings, updateAppSettings } from '../api/client'
import type { AppLanguage, AppSettings, CliSessionSettings } from '../api/types'
import type { SaveStatus } from './useDebouncedCredentialsSave'
import { runtimeDefaultSkillsDirectory } from '../utils/skill-paths'

/**
 * N0 i18n (#15.1): the persisted `app_settings.language` is the durable source
 * of truth for the UI language. When settings hydrate, reconcile the live
 * react-i18next language to the stored value so the backend choice wins over the
 * detector's localStorage cache (e.g. a value synced from another device).
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
  remote_model_catalog_enabled: true,
  cli_sessions: DEFAULT_CLI_SESSIONS,
}

const APP_SETTINGS_SAVE_DELAY_MS = 300

let appSettingsCache: AppSettings | null = null
let appSettingsRequest: Promise<AppSettings> | null = null

function useAuthenticatedSettingsApiReady(): boolean {
  const [ready, setReady] = useState(() => authenticatedApiReady())

  useEffect(() => {
    if (typeof window === 'undefined') return undefined
    const handleConfigChange = () => setReady(authenticatedApiReady())
    window.addEventListener(apiClientConfigChangedEvent, handleConfigChange)
    handleConfigChange()
    return () => {
      window.removeEventListener(apiClientConfigChangedEvent, handleConfigChange)
    }
  }, [])

  return ready
}

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
    && left.remote_model_catalog_enabled === right.remote_model_catalog_enabled
    && JSON.stringify(left.cli_sessions) === JSON.stringify(right.cli_sessions)
}

export function resetAppSettingsCacheForTests(): void {
  appSettingsCache = null
  appSettingsRequest = null
}

export async function loadAppSettings(options: { force?: boolean } = {}): Promise<AppSettings> {
  if (!options.force && appSettingsCache) return appSettingsCache
  if (!options.force && appSettingsRequest) return appSettingsRequest

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
  return request
}

export async function saveAppSettings(settings: AppSettings): Promise<AppSettings> {
  try {
    const saved = withRuntimeDefaults(await updateAppSettings(settings))
    appSettingsCache = saved
    toast.success('Settings saved')
    return saved
  } catch (error) {
    toast.error('Failed to save settings')
    throw error
  }
}

export function useAppSettings() {
  const apiReady = useAuthenticatedSettingsApiReady()
  const [settings, setSettings] = useState<AppSettings>(withRuntimeDefaults(DEFAULT_APP_SETTINGS))
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<unknown>(null)
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle')
  const [lastSaveError, setLastSaveError] = useState<unknown>(null)
  const latestSettingsRef = useRef<AppSettings>(withRuntimeDefaults(DEFAULT_APP_SETTINGS))
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const inflightRef = useRef<Promise<AppSettings | null> | null>(null)
  const pendingSettingsRef = useRef<AppSettings | null>(null)
  const performSaveRef = useRef<(nextSettings: AppSettings) => Promise<AppSettings | null>>(async () => null)

  useEffect(() => {
    if (!apiReady) {
      setIsLoading(true)
      return undefined
    }
    let cancelled = false
    setIsLoading(true)
    loadAppSettings()
      .then((nextSettings) => {
        if (cancelled) return
        latestSettingsRef.current = nextSettings
        setSettings(nextSettings)
        setError(null)
        syncI18nLanguage(nextSettings.language)
      })
      .catch((loadError) => {
        if (cancelled) return
        setError(loadError)
      })
      .finally(() => {
        if (!cancelled) {
          setIsLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [apiReady])

  const performSave = useCallback(async (nextSettings: AppSettings): Promise<AppSettings | null> => {
    setSaveStatus('saving')
    try {
      const saved = withRuntimeDefaults(await updateAppSettings(nextSettings))
      appSettingsCache = saved
      if (!pendingSettingsRef.current) {
        setSaveStatus('saved')
        setLastSaveError(null)
      }
      if (!pendingSettingsRef.current && appSettingsEqual(latestSettingsRef.current, nextSettings)) {
        latestSettingsRef.current = saved
        setSettings(saved)
      }
      return saved
    } catch (saveError) {
      if (!pendingSettingsRef.current) {
        setSaveStatus('error')
        setLastSaveError(saveError)
        const message = saveError instanceof Error ? saveError.message : 'Save failed'
        toast.error(`Settings save failed: ${message}`)
      }
      return null
    } finally {
      inflightRef.current = null
      const buffered = pendingSettingsRef.current
      if (buffered) {
        pendingSettingsRef.current = null
        inflightRef.current = performSaveRef.current(buffered)
      }
    }
  }, [])
  performSaveRef.current = performSave

  const queueSave = useCallback((nextSettings: AppSettings) => {
    if (timerRef.current) clearTimeout(timerRef.current)
    setSaveStatus('pending')
    if (inflightRef.current) {
      pendingSettingsRef.current = nextSettings
      timerRef.current = null
      return
    }
    timerRef.current = setTimeout(() => {
      timerRef.current = null
      if (inflightRef.current) {
        pendingSettingsRef.current = nextSettings
        return
      }
      inflightRef.current = performSave(nextSettings)
    }, APP_SETTINGS_SAVE_DELAY_MS)
  }, [performSave])

  const updateSettings = useCallback((patch: Partial<AppSettings>) => {
    setSettings((current) => {
      const next = withRuntimeDefaults({ ...current, ...patch })
      latestSettingsRef.current = next
      queueSave(next)
      return next
    })
  }, [queueSave])

  const setUserId = useCallback((userId: string) => {
    updateSettings({ user_id: userId })
  }, [updateSettings])

  const setGiteaHost = useCallback((giteaHost: string) => {
    updateSettings({ gitea_host: giteaHost })
  }, [updateSettings])

  const setDefaultSkillsDirectory = useCallback((defaultSkillsDirectory: string) => {
    updateSettings({ default_skills_directory: defaultSkillsDirectory })
  }, [updateSettings])

  const setLanguage = useCallback((language: AppLanguage) => {
    updateSettings({ language })
  }, [updateSettings])

  const setRemoteModelCatalogEnabled = useCallback((remoteModelCatalogEnabled: boolean) => {
    updateSettings({ remote_model_catalog_enabled: remoteModelCatalogEnabled })
  }, [updateSettings])

  const setCliSessions = useCallback((cliSessions: CliSessionSettings) => {
    updateSettings({ cli_sessions: cliSessions })
  }, [updateSettings])

  const save = useCallback(async () => {
    if (timerRef.current) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
    const saved = await performSave(latestSettingsRef.current)
    return saved ?? latestSettingsRef.current
  }, [performSave])

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
      timerRef.current = null
      pendingSettingsRef.current = null
    }
  }, [])

  return {
    settings,
    setUserId,
    setGiteaHost,
    setDefaultSkillsDirectory,
    setLanguage,
    setRemoteModelCatalogEnabled,
    setCliSessions,
    save,
    isLoading,
    error,
    saveStatus,
    lastSaveError,
  }
}
