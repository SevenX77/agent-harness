import { useSyncExternalStore } from 'react'

export type Theme = 'light' | 'dark'

const STORAGE_KEY = 'theme'
const CHANNEL_NAME = 'studio-theme'
const subscribers = new Set<() => void>()
const sourceId = Math.random().toString(36).slice(2)
let themeChannel: BroadcastChannel | null = null
let listenersInstalled = false

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

function getThemeChannel() {
  if (themeChannel || typeof BroadcastChannel === 'undefined') {
    return themeChannel
  }
  try {
    themeChannel = new BroadcastChannel(CHANNEL_NAME)
  } catch {
    themeChannel = null
  }
  return themeChannel
}

function broadcastTheme(theme: Theme) {
  try {
    getThemeChannel()?.postMessage({ type: 'theme-change', theme, sourceId })
  } catch {
    themeChannel = null
  }
}

function handleBroadcast(message: MessageEvent) {
  const data: unknown = message.data
  if (!data || typeof data !== 'object') {
    return
  }
  const record = data as { type?: unknown, theme?: unknown, sourceId?: unknown }
  if (record.type !== 'theme-change' || record.sourceId === sourceId || (record.theme !== 'light' && record.theme !== 'dark')) {
    return
  }
  window.localStorage.setItem(STORAGE_KEY, record.theme)
  emitChange()
}

function handleStorage(event: StorageEvent) {
  if (event.key === STORAGE_KEY || event.key === null) {
    emitChange()
  }
}

function handleSystemThemeChange() {
  emitChange()
}

function installThemeListeners() {
  if (listenersInstalled || typeof window === 'undefined') {
    return
  }

  listenersInstalled = true
  const media = window.matchMedia('(prefers-color-scheme: dark)')
  media.addEventListener('change', handleSystemThemeChange)
  window.addEventListener('storage', handleStorage)
  getThemeChannel()?.addEventListener('message', handleBroadcast)
}

export function setTheme(theme: Theme) {
  window.localStorage.setItem(STORAGE_KEY, theme)
  emitChange()
  broadcastTheme(theme)
}

export function toggleTheme() {
  setTheme(currentTheme() === 'dark' ? 'light' : 'dark')
}

export function subscribeTheme(callback: () => void) {
  subscribers.add(callback)

  return () => {
    subscribers.delete(callback)
  }
}

export function useThemeValue() {
  return useSyncExternalStore(subscribeTheme, currentTheme, () => 'light')
}

installThemeListeners()
applyTheme(currentTheme())
