import { useCallback, useEffect, useRef, useState, type ReactElement, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import i18n from '../i18n'
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
import { sidecarPortAnswers } from './runtime-gate-sidecar-probe'

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
  const { t } = useTranslation('runtimeGate')
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
            <span className="text-muted-foreground">{t('banner.connecting')}</span>
          ) : (
            <>
              <span className="text-destructive">
                {t('banner.unavailablePrefix')}
                {message ? ` (${message})` : ''}
              </span>
              <button
                type="button"
                onClick={onRetry}
                className="rounded border border-border px-2 py-0.5 font-medium text-foreground hover:bg-accent"
              >
                {t('banner.retry')}
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
// Read at call time (not module-load time) via `i18n.t` — not a hook, since
// this constant is consumed inside `useBackendDownSignal`'s callback rather
// than during render — so a language switch between renders is reflected the
// next time the sidecar actually goes down, not baked in at import time.
function backendDownInitialMessage(): string {
  return i18n.t('banner.connectionLostReconnecting', { ns: 'runtimeGate' })
}

// Shown when the automatic restart declined to fire because the sidecar's port
// still answered. The banner stays up because something IS wrong — the app could
// not reach the backend — but the cause is not a dead process, so the remedy is
// the person's own Retry rather than a restart we would be guessing at.
function backendAnsweringButUnreachableMessage(): string {
  return i18n.t('banner.unreachableButAnswering', { ns: 'runtimeGate' })
}

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

  // Recovery episodes are numbered so that work started inside one can tell
  // whether it still belongs to the present. Clearing the timer is not enough
  // any more: the port probe below runs for up to its own timeout, and a verdict
  // that lands after the episode ended describes a sidecar instance that is gone
  // — acting on it would restart the healthy one that replaced it. Same idea as
  // the `cancelled` flag in the boot effect below, kept in a ref because the
  // schedule lives outside React's render cycle.
  const recoveryEpisodeRef = useRef(0)

  const endRecoveryEpisode = useCallback((): void => {
    clearScheduledAutoRestart()
    recoveryEpisodeRef.current += 1
    autoRestartStateRef.current = initialAutoRestartState()
  }, [clearScheduledAutoRestart])

  const markReady = useCallback((): void => {
    endRecoveryEpisode()
    setMessage('')
    setStatus('ready')
  }, [endRecoveryEpisode])

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
      const episode = recoveryEpisodeRef.current
      // confirm-before-you-kill: both signals that get us here are weak, and
      // this is the moment the weakness would cost something irreversible. See
      // `runtime-gate-sidecar-probe.ts` for why the check sits HERE rather than
      // in front of the banner.
      sidecarPortAnswers()
        .then((answers) => {
          // A manual Retry (or a restart that already succeeded) ended this
          // episode while the probe was in flight. Its verdict is about a
          // sidecar instance that no longer exists, so it decides nothing.
          if (episode !== recoveryEpisodeRef.current) return undefined
          if (answers) {
            // Something is serving on that port, so the process is not gone —
            // whatever the weak signal saw, this is not ours to kill. The banner
            // and its Retry are already on screen; stop here rather than
            // rescheduling, so nothing turns into a restart poller.
            setMessage(backendAnsweringButUnreachableMessage())
            return undefined
          }
          return restartSidecarAutomatic().then(() => {
            markReady()
          })
        })
        .catch((error: unknown) => {
          // Same test, and for the sharper reason: without it a failed attempt
          // from an abandoned episode would schedule the NEXT one, reviving a
          // recovery loop the person had already taken over.
          if (episode !== recoveryEpisodeRef.current) return
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
    setMessage(backendDownInitialMessage())
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
    endRecoveryEpisode()
    setAttempt((value) => value + 1)
  }

  return (
    <RuntimeShell status={status} message={message} onRetry={handleRetry}>
      {children}
    </RuntimeShell>
  )
}
