// @vitest-environment jsdom
import { act, createElement } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { renderToStaticMarkup } from 'react-dom/server'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { configureApiBaseURL, configureApiToken } from '../api/client'
import { useStudioEventStream } from '../hooks/useStudioEventStream'
import { AUTO_RESTART_DELAYS_MS, AUTO_RESTART_MAX_ATTEMPTS } from './runtime-gate-auto-restart'
import { RuntimeGate, RuntimeShell } from './RuntimeGate'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

function render(status: 'loading' | 'ready' | 'error', message = ''): string {
  return renderToStaticMarkup(
    <RuntimeShell status={status} message={message} onRetry={() => undefined}>
      <div>app-shell-content</div>
    </RuntimeShell>,
  )
}

describe('RuntimeShell — D10 non-blocking startup gate', () => {
  it('renders the app shell when the sidecar/runtime fails (no full-screen block)', () => {
    const html = render('error', 'sidecar config unavailable')

    // The shell must remain mounted instead of being replaced by an error screen.
    expect(html).toContain('app-shell-content')
    // A non-blocking, observable degraded banner with a retry affordance.
    expect(html).toContain('Retry')
    expect(html.toLowerCase()).toContain('unavailable')
  })

  it('renders the shell while connecting (eager, no bootstrap gate)', () => {
    const html = render('loading')

    expect(html).toContain('app-shell-content')
    expect(html).toContain('Connecting')
  })

  it('renders only the shell once the runtime is ready', () => {
    const html = render('ready')

    expect(html).toContain('app-shell-content')
    expect(html).not.toContain('Retry')
    expect(html).not.toContain('Connecting')
  })
})

// dead-sidecar-says-so (2026-08-24): before this fix, RuntimeGate's boot
// effect only ran on mount / a manual Retry (`[attempt]` dependency array) —
// a sidecar that died AFTER boot left `status` frozen at 'ready' forever, so
// no banner and no Retry ever appeared (verified live: 9s of silence after
// killing the sidecar process). These tests drive the real component (not
// just the static RuntimeShell) through a post-ready death and back.
const runtimeMocks = vi.hoisted(() => ({
  initializeRuntimeConfig: vi.fn(),
  reconnectSidecar: vi.fn(),
  restartSidecar: vi.fn(),
  restartSidecarAutomatic: vi.fn(),
  subscribeToSidecarRestart: vi.fn(async () => () => {}),
}))

vi.mock('../config/runtime', () => runtimeMocks)

const READY_CONFIG = {
  port: 8787,
  baseURL: 'http://127.0.0.1:8787/api',
  wsURL: 'ws://127.0.0.1:8787/ws',
  resourceDir: '/resources',
  configDir: '/config',
  api_token: 'token',
}

interface FakeCloseEvent {
  code: number
  reason: string
  wasClean: boolean
}

class FakeWebSocket {
  static readonly CONNECTING = 0
  static readonly OPEN = 1
  static readonly CLOSING = 2
  static readonly CLOSED = 3
  static instances: FakeWebSocket[] = []

