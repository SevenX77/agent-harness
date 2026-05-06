import { X } from 'lucide-react'
import { hotkeyLabel } from '../../utils/hotkeys'

interface ShortcutItem {
  keys: string
  action: string
  group: string
}

const SHORTCUTS: ShortcutItem[] = [
  { keys: 'mod+s', action: 'Save and lint SKILL.md', group: 'Core' },
  { keys: 'mod+enter', action: 'Run selected skill', group: 'Core' },
  { keys: 'mod+n', action: 'Create new skill', group: 'Core' },
  { keys: 'mod+k', action: 'Open command palette', group: 'Navigation' },
  { keys: 'mod+p', action: 'Search and switch skills', group: 'Navigation' },
  { keys: '?', action: 'Show this shortcut guide', group: 'Help' },
  { keys: 'escape', action: 'Close active modal or drawer', group: 'Help' },
]

interface ShortcutsCheatSheetProps {
  open: boolean
  onClose: () => void
}

export function ShortcutsCheatSheet({ open, onClose }: ShortcutsCheatSheetProps) {
  if (!open) {
    return null
  }

  const groups = Array.from(new Set(SHORTCUTS.map((shortcut) => shortcut.group)))

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 px-4">
      <div className="w-full max-w-xl overflow-hidden rounded-md border border-slate-200 bg-white shadow-2xl dark:border-slate-800 dark:bg-slate-950">
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4 dark:border-slate-800">
          <div>
            <h2 className="text-lg font-bold text-slate-900 dark:text-slate-50">Keyboard Shortcuts</h2>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              Global shortcuts pause while typing in fields or Monaco.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
            title="Close shortcut guide"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="space-y-5 p-5">
          {groups.map((group) => (
            <section key={group}>
              <h3 className="mb-2 text-xs font-bold uppercase text-slate-500 dark:text-slate-400">
                {group}
              </h3>
              <div className="space-y-2">
                {SHORTCUTS.filter((shortcut) => shortcut.group === group).map((shortcut) => (
                  <div
                    key={shortcut.keys}
                    className="flex items-center justify-between gap-3 rounded-md bg-slate-50 px-3 py-2 dark:bg-slate-900"
                  >
                    <span className="text-sm font-medium text-slate-700 dark:text-slate-200">
                      {shortcut.action}
                    </span>
                    <kbd className="shrink-0 rounded border border-slate-300 bg-white px-2 py-1 text-xs font-semibold text-slate-500 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-400">
                      {hotkeyLabel(shortcut.keys)}
                    </kbd>
                  </div>
                ))}
              </div>
            </section>
          ))}
        </div>
      </div>
    </div>
  )
}
