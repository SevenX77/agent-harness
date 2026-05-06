import { useEffect, useRef } from 'react'
import { FitAddon } from 'xterm-addon-fit'
import { Terminal as XTermTerminal } from 'xterm'
import 'xterm/css/xterm.css'
import { wsUrl } from '../api/client'
import type { TerminalSession } from '../api/types'
import type { TerminalStatus } from '../types/studio'

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

  useEffect(() => {
    if (!containerRef.current) {
      return undefined
    }

    const terminal = new XTermTerminal({
      cursorBlink: true,
      fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
      fontSize: 13,
      theme: {
        background: '#0f172a',
        foreground: '#e2e8f0',
      },
    })
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
    }
  }, [onStatusChange, session.ws_url])

  return <div ref={containerRef} className="h-full w-full bg-slate-950 p-2" />
}

export function TerminalPanel({ session, status, onStatusChange }: TerminalPanelProps) {
  return (
    <div className="flex h-full flex-col">
      <div className="flex shrink-0 items-center justify-between border-b border-gray-200 dark:border-slate-800 bg-gray-50 dark:bg-slate-950 px-3 py-2 text-xs text-gray-600 dark:text-gray-400">
        <span>{session ? session.cwd : 'No CLI session'}</span>
        <span className="font-medium">{status}</span>
      </div>
      <div className="flex-1 overflow-hidden">
        {session ? (
          <TerminalEmulator session={session} onStatusChange={onStatusChange} />
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-gray-400">
            Open a CLI session for the active skill
          </div>
        )}
      </div>
    </div>
  )
}
