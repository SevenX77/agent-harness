import {
  attachCodeAssistant,
  detachCliTerminal,
  openClaudeCode,
  openCodexCli,
  resizeCliTerminal,
  writeCliTerminal,
  type CliTerminalGrid,
} from '@/lib/tauri'

/**
 * Owns one CLI session's lifetime, separately from whatever renders it (design:
 * `docs/studio/mvp1/03_regions/copilot/ah-orchestration-design.md` §10).
 *
 * Starting a CLI runtime is a user intent, not a rendering side effect: the
 * panel starts a session when the user picks one from the header control, and
 * the terminal view is a pure renderer that attaches to it. Keeping those apart
 * is what makes a view remount harmless — React deliberately mounts effects
 * twice in development, and `ah start` is a lifecycle command that rejects the
 * second call as "still starting".
 *
 * Output produced before a renderer attaches is buffered and replayed, so the
 * session can start talking immediately — on Windows its opening bytes are a
 * cursor-position query that ConPTY blocks on until the terminal answers.
 */

export type CliTerminalAssistant = 'claude' | 'codex'
// 'resume' = 与 'open' 同一条启动流程,但让 claude 用 --continue 续上该工作区
// 最近一次对话(决议 2026-08-05 D-F2)。仅 claude 支持。
export type CliTerminalMode = 'open' | 'attach' | 'resume'

/** base64 chunk → the exact bytes the PTY produced (a chunk boundary can fall
 * inside a multi-byte character, so text decoding belongs to the emulator). */
export function cliTerminalOutputBytes(chunk: string): Uint8Array {
  if (!chunk) return new Uint8Array(0)
  const binary = atob(chunk)
  const bytes = new Uint8Array(binary.length)
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index)
  }
  return bytes
}

export type CliOutputSink = (bytes: Uint8Array) => void

export interface CliOutputPump {
  push: (chunk: string) => void
  /** Attach a renderer: replays the session's history, then streams live. */
  attach: (sink: CliOutputSink) => () => void
}

/**
 * Output is kept, not consumed, so EVERY renderer that attaches sees the same
 * screen. Draining the backlog into the first attacher silently breaks two real
 * cases: React's development double-mount (the first terminal is discarded
 * immediately, taking the backlog with it — including the cursor-position query
 * ConPTY blocks on) and any later re-attach, which would come up blank. The cap
 * keeps a long-running session from growing without bound.
 */
const CLI_OUTPUT_HISTORY_LIMIT_BYTES = 256 * 1024

export function createCliOutputPump(): CliOutputPump {
  let sink: CliOutputSink | null = null
  const history: Uint8Array[] = []
  let historyBytes = 0
  return {
    push(chunk) {
      const bytes = cliTerminalOutputBytes(chunk)
      history.push(bytes)
      historyBytes += bytes.length
      while (historyBytes > CLI_OUTPUT_HISTORY_LIMIT_BYTES && history.length > 1) {
        historyBytes -= (history.shift() as Uint8Array).length
      }
      sink?.(bytes)
    },
    attach(next) {
      sink = next
      for (const bytes of history) {
        next(bytes)
      }
      return () => {
        if (sink === next) sink = null
      }
    },
  }
}

export interface CliTerminalSession {
  id: string
  assistant: CliTerminalAssistant
  attach: (sink: CliOutputSink) => () => void
  write: (data: string) => void
  resize: (grid: CliTerminalGrid) => void
  /** Ends the local terminal client; the ah runtime keeps running (§10 D3). */
  detach: () => void
}

interface StartCliTerminalSessionParams {
  workspaceRoot: string
  assistant: CliTerminalAssistant
  mode: CliTerminalMode
  /** Grid to start at; the renderer re-reports its real one once it mounts. */
  grid: CliTerminalGrid
  onExit: () => void
}

export async function startCliTerminalSession({
  workspaceRoot,
  assistant,
  mode,
  grid,
  onExit,
}: StartCliTerminalSessionParams): Promise<CliTerminalSession | null> {
  const pump = createCliOutputPump()
  const handlers = {
    onOutput: (chunk: string) => pump.push(chunk),
    onExit: () => onExit(),
  }
  const id =
    mode === 'attach'
      ? await attachCodeAssistant(workspaceRoot, assistant, grid, handlers)
      : assistant === 'claude'
        ? await openClaudeCode(workspaceRoot, grid, handlers, {
            resumeLastConversation: mode === 'resume',
          })
        : await openCodexCli(workspaceRoot, grid, handlers)
  if (!id) return null

  return {
    id,
    assistant,
    attach: pump.attach,
    write: (data) => {
      void writeCliTerminal(id, data)
    },
    resize: (next) => {
      void resizeCliTerminal(id, next)
    },
    detach: () => {
      void detachCliTerminal(id)
    },
  }
}
