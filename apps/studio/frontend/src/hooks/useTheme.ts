import { setTheme, toggleTheme, useThemeValue } from '../store/themeStore'

export function useTheme() {
  const theme = useThemeValue()

  return {
    theme,
    isDarkMode: theme === 'dark',
    setTheme,
    setIsDarkMode: (next: boolean) => setTheme(next ? 'dark' : 'light'),
    toggleTheme,
  }
}