  readyState = FakeWebSocket.CONNECTING
  onopen: ((event: Event) => void) | null = null
  onclose: ((event: FakeCloseEvent) => void) | null = null
  onerror: ((event: Event) => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  readonly url: string

  constructor(url: string) {
    this.url = url
    FakeWebSocket.instances.push(this)
  }

  acceptOpen(): void {
    this.readyState = FakeWebSocket.OPEN
    this.onopen?.(new Event('open'))
  }

  dropWith(code: number, reason = ''): void {
    this.readyState = FakeWebSocket.CLOSED
    this.onclose?.({ code, reason, wasClean: false })
  }

  close(): void {
    this.readyState = FakeWebSocket.CLOSED
  }
}

let container: HTMLDivElement | undefined
let root: Root | undefined
const originalWebSocket = globalThis.WebSocket

// Mirrors Workspace.tsx's own, permanently-enabled `useStudioEventStream`
// subscriber: production always has at least one of these alive for the
// app's whole lifetime, so the shared hub's `subscribers.size` never actually
// reaches zero while RuntimeGate's OWN subscription (inside
// `useBackendDownSignal`) toggles off and back on across a down/recovery
// episode. Without this sibling, RuntimeGate would be the ONLY subscriber in
// this test tree, so disabling it would drop `subscribers.size` to zero and
// trigger a full `resetHubState()` — masking exactly the stale-state race the
// recovery-stops-when-it-succeeds tests below exist to catch.
const PERMANENT_SUBSCRIBER_CALLBACKS = {
  onRegistryChanged: (): void => {},
  onRolesChanged: (): void => {},
}

function PermanentSubscriber(): null {
  useStudioEventStream(PERMANENT_SUBSCRIBER_CALLBACKS)
  return null
}

async function mountReady(): Promise<void> {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  const mountedRoot = root

  await act(async () => {
    mountedRoot.render(
      createElement(
        RuntimeGate,
        null,
        createElement(PermanentSubscriber),
        createElement('div', null, 'app-shell-content'),
      ),
    )
    await Promise.resolve()
  })
}

function unmount(): void {
  if (!root || !container) return
  const mountedRoot = root
  act(() => {
    mountedRoot.unmount()
  })
  container.remove()
  root = undefined
  container = undefined
}

function bannerText(): string {
  return container?.textContent ?? ''
}

function findButton(): HTMLButtonElement | null {
  return container?.querySelector('button') ?? null
}

function clickRetry(): void {
  const button = findButton()
  if (!button) throw new Error('Retry button not found')
  act(() => {
    button.dispatchEvent(new MouseEvent('click', { bubbles: true }))
  })
}

async function flush(): Promise<void> {
  await act(async () => {
    await Promise.resolve()
    await Promise.resolve()
  })
}

async function advance(ms: number): Promise<void> {
  await act(async () => {
    vi.advanceTimersByTime(ms)
    await Promise.resolve()
    await Promise.resolve()
  })
}

// The automatic restart now asks the sidecar's port whether anything is still
// answering before it fires. Left unstubbed, `fetch` would attempt a REAL
// connection to 127.0.0.1:8787 and the result of this gate would depend on
// whether a sidecar happens to be running on the machine: green on a clean box,
// and silently skipping every restart below for a developer with the app open.
// The default is a `fetch` that throws, which is what these tests mean by a dead
// sidecar — and deliberately NOT named after connection-refused, because the
// production code cannot tell that apart from a reset or a CORS rejection
// either. A helper that claimed to stub one specific cause would assert a
// distinction the code does not make.
let probeFetch: ReturnType<typeof vi.fn>

function nothingAnswersOnTheSidecarPort(): void {
  probeFetch.mockRejectedValue(new TypeError('Failed to fetch'))
}

function sidecarPortAnswersWith(status: number): void {
  probeFetch.mockResolvedValue({ ok: status >= 200 && status < 300, status })
}

beforeEach(() => {
  vi.useFakeTimers()
  FakeWebSocket.instances = []
  ;(globalThis as unknown as { WebSocket: typeof FakeWebSocket }).WebSocket = FakeWebSocket
  probeFetch = vi.fn()
  vi.stubGlobal('fetch', probeFetch)
  nothingAnswersOnTheSidecarPort()
  configureApiBaseURL('http://127.0.0.1:8787/api')
  configureApiToken('token')
  runtimeMocks.initializeRuntimeConfig.mockReset().mockResolvedValue(READY_CONFIG)
  runtimeMocks.reconnectSidecar.mockReset().mockResolvedValue(READY_CONFIG)
  runtimeMocks.restartSidecar.mockReset().mockResolvedValue(READY_CONFIG)
  runtimeMocks.restartSidecarAutomatic.mockReset()
  runtimeMocks.subscribeToSidecarRestart.mockReset().mockResolvedValue(() => {})
})

afterEach(() => {
  unmount()
  vi.useRealTimers()
  vi.unstubAllGlobals()
  ;(globalThis as unknown as { WebSocket: typeof WebSocket }).WebSocket = originalWebSocket
  configureApiToken(null)
})

/**
 * confirm-before-you-kill — the automatic restart is the destructive act, so it
 * is where the weak liveness signals get checked.
 *
 * Both signals that reach RuntimeGate mean less than they look like.
 * `BACKEND_UNAVAILABLE_HTTP_EVENT` means "a call got no HTTP RESPONSE", which is
 * not "the process is gone" — a 500 the browser discards for missing
 * `Access-Control-Allow-Origin` reaches axios as ERR_NETWORK and looks exactly
 * the same from inside the interceptor. Acting on that restarted sidecars that
 * were serving fine, rotating their token and port and dropping in-flight runs.
 *
 * The check deliberately does NOT gate the banner. Banner and Retry appear only
 * once RuntimeGate leaves 'ready', so confirming before reporting would hide
 * both and leave a broken app with no message and no affordance — worse than
 * the spurious restart. Detection stays as sensitive as it was; only the
 * irreversible half asks for more evidence, and an unclear answer declines.
 */
describe('RuntimeGate — confirm-before-you-kill (the restart asks the port first)', () => {
  it('reports the outage as before: the recheck never delays or hides the banner', async () => {
    sidecarPortAnswersWith(200)
    await mountReady()

    await act(async () => {
      window.dispatchEvent(new Event('studio-backend-http-unavailable'))
    })

    // Banner and Retry are up immediately, with no probe awaited first.
    expect(bannerText().toLowerCase()).toContain('unavailable')
    expect(findButton()).not.toBeNull()
    expect(probeFetch).not.toHaveBeenCalled()
  })

  it('does NOT restart when the port still answers: it reconnects instead', async () => {
    sidecarPortAnswersWith(200)
    await mountReady()
    runtimeMocks.initializeRuntimeConfig.mockClear()

    await act(async () => {
      window.dispatchEvent(new Event('studio-backend-http-unavailable'))
    })
    await advance(AUTO_RESTART_DELAYS_MS[0] + 1)

    expect(probeFetch).toHaveBeenCalledTimes(1)
    expect(runtimeMocks.restartSidecarAutomatic).not.toHaveBeenCalled()
    // The non-destructive half of what Retry does. `reconnectSidecar`
    // specifically, not the boot path: boot keeps a token that is already set,
    // and a stale token is one of the things that gets us here.
    expect(runtimeMocks.reconnectSidecar).toHaveBeenCalledTimes(1)
    expect(runtimeMocks.initializeRuntimeConfig).not.toHaveBeenCalled()
    expect(bannerText().toLowerCase()).not.toContain('unavailable')
  })

  /**
   * Declining to restart must not be a dead end. Detection is armed by
   * `useBackendDownSignal(status === 'ready', …)`, so a branch that leaves
   * `status` on 'error' also leaves the app unable to notice the NEXT outage —
   * and the only way out would be the destructive Retry this whole change
   * exists to avoid. Whatever the branch decides, it has to end somewhere the
   * machine can leave.
   */
  it('re-arms detection after declining: a second outage is still noticed', async () => {
    sidecarPortAnswersWith(200)
    await mountReady()

    await act(async () => {
      window.dispatchEvent(new Event('studio-backend-http-unavailable'))
    })
    await advance(AUTO_RESTART_DELAYS_MS[0] + 1)
    expect(runtimeMocks.restartSidecarAutomatic).not.toHaveBeenCalled()
    // Back to a working app: no banner, nothing killed.
    expect(bannerText().toLowerCase()).not.toContain('unavailable')

    // The sidecar dies for real this time.
    nothingAnswersOnTheSidecarPort()
    runtimeMocks.restartSidecarAutomatic.mockResolvedValue(READY_CONFIG)
    await act(async () => {
      window.dispatchEvent(new Event('studio-backend-http-unavailable'))
    })
    expect(bannerText().toLowerCase()).toContain('unavailable')
    await advance(AUTO_RESTART_DELAYS_MS[0] + 1)

    expect(runtimeMocks.restartSidecarAutomatic).toHaveBeenCalledTimes(1)
  })

  it('treats a 503 as an answer: a process that replies is not a process to kill', async () => {
    sidecarPortAnswersWith(503)
    await mountReady()

    await act(async () => {
      window.dispatchEvent(new Event('studio-backend-http-unavailable'))
    })
    await advance(AUTO_RESTART_DELAYS_MS[0] + 1)

    expect(runtimeMocks.restartSidecarAutomatic).not.toHaveBeenCalled()
  })

  it('does not turn into a probe poller after reconnecting once', async () => {
    sidecarPortAnswersWith(200)
    await mountReady()

    await act(async () => {
      window.dispatchEvent(new Event('studio-backend-http-unavailable'))
    })
    await advance(AUTO_RESTART_DELAYS_MS[0] + 1)
    // Far past every remaining delay in the schedule. The reconnect ends the
    // episode, so nothing is left to fire: a new cycle needs a new outage, not
    // the passage of time.
    await advance(120_000)

    expect(probeFetch).toHaveBeenCalledTimes(1)
    expect(runtimeMocks.restartSidecarAutomatic).not.toHaveBeenCalled()
  })

  it('still restarts when nothing answers, exactly as before', async () => {
    nothingAnswersOnTheSidecarPort()
    runtimeMocks.restartSidecarAutomatic.mockResolvedValue(READY_CONFIG)
    await mountReady()

    await act(async () => {
      window.dispatchEvent(new Event('studio-backend-http-unavailable'))
    })
    await advance(AUTO_RESTART_DELAYS_MS[0] + 1)

    expect(runtimeMocks.restartSidecarAutomatic).toHaveBeenCalledTimes(1)
    expect(bannerText()).toContain('app-shell-content')
    expect(bannerText().toLowerCase()).not.toContain('unavailable')
  })

  /**
   * The probe took an ACTION that used to be instantaneous and gave it a
   * duration, and anything with a duration can be overtaken. `handleRetry`
   * cancels the pending timer, but a probe already in flight is not a timer —
   * so its verdict came back after the person's own restart had finished and
   * killed the sidecar they had just been given.
   *
   * This is the same hazard the boot effect above already guards with its
   * `cancelled` flag: an async result must be discarded when the episode it was
   * started for is over. The probe answers a question about a PARTICULAR sidecar
   * instance, and after a manual restart that instance no longer exists.
   */
  it('drops a probe verdict that arrives after a manual Retry already restarted', async () => {
    let answerTheProbe: (() => void) | undefined
    probeFetch.mockImplementation(
      () =>
        new Promise((_resolve, reject) => {
          answerTheProbe = () => reject(new TypeError('Failed to fetch'))
        }),
    )
    runtimeMocks.restartSidecarAutomatic.mockResolvedValue(READY_CONFIG)
    await mountReady()

    await act(async () => {
      window.dispatchEvent(new Event('studio-backend-http-unavailable'))
    })
    // The scheduled attempt fires and the probe is now in flight, unanswered.
    await advance(AUTO_RESTART_DELAYS_MS[0] + 1)
    expect(probeFetch).toHaveBeenCalledTimes(1)

    // The person does not wait for it. Retry restarts the sidecar itself.
    clickRetry()
    await flush()
    expect(runtimeMocks.restartSidecar).toHaveBeenCalledTimes(1)

    // Only now does the probe report that nothing was answering — true of the
    // instance it asked about, and irrelevant to the one now running.
    await act(async () => {
      answerTheProbe?.()
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(runtimeMocks.restartSidecarAutomatic).not.toHaveBeenCalled()
  })
})

describe('RuntimeGate — post-ready sidecar death is observable (dead-sidecar-says-so)', () => {
  it('boots to ready with no banner, matching the pre-fix baseline', async () => {
    await mountReady()

    expect(bannerText()).toContain('app-shell-content')
    expect(bannerText()).not.toContain('unavailable')
    expect(findButton()).toBeNull()
  })

  it('shows a persistent unavailable banner with Retry the moment an HTTP call gets no response', async () => {
    await mountReady()

    await act(async () => {
      window.dispatchEvent(new Event('studio-backend-http-unavailable'))
    })

    expect(bannerText().toLowerCase()).toContain('unavailable')
    expect(findButton()).not.toBeNull()
    expect(findButton()?.textContent).toContain('Retry')
    // The shell content stays mounted and usable throughout.
    expect(bannerText()).toContain('app-shell-content')
  })

  it('also reacts to the shared WebSocket connection being reported lost', async () => {
    runtimeMocks.restartSidecarAutomatic.mockReturnValue(new Promise(() => {}))
    await mountReady()

    act(() => {
      FakeWebSocket.instances[0]?.acceptOpen()
    })
    for (let i = 0; i < 3; i += 1) {
      const current = FakeWebSocket.instances[FakeWebSocket.instances.length - 1]
      act(() => {
        current?.dropWith(1006, 'abnormal')
      })
      await advance(60_000)
    }

    expect(bannerText().toLowerCase()).toContain('unavailable')
  })

  it('does not auto-dismiss: the banner stays visible across many ticks with no user action', async () => {
    runtimeMocks.restartSidecarAutomatic.mockRejectedValue(new Error('still down'))
    await mountReady()
    await act(async () => {
      window.dispatchEvent(new Event('studio-backend-http-unavailable'))
    })

    await advance(5 * 60_000)

    expect(bannerText().toLowerCase()).toContain('unavailable')
  })

  it('schedules bounded automatic restarts on the 1s/4s/16s backoff, then stops', async () => {
    runtimeMocks.restartSidecarAutomatic.mockRejectedValue(new Error('spawn failed'))
    await mountReady()

    await act(async () => {
      window.dispatchEvent(new Event('studio-backend-http-unavailable'))
    })
    expect(runtimeMocks.restartSidecarAutomatic).not.toHaveBeenCalled()

    for (let i = 0; i < AUTO_RESTART_MAX_ATTEMPTS; i += 1) {
      const delay = AUTO_RESTART_DELAYS_MS[i]
      await advance(delay - 1)
      expect(runtimeMocks.restartSidecarAutomatic).toHaveBeenCalledTimes(i)
      await advance(1)
      expect(runtimeMocks.restartSidecarAutomatic).toHaveBeenCalledTimes(i + 1)
    }

    // Bounded: no further automatic attempts even after a long wait.
    await advance(5 * 60_000)
    expect(runtimeMocks.restartSidecarAutomatic).toHaveBeenCalledTimes(AUTO_RESTART_MAX_ATTEMPTS)
  })

  it('a successful automatic attempt clears the banner and returns to ready', async () => {
    runtimeMocks.restartSidecarAutomatic
      .mockRejectedValueOnce(new Error('first attempt failed'))
      .mockResolvedValueOnce(READY_CONFIG)
    await mountReady()

    await act(async () => {
      window.dispatchEvent(new Event('studio-backend-http-unavailable'))
    })
    await advance(AUTO_RESTART_DELAYS_MS[0])
    expect(runtimeMocks.restartSidecarAutomatic).toHaveBeenCalledTimes(1)
    expect(bannerText().toLowerCase()).toContain('unavailable')

    await advance(AUTO_RESTART_DELAYS_MS[1])
    expect(runtimeMocks.restartSidecarAutomatic).toHaveBeenCalledTimes(2)

    expect(bannerText().toLowerCase()).not.toContain('unavailable')
    expect(findButton()).toBeNull()
  })

  it('after exhausting automatic attempts, shows the LAST attempt\'s own error text and keeps Retry usable', async () => {
    runtimeMocks.restartSidecarAutomatic
      .mockRejectedValueOnce(new Error('attempt one failed: vendor missing'))
      .mockRejectedValueOnce(new Error('attempt two failed: vendor missing'))
      .mockRejectedValueOnce(new Error('attempt three failed: vendor missing'))
    await mountReady()

    await act(async () => {
      window.dispatchEvent(new Event('studio-backend-http-unavailable'))
    })
    for (const delay of AUTO_RESTART_DELAYS_MS) {
      await advance(delay)
    }

    expect(runtimeMocks.restartSidecarAutomatic).toHaveBeenCalledTimes(AUTO_RESTART_MAX_ATTEMPTS)
    // The visible terminal state carries the LAST attempt's own error text.
    expect(bannerText()).toContain('attempt three failed: vendor missing')
    expect(bannerText()).not.toContain('attempt one failed')

    // Retry stays usable — clicking it attempts a MANUAL restart, which is
    // never refused by the exhausted automatic budget.
    runtimeMocks.restartSidecar.mockResolvedValueOnce(READY_CONFIG)
    clickRetry()
    await flush()

    expect(runtimeMocks.restartSidecar).toHaveBeenCalledTimes(1)
    expect(bannerText().toLowerCase()).not.toContain('unavailable')
  })

  it('a manual Retry cancels a pending automatic-restart timer instead of racing it', async () => {
    runtimeMocks.restartSidecarAutomatic.mockRejectedValue(new Error('should not be called'))
    await mountReady()

    await act(async () => {
      window.dispatchEvent(new Event('studio-backend-http-unavailable'))
    })
    // The first automatic attempt is scheduled for 1s from now but has not
    // fired yet — press Retry before it does.
    runtimeMocks.restartSidecar.mockResolvedValueOnce(READY_CONFIG)
    clickRetry()
    await flush()

    expect(runtimeMocks.restartSidecar).toHaveBeenCalledTimes(1)
    expect(bannerText().toLowerCase()).not.toContain('unavailable')

    // Advancing well past every automatic delay must not fire the cancelled
    // timer — it was cleared, not just superseded.
    await advance(5 * 60_000)
    expect(runtimeMocks.restartSidecarAutomatic).not.toHaveBeenCalled()
  })

  it('the shell content underneath stays mounted and usable throughout an outage', async () => {
    runtimeMocks.restartSidecarAutomatic.mockRejectedValue(new Error('still down'))
    await mountReady()

    await act(async () => {
      window.dispatchEvent(new Event('studio-backend-http-unavailable'))
    })
    await advance(AUTO_RESTART_DELAYS_MS[0])
    await advance(AUTO_RESTART_DELAYS_MS[1])
    await advance(AUTO_RESTART_DELAYS_MS[2])

    // The app never gets torn down / replaced by a full-screen error — the
    // shell content is present the whole time, banner or not.
    expect(bannerText()).toContain('app-shell-content')
  })
})

/**
 * recovery-stops-when-it-succeeds (2026-08-24): real-machine verification of
 * the fix above found the bounded auto-restart loop livelocked. A restart
 * attempt genuinely succeeded (confirmed in the Rust logs), but the shared
 * WS hub's `connectionLost` had not yet caught up — it takes a moment to
 * reconnect with the freshly-rotated token — and re-arming detection at
 * EXACTLY that instant read the stale `true` as a brand-new failure, firing a
 * second (then third) automatic restart. All three "succeeded," yet the
 * Rust-side budget (a single long-lived counter, correctly NOT reset by
 * automatic attempts — only a manual Retry resets it) still exhausted across
 * the three spurious rounds, freezing the banner on
 * "automatic restart budget exhausted — press Retry" while the sidecar sat
 * healthy the entire time.
 *
 * These tests drive the REAL (unmocked) `useBackendDownSignal` /
 * `useStudioEventStream` hub through that exact race — connectionLost is
 * left deliberately stale (true) at the moment `restartSidecarAutomatic`
 * resolves, by never opening a fresh FakeWebSocket for it to catch up on.
 *
 * The first automatic attempt is held PENDING (a manually-controlled deferred
 * promise) rather than pre-resolved: the 1s/4s/16s schedule and the WS hub's
 * own 1s ticker share the same fake-timer clock, so a single big
 * `advance(60_000)` used to detect the down-episode ALSO crosses the first
 * attempt's 1s delay in the same jump — a pre-resolved mock would settle
 * before the test ever got to inspect the "restart succeeded, WS still
 * stale" moment it exists to pin.
 */
describe('RuntimeGate — recovery-stops-when-it-succeeds (a successful restart ends its own episode)', () => {
  async function driveIntoADownEpisodeWithStaleConnectionLost(): Promise<{
    resolveFirstAttempt: (value: typeof READY_CONFIG) => void
  }> {
    let resolveFirstAttempt: (value: typeof READY_CONFIG) => void = () => {}
    const firstAttempt = new Promise<typeof READY_CONFIG>((resolve) => {
      resolveFirstAttempt = resolve
    })
    runtimeMocks.restartSidecarAutomatic.mockReturnValueOnce(firstAttempt)

    await mountReady()
    act(() => {
      FakeWebSocket.instances[0]?.acceptOpen()
    })
    for (let i = 0; i < 3; i += 1) {
      const current = FakeWebSocket.instances[FakeWebSocket.instances.length - 1]
      act(() => {
        current?.dropWith(1006, 'abnormal')
      })
      await advance(60_000)
    }
    expect(bannerText().toLowerCase()).toContain('unavailable')
    // The first automatic attempt already fired (1s delay, well inside the
    // 60s jumps above) and is sitting pending — exactly the moment the
    // real-machine repro caught: a restart in flight, connectionLost still
    // reporting the pre-restart failure because nothing has reopened it.
    expect(runtimeMocks.restartSidecarAutomatic).toHaveBeenCalledTimes(1)
    // Deliberately: no FakeWebSocket in this describe block is ever reopened.
    // connectionLost stays exactly as stale/true as it was the instant the
    // restart below resolves — that staleness is the point of the test.
    return { resolveFirstAttempt }
  }

  it('mandated test (a): a successful automatic restart does not trigger a second one, even while connectionLost is still stale-true', async () => {
    const { resolveFirstAttempt } = await driveIntoADownEpisodeWithStaleConnectionLost()

    await act(async () => {
      resolveFirstAttempt(READY_CONFIG)
      await Promise.resolve()
      await Promise.resolve()
    })
    expect(runtimeMocks.restartSidecarAutomatic).toHaveBeenCalledTimes(1)

    // The would-be second and third rounds (#1016's real-machine livelock)
    // must never fire: no new automatic attempt, no matter how long we wait,
    // even though connectionLost never actually flipped back to false (no
    // FakeWebSocket in this test is ever reopened).
    await advance(5 * 60_000)
    expect(runtimeMocks.restartSidecarAutomatic).toHaveBeenCalledTimes(1)
  })

  it('mandated test (c): a successful automatic restart clears the banner and never re-freezes it on a stale budget-exhausted message', async () => {
    const { resolveFirstAttempt } = await driveIntoADownEpisodeWithStaleConnectionLost()

    await act(async () => {
      resolveFirstAttempt(READY_CONFIG)
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(bannerText().toLowerCase()).not.toContain('unavailable')
    expect(bannerText()).not.toContain('budget exhausted')
    expect(findButton()).toBeNull()

    // The banner must STAY cleared — it must never re-assert a state (like
    // "budget exhausted") that stopped being true the moment the restart
    // above actually succeeded.
    await advance(5 * 60_000)
    expect(bannerText().toLowerCase()).not.toContain('unavailable')
    expect(findButton()).toBeNull()
  })
})
