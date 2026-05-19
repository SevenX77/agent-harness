import { useSyncExternalStore } from "react"

type Theme = "light" | "dark"

const listeners = new Set<() => void>()

function getInitialTheme(): Theme {
  if (typeof window === "undefined") return "dark"
  const stored = localStorage.getItem("theme")
  if (stored === "light" || stored === "dark") return stored
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light"
}

function applyTheme(t: Theme) {
  if (typeof document === "undefined") return
  document.documentElement.classList.remove("light", "dark")
  document.documentElement.classList.add(t)
}

let currentTheme: Theme = getInitialTheme()
applyTheme(currentTheme)

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

function getSnapshot(): Theme {
  return currentTheme
}

function getServerSnapshot(): Theme {
  return "dark"
}

export function setTheme(next: Theme) {
  if (currentTheme === next) return
  currentTheme = next
  if (typeof window !== "undefined") {
    localStorage.setItem("theme", next)
  }
  applyTheme(next)
  listeners.forEach((l) => l())
}

if (typeof window !== "undefined") {
  const mq = window.matchMedia("(prefers-color-scheme: dark)")
  mq.addEventListener("change", (e) => {
    const stored = localStorage.getItem("theme")
    if (stored === "light" || stored === "dark") return
    setTheme(e.matches ? "dark" : "light")
  })
}

export function useTheme() {
  const theme = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot)
  return {
    theme,
    setTheme,
    toggleTheme: () => setTheme(theme === "dark" ? "light" : "dark"),
  }
}
