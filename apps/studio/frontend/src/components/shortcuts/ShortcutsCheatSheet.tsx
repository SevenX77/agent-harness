import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '../ui/dialog'
import { Kbd } from '../ui/kbd'
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
  const groups = Array.from(new Set(SHORTCUTS.map((shortcut) => shortcut.group)))

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen) {
          onClose()
        }
      }}
    >
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Keyboard Shortcuts</DialogTitle>
          <DialogDescription>
            Global shortcuts pause while typing in fields or Monaco.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-5">
          {groups.map((group) => (
            <section key={group} className="space-y-2">
              <h3 className="text-xs font-medium uppercase text-muted-foreground">
                {group}
              </h3>
              <div className="space-y-2">
                {SHORTCUTS.filter((shortcut) => shortcut.group === group).map((shortcut) => (
                  <div
                    key={shortcut.keys}
                    className="flex items-center justify-between gap-3 rounded-md bg-muted/50 px-3 py-2"
                  >
                    <span className="text-sm font-medium text-foreground">
                      {shortcut.action}
                    </span>
                    <Kbd>{hotkeyLabel(shortcut.keys)}</Kbd>
                  </div>
                ))}
              </div>
            </section>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  )
}
