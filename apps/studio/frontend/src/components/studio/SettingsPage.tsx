import { Bell, CircleUser, Cog, Keyboard, Monitor, Moon, Plug, ShieldCheck, Sun, X } from 'lucide-react'
import { useState } from 'react'
import { setTheme, useThemeValue, type Theme } from '../../store/themeStore'

type SectionId = 'account' | 'general' | 'appearance' | 'keybindings' | 'notifications' | 'integrations' | 'privacy'

const SECTIONS: Array<{ id: SectionId, label: string, icon: typeof Cog }> = [
  { id: 'account', label: 'Account', icon: CircleUser },
  { id: 'general', label: 'General', icon: Cog },
  { id: 'appearance', label: 'Appearance', icon: Monitor },
  { id: 'keybindings', label: 'Keybindings', icon: Keyboard },
  { id: 'notifications', label: 'Notifications', icon: Bell },
  { id: 'integrations', label: 'Integrations', icon: Plug },
  { id: 'privacy', label: 'Privacy', icon: ShieldCheck },
]

interface SettingsPageProps {
  onClose: () => void
}

function SectionTitle({ title, description }: { title: string, description?: string }) {
  return (
    <div className="mb-6">
      <h2 className="text-base font-semibold text-foreground">{title}</h2>
      {description ? <p className="mt-1 text-xs text-muted-foreground">{description}</p> : null}
    </div>
  )
}

function PlaceholderSection({ title }: { title: string }) {
  return (
    <div>
      <SectionTitle title={title} description="This area will be wired up later." />
    </div>
  )
}

function AppearanceSection() {
  const theme = useThemeValue()
  const themeOptions: Array<{ id: Theme, label: string, icon: typeof Sun }> = [
    { id: 'light', label: 'Light', icon: Sun },
    { id: 'dark', label: 'Dark', icon: Moon },
  ]

  return (
    <div>
      <SectionTitle title="Appearance" description="Theme and visual preferences." />
      <div className="flex items-start justify-between gap-6 py-3">
        <div className="min-w-0 flex-1">
          <label className="text-xs font-medium text-foreground">Theme</label>
          <p className="mt-0.5 text-[11px] leading-relaxed text-muted-foreground">Switch between light and dark themes.</p>
        </div>
        <div className="inline-flex items-center gap-0.5 rounded-md bg-muted p-0.5">
          {themeOptions.map((option) => (
            <button
              key={option.id}
              type="button"
              onClick={() => setTheme(option.id)}
              className={[
                'flex items-center gap-1.5 rounded-sm px-2.5 py-1 text-xs transition-colors',
                theme === option.id ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground',
              ].join(' ')}
            >
              <option.icon className="size-3.5" strokeWidth={1.75} />
              {option.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

function KeybindingsSection() {
  const bindings = [
    ['Toggle Assets panel', '1'],
    ['Toggle Input panel', '2'],
    ['Toggle Timeline panel', '3'],
    ['Toggle Properties panel', '4'],
  ]

  return (
    <div>
      <SectionTitle title="Keybindings" description="Default keyboard shortcuts." />
      <div className="space-y-px">
        {bindings.map(([action, keys]) => (
          <div key={action} className="flex items-center justify-between rounded-sm px-2 py-2 hover:bg-muted/40">
            <span className="text-xs text-foreground">{action}</span>
            <kbd className="rounded bg-muted px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground">{keys}</kbd>
          </div>
        ))}
      </div>
    </div>
  )
}

export function SettingsPage({ onClose }: SettingsPageProps) {
  const [active, setActive] = useState<SectionId>('account')

  return (
    <div className="flex size-full flex-col bg-background">
      <div className="flex h-11 shrink-0 items-center justify-between gap-2 border-b border-border pl-4 pr-2">
        <span className="text-sm font-semibold text-foreground">Settings</span>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close settings"
          className="inline-flex size-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
        >
          <X className="size-4" />
        </button>
      </div>

      <div className="flex min-h-0 flex-1">
        <nav className="w-56 shrink-0 border-r border-border bg-sidebar/40 px-2 py-4">
          {SECTIONS.map((section) => {
            const isActive = active === section.id
            return (
              <button
                key={section.id}
                type="button"
                onClick={() => setActive(section.id)}
                className={[
                  'flex w-full items-center gap-2.5 rounded-sm px-2.5 py-1.5 text-xs transition-colors',
                  isActive ? 'bg-sidebar-accent text-foreground' : 'text-muted-foreground hover:bg-sidebar-accent/60 hover:text-foreground',
                ].join(' ')}
              >
                <section.icon className="size-3.5" strokeWidth={1.75} />
                {section.label}
              </button>
            )
          })}
        </nav>

        <div className="min-w-0 flex-1 overflow-y-auto">
          <div className="max-w-2xl px-10 py-8">
            {active === 'account' ? <PlaceholderSection title="Account" /> : null}
            {active === 'general' ? <PlaceholderSection title="General" /> : null}
            {active === 'appearance' ? <AppearanceSection /> : null}
            {active === 'keybindings' ? <KeybindingsSection /> : null}
            {active === 'notifications' ? <PlaceholderSection title="Notifications" /> : null}
            {active === 'integrations' ? <PlaceholderSection title="Integrations" /> : null}
            {active === 'privacy' ? <PlaceholderSection title="Privacy" /> : null}
          </div>
        </div>
      </div>
    </div>
  )
}
