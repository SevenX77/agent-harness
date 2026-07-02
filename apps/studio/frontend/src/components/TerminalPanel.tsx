import { useEffect, useRef } from 'react'
import { FitAddon } from 'xterm-addon-fit'
import { Terminal as XTermTerminal, type ITheme } from 'xterm'
import 'xterm/css/xterm.css'
import { wsUrl } from '../api/client'
import type { TerminalSession } from '../api/types'
import type { TerminalStatus } from '../types/studio'
import { useThemeValue } from '../store/themeStore'

// xterm draws to a canvas, so it ignores the container's `bg-background` class —
// it needs actual color VALUES. Read the live oklch(...) tokens (any valid CSS
// color string works here) so the terminal follows the active theme instead of
// staying a hardcoded dark island when the app is in light mode.
function terminalThemeFromTokens(): ITheme {
  const style = getComputedStyle(document.documentElement)
  const read = (name: string) => style.getPropertyValue(name).trim()
  return {
    background: read('--background'),
    foreground: read('--foreground'),
    cursor: read('--primary'),
    selectionBackground: read('--muted'),
  }
}

interface TerminalPanelProps {
  session: TerminalSession | null
  status: TerminalStatus
  onStatusChange: (status: TerminalStatus) => void
}

interface TerminalEmulatorProps {
  session: TerminalSession
  onStatusChange: (status: TerminalStatus) => void
}

function TerminalEmulator({ session, onStatusChange }: TerminalEmulatorProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const terminalRef = useRef<XTermTerminal | null>(null)
  const theme = useThemeValue()

  useEffect(() => {
    if (!containerRef.current) {
      return undefined
    }

    const terminal = new XTermTerminal({
      cursorBlink: true,
      fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
      fontSize: 13,
      theme: terminalThemeFromTokens(),
    })
    terminalRef.current = terminal
    const fitAddon = new FitAddon()
    terminal.loadAddon(fitAddon)
    terminal.open(containerRef.current)
    fitAddon.fit()
    terminal.focus()

    const socket = new WebSocket(wsUrl(session.ws_url))
    socket.binaryType = 'arraybuffer'
    onStatusChange('connecting')

    socket.onopen = () => {
      onStatusChange('open')
      terminal.focus()
    }
    socket.onmessage = (message) => {
      if (typeof message.data === 'string') {
        terminal.write(message.data)
      } else if (message.data instanceof ArrayBuffer) {
        terminal.write(new Uint8Array(message.data))
      }
    }
    socket.onerror = () => onStatusChange('error')
    socket.onclose = () => onStatusChange('closed')

    const dataDisposable = terminal.onData((data) => {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send(data)
      }
    })
    const resize = () => fitAddon.fit()
    window.addEventListener('resize', resize)

    return () => {
      window.removeEventListener('resize', resize)
      dataDisposable.dispose()
      socket.close()
      terminal.dispose()
      terminalRef.current = null
    }
  }, [onStatusChange, session.ws_url])

  // Live theme toggle: update the existing terminal's palette in place —
  // deliberately NOT in the construction effect above, which would tear
  // down and reconnect the WebSocket session on every theme flip.
  useEffect(() => {
    if (terminalRef.current) {
      terminalRef.current.options.theme = terminalThemeFromTokens()
    }
  }, [theme])

  return <div ref={containerRef} className="h-full w-full bg-background p-2" />
}

export function TerminalPanel({ session, status, onStatusChange }: TerminalPanelProps) {
  return (
    <div className="flex h-full flex-col">
      <div className="flex shrink-0 items-center justify-between border-b border-border bg-card px-3 py-2 text-xs text-muted-foreground">
        <span>{session ? session.cwd : 'No CLI session'}</span>
        <span className="font-medium">{status}</span>
      </div>
      <div className="flex-1 overflow-hidden">
        {session ? (
          <TerminalEmulator session={session} onStatusChange={onStatusChange} />
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            Open a CLI session for the active skill
          </div>
        )}
      </div>
    </div>
  )
}
