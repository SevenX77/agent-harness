import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { CommandPalette, type CommandAction } from '../shortcuts/CommandPalette'
import { ShortcutsCheatSheet } from '../shortcuts/ShortcutsCheatSheet'
import { useGlobalShortcuts } from '../../hooks/useGlobalShortcuts'

export function GlobalShortcutShell() {
  const navigate = useNavigate()
  const { register } = useGlobalShortcuts()
  const [commandOpen, setCommandOpen] = useState(false)
  const [shortcutsOpen, setShortcutsOpen] = useState(false)

  const actions = useMemo<CommandAction[]>(() => [
    {
      id: 'home',
      label: 'Go to Home',
      description: 'Return to the dashboard route',
      hotkey: '/',
      run: () => navigate('/'),
    },
    {
      id: 'settings',
      label: 'Open Settings',
      description: 'Configure Studio settings and credentials',
      run: () => navigate('/settings'),
    },
  ], [navigate])

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
