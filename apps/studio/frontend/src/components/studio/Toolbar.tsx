import { Bug, GitCompare, Home, Moon, Play, Sparkles, Sun, Wand2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { NavLink, useParams } from 'react-router-dom'
import { lintStatusEvent, readLintStatus } from '../../hooks/useDebouncedLint'
import { toggleTheme, useThemeValue } from '../../store/themeStore'

const TOOLBAR_ITEMS = [
  { id: 'edit', label: 'Edit', icon: Wand2 },
  { id: 'predict', label: 'Predict', icon: Sparkles },
  { id: 'run', label: 'Run', icon: Play },
  { id: 'debug', label: 'Debug', icon: Bug },
  { id: 'eval', label: 'Eval', icon: GitCompare },
]

export function Toolbar() {
  const { skillId } = useParams()
  const basePath = skillId ? `/skill/${skillId}` : '/'
  const [lintStatus, setLintStatus] = useState(() => (skillId ? readLintStatus(skillId) : 'idle'))
  const theme = useThemeValue()

  useEffect(() => {
    if (!skillId) {
      setLintStatus('idle')
      return undefined
    }

    setLintStatus(readLintStatus(skillId))
    const listener = (event: Event) => {
      const detail = (event as CustomEvent<{ skillId: string }>).detail
      if (detail?.skillId === skillId) {
        setLintStatus(readLintStatus(skillId))
      }
    }
    window.addEventListener(lintStatusEvent, listener)
    return () => window.removeEventListener(lintStatusEvent, listener)
  }, [skillId])

  const lintLocked = lintStatus === 'checking' || lintStatus === 'failed'

  return (
    <aside className="z-10 flex w-12 shrink-0 flex-col items-center gap-1 border-e border-border bg-sidebar px-2 py-3 text-sidebar-foreground">
      <NavLink
        to="/"
        aria-label="Home"
        className="mb-3 inline-flex min-h-8 min-w-8 items-center justify-center rounded-md bg-foreground text-background transition-opacity hover:opacity-90"
      >
        <Home className="size-4" />
      </NavLink>

      {TOOLBAR_ITEMS.map((item) => (
        <NavLink
          key={item.id}
          to={`${basePath}/${item.id}`}
          aria-label={item.label}
          aria-disabled={(item.id === 'predict' || item.id === 'run') && lintLocked}
          onClick={(event) => {
            if ((item.id === 'predict' || item.id === 'run') && lintLocked) {
              event.preventDefault()
            }
          }}
          className={({ isActive }) =>
            [
              'inline-flex min-h-8 min-w-8 items-center justify-center rounded-md transition-colors',
              (item.id === 'predict' || item.id === 'run') && lintLocked ? 'pointer-events-auto opacity-45' : '',
              isActive
                ? 'bg-secondary text-secondary-foreground'
                : 'text-muted-foreground hover:bg-accent hover:text-foreground',
            ].join(' ')
          }
        >
          <item.icon className="size-4" strokeWidth={1.75} />
        </NavLink>
      ))}

      <button
        type="button"
        aria-label="Toggle theme"
        title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
        onClick={() => toggleTheme()}
        className="mt-auto inline-flex min-h-8 min-w-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
      >
        {theme === 'dark' ? <Sun className="size-4" /> : <Moon className="size-4" />}
      </button>
    </aside>
  )
}
