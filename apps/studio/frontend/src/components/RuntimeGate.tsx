import { useCallback, useEffect, useRef, useState, type ReactElement, type ReactNode } from 'react'
import {
  initializeRuntimeConfig,
  restartSidecar,
  restartSidecarAutomatic,
  subscribeToSidecarRestart,
} from '../config/runtime'
import { errorMessage } from '../utils/errors'
import { useBackendDownSignal } from '../hooks/useBackendDownSignal'
import {
  canAttemptAutoRestart,
  initialAutoRestartState,
  nextAutoRestartDelayMs,
  recordAutoRestartAttempt,
  type AutoRestartState,
} from './runtime-gate-auto-restart'

type RuntimeStatus = 'loading' | 'ready' | 'error'

interface RuntimeGateProps {
  children: ReactNode
}

interface RuntimeShellProps {
  status: RuntimeStatus
  message: string
  onRetry: () => void
  children: ReactNode
}

// D10 / native-fs F5: the app shell renders immediately ("skeleton 就行,
// 不需要 bootstrap"). Sidecar/runtime startup is surfaced as a non-blocking
// banner — a failed sidecar shows scoped errors, it never hides the whole UI.
export function RuntimeShell({ status, message, onRetry, children }: RuntimeShellProps): ReactElement {
  return (
    <>
      {children}
      {status !== 'ready' ? (
        <div
          role="status"
          aria-live="polite"
          className="fixed bottom-3 left-1/2 z-50 flex -translate-x-1/2 items-center gap-3 rounded-md border border-border bg-background/95 px-3 py-2 text-xs shadow-lg backdrop-blur"
        >
          {status === 'loading' ? (
            <span className="text-muted-foreground">Connecting to backend…</span>
          ) : (
            <>
              <span className="text-destructive">
                Backend unavailable — some features are disabled.
                {message ? ` (${message})` : ''}
              </span>
              <button
                type="button"
                onClick={onRetry}
                className="rounded border border-border px-2 py-0.5 font-medium text-foreground hover:bg-accent"
              >
                Retry
              </button>
            </>
          )}
        </div>
      ) : null}
    </>
  )
}

// Shown the instant liveness fails, before the first automatic attempt below
// has reported anything of its own — replaced by that attempt's real error
// text (or by nothing at all, on success) within `AUTO_RESTART_DELAYS_MS[0]`.
const BACKEND_DOWN_INITIAL_MESSAGE = 'Backend connection lost. Reconnecting…'

