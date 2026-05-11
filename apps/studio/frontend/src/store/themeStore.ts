import { useSyncExternalStore } from 'react'

export type Theme = 'light' | 'dark'

const STORAGE_KEY = 'theme'
const subscribers = new Set<() => void>()

function systemTheme(): Theme {
  if (typeof window === 'undefined') {
    return 'light'
  }
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function readStoredTheme(): Theme | null {
  if (typeof window === 'undefined') {
    return null
  }
  const stored = window.localStorage.getItem(STORAGE_KEY)
  return stored === 'light' || stored === 'dark' ? stored : null
}

function currentTheme(): Theme {
  return readStoredTheme() ?? systemTheme()
}

function applyTheme(theme: Theme) {
  if (typeof document === 'undefined') {
    return
  }
  document.documentElement.classList.toggle('dark', theme === 'dark')
  document.documentElement.classList.toggle('light', theme === 'light')
}

function emitChange() {
  applyTheme(currentTheme())
  subscribers.forEach((subscriber) => subscriber())
}

export function setTheme(theme: Theme) {
  window.localStorage.setItem(STORAGE_KEY, theme)
  emitChange()
}

export function toggleTheme() {
  setTheme(currentTheme() === 'dark' ? 'light' : 'dark')
}

export function subscribeTheme(callback: () => void) {
  subscribers.add(callback)

  if (subscribers.size === 1 && typeof window !== 'undefined') {
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    media.addEventListener('change', emitChange)
    window.addEventListener('storage', emitChange)
  }

  return () => {
    subscribers.delete(callback)
    if (subscribers.size === 0 && typeof window !== 'undefined') {
      const media = window.matchMedia('(prefers-color-scheme: dark)')
      media.removeEventListener('change', emitChange)
      window.removeEventListener('storage', emitChange)
    }
  }
}

export function useThemeValue() {
  return useSyncExternalStore(subscribeTheme, currentTheme, () => 'light')
}

applyTheme(currentTheme())
