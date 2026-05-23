import { useCallback, useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { getAppSettings, updateAppSettings } from '../api/client'
import type { AppSettings } from '../api/types'
import type { SaveStatus } from './useDebouncedCredentialsSave'
import { runtimeDefaultSkillsDirectory } from '../utils/skill-paths'

export const DEFAULT_APP_SETTINGS: AppSettings = {
  user_id: '',
  gitea_host: '',
  default_skills_directory: '',
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

function appSettingsEqual(left: AppSettings, right: AppSettings) {
  return left.user_id === right.user_id
    && left.gitea_host === right.gitea_host
    && left.default_skills_directory === right.default_skills_directory
}

export async function loadAppSettings(): Promise<AppSettings> {
  try {
    return withRuntimeDefaults(await getAppSettings())
  } catch (error) {
    console.warn('Failed to load settings', error)
    return withRuntimeDefaults(DEFAULT_APP_SETTINGS)
  }
}

export async function saveAppSettings(settings: AppSettings): Promise<AppSettings> {
  try {
    const saved = await updateAppSettings(settings)
    toast.success('Settings saved')
    return saved
  } catch (error) {
    toast.error('Failed to save settings')
    throw error
  }
}

export function useAppSettings() {
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
    let cancelled = false
    setIsLoading(true)
    loadAppSettings()
      .then((nextSettings) => {
        if (cancelled) return
        latestSettingsRef.current = nextSettings
        setSettings(nextSettings)
        setError(null)
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
  }, [])

  const performSave = useCallback(async (nextSettings: AppSettings): Promise<AppSettings | null> => {
    setSaveStatus('saving')
    try {
      const saved = withRuntimeDefaults(await updateAppSettings(nextSettings))
      setSaveStatus('saved')
      setLastSaveError(null)
      if (!pendingSettingsRef.current && appSettingsEqual(latestSettingsRef.current, nextSettings)) {
        latestSettingsRef.current = saved
        setSettings(saved)
      }
      return saved
    } catch (saveError) {
      setSaveStatus('error')
      setLastSaveError(saveError)
      const message = saveError instanceof Error ? saveError.message : 'Save failed'
      toast.error(`Settings save failed: ${message}`)
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
    save,
    isLoading,
    error,
    saveStatus,
    lastSaveError,
  }
}
