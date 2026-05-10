import { useEffect, useState } from "react"

type Theme = "light" | "dark"

function systemPrefersDark(): boolean {
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false
}

function applyTheme(next: Theme) {
  document.documentElement.classList.remove("light", "dark")
  document.documentElement.classList.add(next)
}

export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(() => {
    if (typeof window === "undefined") return "dark"
    const stored = localStorage.getItem("theme") as Theme | null
    if (stored === "light" || stored === "dark") return stored
    return systemPrefersDark() ? "dark" : "light"
  })

  useEffect(() => {
    applyTheme(theme)
  }, [theme])

  useEffect(() => {
    const stored = localStorage.getItem("theme")
    if (stored === "light" || stored === "dark") return
    const mq = window.matchMedia("(prefers-color-scheme: dark)")
    const handler = (e: MediaQueryListEvent) => {
      setThemeState(e.matches ? "dark" : "light")
    }
    mq.addEventListener("change", handler)
    return () => mq.removeEventListener("change", handler)
  }, [])

  const setTheme = (next: Theme) => {
    localStorage.setItem("theme", next)
    setThemeState(next)
  }

  const toggleTheme = () => {
    setTheme(theme === "dark" ? "light" : "dark")
  }

  return { theme, setTheme, toggleTheme }
}
