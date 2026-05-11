import { Bug, GitCompare, Home, Play, Sparkles, Wand2 } from 'lucide-react'
import { NavLink, useParams } from 'react-router-dom'

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

  return (
    <aside className="z-10 flex w-12 shrink-0 flex-col items-center gap-1 border-r border-border bg-sidebar px-2 py-3 text-sidebar-foreground">
      <NavLink
        to="/"
        aria-label="Home"
        className="mb-3 inline-flex size-8 items-center justify-center rounded-md bg-foreground text-background transition-opacity hover:opacity-90"
      >
        <Home className="size-4" />
      </NavLink>

      {TOOLBAR_ITEMS.map((item) => (
        <NavLink
          key={item.id}
          to={`${basePath}/${item.id}`}
          aria-label={item.label}
          className={({ isActive }) =>
            [
              'inline-flex size-8 items-center justify-center rounded-md transition-colors',
              isActive
                ? 'bg-secondary text-secondary-foreground'
                : 'text-muted-foreground hover:bg-accent hover:text-foreground',
            ].join(' ')
          }
        >
          <item.icon className="size-4" strokeWidth={1.75} />
        </NavLink>
      ))}
    </aside>
  )
}
