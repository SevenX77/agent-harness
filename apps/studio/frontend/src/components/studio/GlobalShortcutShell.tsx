import { useEffect, useMemo, useState } from 'react'
import { CommandPalette, type CommandAction } from '../shortcuts/CommandPalette'
import { ShortcutsCheatSheet } from '../shortcuts/ShortcutsCheatSheet'
import { useGlobalShortcuts } from '../../hooks/useGlobalShortcuts'

export function GlobalShortcutShell() {
  const { register } = useGlobalShortcuts()
  const [commandOpen, setCommandOpen] = useState(false)
  const [shortcutsOpen, setShortcutsOpen] = useState(false)

  const actions = useMemo<CommandAction[]>(() => [
    {
      id: 'home',
      label: 'Open Welcome',
      description: 'Welcome overlay is controlled by the workspace shell',
      hotkey: '/',
      run: () => setCommandOpen(false),
    },
    {
      id: 'settings',
      label: 'Open Settings',
      description: 'Settings will return in Phase 2',
      run: () => setCommandOpen(false),
    },
  ], [])

  useEffect(() => {
    const unregisterCommand = register('/', () => setCommandOpen(true))
    const unregisterShortcuts = register('?', () => setShortcutsOpen(true))

    return () => {
      unregisterCommand()
      unregisterShortcuts()
    }
  }, [register])

  return (
    <>
      <CommandPalette
        open={commandOpen}
        actions={actions}
        onClose={() => setCommandOpen(false)}
      />
      <ShortcutsCheatSheet
        open={shortcutsOpen}
        onClose={() => setShortcutsOpen(false)}
      />
    </>
  )
}
