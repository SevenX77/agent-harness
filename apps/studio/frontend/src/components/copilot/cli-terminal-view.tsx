import { useEffect, useRef } from 'react'
import { FitAddon } from '@xterm/addon-fit'
import { Terminal as XTermTerminal, type ITheme } from '@xterm/xterm'
import '@xterm/xterm/css/xterm.css'
import { useThemeValue } from '@/store/themeStore'
import type { CliTerminalSession } from './cli-terminal-session'

/**
 * Renders one CLI session in place of the chat surface ("CLI 即 copilot",
 * design: `docs/studio/mvp1/03_regions/copilot/ah-orchestration-design.md`
 * §10). This component is a pure renderer: it never starts or stops a session,
 * it attaches to one the panel already owns, so mounting it twice (which React
 * does in development) can neither launch a second CLI nor kill a live one.
 */

interface CliTerminalViewProps {
  session: CliTerminalSession
}

// xterm paints to a canvas, so `bg-background` on the container means nothing to
// it — it needs colour VALUES. Reading the live tokens keeps the terminal in the
// active Studio theme instead of a hardcoded dark island.
function terminalThemeFromTokens(): ITheme {
  const style = getComputedStyle(document.documentElement)
  const read = (name: string) => style.getPropertyValue(name).trim()
  return {
    background: read('--background'),
    foreground: read('--foreground'),
    // The cursor follows the text colour, i.e. the classic terminal look
    // (white block in the dark theme). `--primary` made it near-invisible
    // against the terminal background (PM report 2026-08-07).
    cursor: read('--foreground'),
    selectionBackground: read('--muted'),
  }
}

export function CliTerminalView({ session }: CliTerminalViewProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const terminalRef = useRef<XTermTerminal | null>(null)
  const theme = useThemeValue()

  useEffect(() => {
    const container = containerRef.current
    if (!container) return undefined

    let opened = false
    let detachOutput: (() => void) | null = null
    const terminal = new XTermTerminal({
      cursorBlink: true,
      fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
      fontSize: 13,
      // Host-side history for the launcher's own output; once tmux attaches it
      // switches to the alternate screen and tmux owns scrollback (§10 D6).
      scrollback: 5000,
      theme: terminalThemeFromTokens(),
    })
    terminalRef.current = terminal
    const fitAddon = new FitAddon()
    terminal.loadAddon(fitAddon)

    const inputDisposable = terminal.onData((data) => session.write(data))
    const resizeDisposable = terminal.onResize(({ cols, rows }) => session.resize({ cols, rows }))

    // xterm measures a character cell from the live DOM, so opening into a
    // container that has not been laid out yet leaves the renderer without
    // dimensions. Wait for a real size, then open and take the output stream.
    const openWhenMeasured = () => {
      if (opened) return
      if (container.clientWidth === 0 || container.clientHeight === 0) return
      opened = true
      terminal.open(container)
      fitAddon.fit()
      terminal.focus()
      detachOutput = session.attach((bytes) => terminal.write(bytes))
      session.resize({ cols: terminal.cols, rows: terminal.rows })
    }

    const observer =
      typeof ResizeObserver === 'undefined'
        ? null
        : new ResizeObserver(() => {
            if (!opened) {
              openWhenMeasured()
              return
            }
            if (container.clientWidth === 0 || container.clientHeight === 0) return
            // fit() drives terminal.onResize above, which forwards the new grid
            // to the PTY so tmux redraws at the panel's real size.
            fitAddon.fit()
          })
    observer?.observe(container)
    openWhenMeasured()

    return () => {
      observer?.disconnect()
      inputDisposable.dispose()
      resizeDisposable.dispose()
      detachOutput?.()
      terminal.dispose()
      terminalRef.current = null
    }
  }, [session])

  // Live theme flip repaints the existing terminal instead of tearing it down.
  useEffect(() => {
    if (terminalRef.current) {
      terminalRef.current.options.theme = terminalThemeFromTokens()
    }
  }, [theme])

  return (
    <div ref={containerRef} data-studio-cli-terminal="true" className="min-h-0 flex-1 px-2 py-1" />
  )
}
