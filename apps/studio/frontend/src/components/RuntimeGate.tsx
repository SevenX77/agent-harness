import { useEffect, useState, type ReactElement, type ReactNode } from 'react'
import { initializeRuntimeConfig } from '../config/runtime'

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

export function RuntimeGate({ children }: RuntimeGateProps) {
  const [status, setStatus] = useState<RuntimeStatus>('loading')
  const [message, setMessage] = useState('')
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let cancelled = false
    setStatus('loading')
    initializeRuntimeConfig()
      .then(() => {
        if (!cancelled) {
          setStatus('ready')
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setMessage(error instanceof Error ? error.message : String(error))
          setStatus('error')
        }
      })
    return () => {
      cancelled = true
    }
  }, [attempt])

  return (
    <RuntimeShell status={status} message={message} onRetry={() => setAttempt((value) => value + 1)}>
      {children}
    </RuntimeShell>
  )
}
