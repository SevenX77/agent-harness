import { Clock, FileInput, Files, Moon, Settings2, Sun } from 'lucide-react'
import { toggleTheme, useThemeValue } from '../../store/themeStore'

export type PanelKind = 'assets' | 'input' | 'timeline' | 'properties'

interface ToolbarProps {
  activePanel: PanelKind | null
  onPanelChange: (panel: PanelKind | null) => void
}

const TOOLBAR_ITEMS: Array<{ id: PanelKind, label: string, icon: typeof Files, shortcut: string }> = [
  { id: 'assets', label: 'Assets', icon: Files, shortcut: '1' },
  { id: 'input', label: 'Input', icon: FileInput, shortcut: '2' },
  { id: 'timeline', label: 'Trace Timeline', icon: Clock, shortcut: '3' },
  { id: 'properties', label: 'Properties', icon: Settings2, shortcut: '4' },
]

export function Toolbar({ activePanel, onPanelChange }: ToolbarProps) {
  const theme = useThemeValue()

  return (
    <aside className="z-10 flex w-12 shrink-0 flex-col items-center border-e border-border bg-sidebar px-2 py-3 text-sidebar-foreground">
      <div className="flex flex-col gap-1">
        {TOOLBAR_ITEMS.map((item) => {
          const isActive = activePanel === item.id
          return (
            <button
              key={item.id}
              type="button"
              aria-label={item.label}
              aria-pressed={isActive}
              title={`${item.label} ${item.shortcut}`}
              onClick={() => onPanelChange(isActive ? null : item.id)}
              className={[
                'inline-flex size-8 items-center justify-center rounded-md transition-colors',
                isActive ? 'bg-accent text-foreground' : 'text-muted-foreground hover:text-foreground',
              ].join(' ')}
            >
              <item.icon className="size-4" strokeWidth={1.75} />
            </button>
          )
        })}
      </div>

      <button
        type="button"
        aria-label="Toggle theme"
        title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
        onClick={() => toggleTheme()}
        className="mt-auto inline-flex size-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
      >
        {theme === 'dark' ? <Sun className="size-4" /> : <Moon className="size-4" />}
      </button>
    </aside>
  )
}
