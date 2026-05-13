import { useCallback, useEffect, useState } from 'react'
import { toast } from 'sonner'
import { getAppSettings, updateAppSettings } from '../api/client'
import type { AppSettings } from '../api/types'

export const DEFAULT_APP_SETTINGS: AppSettings = {
  user_id: '',
  gitea_host: '',
}

export async function loadAppSettings(): Promise<AppSettings> {
  try {
    return await getAppSettings()
  } catch (error) {
    console.warn('Failed to load settings', error)
    return DEFAULT_APP_SETTINGS
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
  const [settings, setSettings] = useState<AppSettings>(DEFAULT_APP_SETTINGS)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<unknown>(null)

  useEffect(() => {
    let cancelled = false
    setIsLoading(true)
    loadAppSettings()
      .then((nextSettings) => {
        if (cancelled) return
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

  const setUserId = useCallback((userId: string) => {
    setSettings((current) => ({ ...current, user_id: userId }))
  }, [])

  const setGiteaHost = useCallback((giteaHost: string) => {
    setSettings((current) => ({ ...current, gitea_host: giteaHost }))
  }, [])

  const save = useCallback(async () => {
    const saved = await saveAppSettings(settings)
    setSettings(saved)
    return saved
  }, [settings])

  return {
    settings,
    setUserId,
    setGiteaHost,
    save,
    isLoading,
    error,
  }
}