export function RuntimeGate({ children }: RuntimeGateProps) {
  const [status, setStatus] = useState<RuntimeStatus>('loading')
  const [message, setMessage] = useState('')
  const [attempt, setAttempt] = useState(0)

  // Bounded automatic-restart bookkeeping (dead-sidecar-says-so). Refs, not
  // state: the schedule is driven by its own setTimeout chain, not by re-
  // renders, and nothing here needs to trigger one on its own.
  const autoRestartTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const autoRestartStateRef = useRef<AutoRestartState>(initialAutoRestartState())

  // Stable across renders (useCallback, no reactive deps: only refs and
  // setState setters, both of which React guarantees are stable identities) —
  // so the boot/retry effect below can name it in a dependency array without
  // re-running every render.
  const clearScheduledAutoRestart = useCallback((): void => {
    if (autoRestartTimerRef.current !== undefined) {
      clearTimeout(autoRestartTimerRef.current)
      autoRestartTimerRef.current = undefined
    }
  }, [])

  const markReady = useCallback((): void => {
    clearScheduledAutoRestart()
    autoRestartStateRef.current = initialAutoRestartState()
    setMessage('')
    setStatus('ready')
  }, [clearScheduledAutoRestart])

  // Paces automatic attempts on AUTO_RESTART_DELAYS_MS (1s/4s/16s), calling
  // `restartSidecarAutomatic` — never `restartSidecar` — so a spent budget
  // never touches the manual-retry path (see runtime-gate-auto-restart.ts and
  // the Rust-side SidecarSupervisor.restart_automatic doc for why the two are
  // separate commands). Stops silently once the budget is spent: the banner
  // scheduled by `useBackendDownSignal` below is already showing, and it
  // already carries the last attempt's own error text.
  function scheduleAutoRestart(): void {
    if (!canAttemptAutoRestart(autoRestartStateRef.current, Date.now())) return
    const delay = nextAutoRestartDelayMs(autoRestartStateRef.current)
    autoRestartTimerRef.current = setTimeout(() => {
      autoRestartTimerRef.current = undefined
      autoRestartStateRef.current = recordAutoRestartAttempt(autoRestartStateRef.current, Date.now())
      restartSidecarAutomatic()
        .then(() => {
          markReady()
        })
        .catch((error: unknown) => {
          setMessage(errorMessage(error))
          scheduleAutoRestart()
        })
    }, delay)
  }

  // The first pass reads the sidecar the shell already started at boot. Every
  // later pass is the user pressing Retry, which has to ASK FOR a sidecar
  // (shell-layout F5): with none running, re-reading the config only replays the
  // failure the shell recorded at boot — the same string, press after press.
  // Both paths land on 'loading' first, so a restart that takes its health
  // timeout looks like work in progress rather than another dead button.
  useEffect(() => {
    let cancelled = false
    setStatus('loading')
    const connecting = attempt === 0 ? initializeRuntimeConfig() : restartSidecar()
    connecting
      .then(() => {
        if (!cancelled) {
          markReady()
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setMessage(errorMessage(error))
          setStatus('error')
        }
      })
    return () => {
      cancelled = true
    }
  }, [attempt, markReady])

  // dead-sidecar-says-so: `status` used to be frozen at whatever the effect
  // above last set it to — a sidecar that died AFTER boot left it stuck on
  // 'ready' forever, with no banner and no Retry (verified live: 9s of total
  // silence after killing the process). This is the fix's other half: react
  // to the sidecar dying on its OWN, not just to a manual Retry. Enabled only
  // while 'ready' — once this fires, status leaves 'ready', which is also
  // what lets the hook re-arm for the NEXT episode once we return to 'ready'.
  useBackendDownSignal(status === 'ready', () => {
    setStatus('error')
    setMessage(BACKEND_DOWN_INITIAL_MESSAGE)
    autoRestartStateRef.current = initialAutoRestartState()
    scheduleAutoRestart()
  })

  useEffect(() => clearScheduledAutoRestart, [clearScheduledAutoRestart])

  // R-F13 — listen for `sidecar-restarted` Tauri events so a sidecar token
  // rotation propagates into `currentApiToken` before `useStudioEventStream`
  // schedules its next reconnect attempt (which reads the token via wsUrl()).
  // The subscription survives across RuntimeGate retries; in non-Tauri builds
  // `subscribeToSidecarRestart` is a no-op.
  useEffect(() => {
    let unlisten: (() => void) | undefined
    let cancelled = false
    subscribeToSidecarRestart().then((dispose) => {
      if (cancelled) {
        dispose()
      } else {
        unlisten = dispose
      }
    })
    return () => {
      cancelled = true
      if (unlisten) unlisten()
    }
  }, [])

  // A person pressing Retry is never subject to the automatic budget above
  // (Rust-side enforcement: `SidecarSupervisor::restart_automatic` vs
  // `::restart`) and always wins any race with a pending automatic attempt —
  // cancel the timer first so the two never fire back-to-back into the shell.
  function handleRetry(): void {
    clearScheduledAutoRestart()
    autoRestartStateRef.current = initialAutoRestartState()
    setAttempt((value) => value + 1)
  }

  return (
    <RuntimeShell status={status} message={message} onRetry={handleRetry}>
      {children}
    </RuntimeShell>
  )
}
