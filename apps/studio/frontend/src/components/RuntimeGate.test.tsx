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

// The two answers `restartSidecarAutomatic` can give without failing: a sidecar
// was replaced, or the supervisor confirmed the one already there was serving
// and refused to replace it (`AutoRestartOutcome::Declined`).
const RESTARTED = { outcome: 'restarted' as const, config: READY_CONFIG }
const DECLINED = { outcome: 'declined' as const, config: READY_CONFIG }

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

// RuntimeGate must never reach the network itself. It briefly did — a `/health`
// probe in front of the automatic restart — and that could not be made correct
// from here: the check and the kill sat on opposite sides of the Tauri command
// boundary, and `/health` names no instance, so the verdict could not be tied
// to the sidecar being killed. The confirmation now lives in the supervisor.
// This spy is what fails loudly if a probe is ever reintroduced at this layer.
let networkFetch: ReturnType<typeof vi.fn>

beforeEach(() => {
  vi.useFakeTimers()
  FakeWebSocket.instances = []
  ;(globalThis as unknown as { WebSocket: typeof FakeWebSocket }).WebSocket = FakeWebSocket
  networkFetch = vi.fn(() => Promise.reject(new TypeError('RuntimeGate must not fetch')))
  vi.stubGlobal('fetch', networkFetch)
  configureApiBaseURL('http://127.0.0.1:8787/api')
  configureApiToken('token')
  runtimeMocks.initializeRuntimeConfig.mockReset().mockResolvedValue(READY_CONFIG)
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
 * confirm-before-you-kill — the automatic restart is the destructive act, and
 * both signals that reach RuntimeGate are too weak to authorise it on their own.
 * `BACKEND_UNAVAILABLE_HTTP_EVENT` means "a call got no HTTP RESPONSE", which is
 * not "the process is gone" — a 500 the browser discards for missing
 * `Access-Control-Allow-Origin` reaches axios as ERR_NETWORK and looks exactly
 * the same from inside the interceptor. Acting on that restarted sidecars that
 * were serving fine, rotating their token and port and dropping in-flight runs.
 *
 * So RuntimeGate ASKS FOR a restart; it does not decide one. The confirmation
 * lives in the supervisor that owns the process, under the lock that serializes
 * restarts (`apps/studio/tauri/src/sidecar.rs`), because only there are the
 * check and the kill one step about one instance. What this file pins is
 * RuntimeGate's half of that contract: it probes nothing itself, and it handles
 * a refusal as the success it is.
 *
 * The confirmation deliberately does NOT gate the banner. Banner and Retry
 * appear only once RuntimeGate leaves 'ready', so confirming before reporting
 * would hide both and leave a broken app with no message and no affordance —
 * worse than a spurious restart. Detection stays as sensitive as it was; only
 * the irreversible half asks for more evidence.
 */
describe('RuntimeGate — confirm-before-you-kill (the supervisor decides, this asks)', () => {
  it('never probes the sidecar itself: the confirmation is not this layer\'s job', async () => {
    runtimeMocks.restartSidecarAutomatic.mockResolvedValue(RESTARTED)
    await mountReady()

    await act(async () => {
      window.dispatchEvent(new Event('studio-backend-http-unavailable'))
    })
    await advance(AUTO_RESTART_DELAYS_MS[0] + 1)

    expect(runtimeMocks.restartSidecarAutomatic).toHaveBeenCalledTimes(1)
    expect(networkFetch).not.toHaveBeenCalled()
  })

  it('reports the outage immediately: nothing is awaited before the banner', async () => {
    runtimeMocks.restartSidecarAutomatic.mockResolvedValue(RESTARTED)
    await mountReady()

    await act(async () => {
      window.dispatchEvent(new Event('studio-backend-http-unavailable'))
    })

    expect(bannerText().toLowerCase()).toContain('unavailable')
    expect(findButton()).not.toBeNull()
    expect(runtimeMocks.restartSidecarAutomatic).not.toHaveBeenCalled()
  })

  it('treats a declined restart as recovery: banner clears, nothing rescheduled', async () => {
    runtimeMocks.restartSidecarAutomatic.mockResolvedValue(DECLINED)
    await mountReady()

    await act(async () => {
      window.dispatchEvent(new Event('studio-backend-http-unavailable'))
    })
    await advance(AUTO_RESTART_DELAYS_MS[0] + 1)

    // The refusal ended the episode. Far past every remaining delay in the
    // schedule, nothing fires again: a new cycle needs a new outage, not the
    // passage of time. A decline handled as a FAILURE would show here as a
    // second and third ask on the backoff.
    await advance(120_000)

    expect(runtimeMocks.restartSidecarAutomatic).toHaveBeenCalledTimes(1)
    expect(bannerText().toLowerCase()).not.toContain('unavailable')
    expect(findButton()).toBeNull()
  })

  /**
   * Declining must not be a dead end. Detection is armed by
   * `useBackendDownSignal(status === 'ready', …)`, so a branch that left
   * `status` on 'error' would also leave the app unable to notice the NEXT
   * outage — and the only way out would be the destructive Retry this whole
   * change exists to avoid.
   */
  it('re-arms detection after a decline: a second outage is still noticed', async () => {
    runtimeMocks.restartSidecarAutomatic.mockResolvedValueOnce(DECLINED)
    await mountReady()

    await act(async () => {
      window.dispatchEvent(new Event('studio-backend-http-unavailable'))
    })
    await advance(AUTO_RESTART_DELAYS_MS[0] + 1)
    expect(bannerText().toLowerCase()).not.toContain('unavailable')

    // The sidecar dies for real this time, and the supervisor confirms it.
    runtimeMocks.restartSidecarAutomatic.mockResolvedValue(RESTARTED)
    await act(async () => {
      window.dispatchEvent(new Event('studio-backend-http-unavailable'))
    })
    expect(bannerText().toLowerCase()).toContain('unavailable')
    await advance(AUTO_RESTART_DELAYS_MS[0] + 1)

    expect(runtimeMocks.restartSidecarAutomatic).toHaveBeenCalledTimes(2)
    expect(bannerText().toLowerCase()).not.toContain('unavailable')
  })

  /**
   * A restart request has a duration, and anything with a duration can be
   * overtaken. `handleRetry` cancels the pending timer, but a request already
   * in flight is not a timer — its answer describes the instance it was sent
   * about, which a manual Retry has since replaced. The supervisor makes that
   * answer harmless (it re-confirms under the lock and would decline); this
   * side must still not report a superseded episode's result as the current
   * state.
   */
  it('drops an answer that arrives after a manual Retry already restarted', async () => {
    let answerTheRequest: ((result: typeof RESTARTED) => void) | undefined
    runtimeMocks.restartSidecarAutomatic.mockReturnValue(
      new Promise((resolve) => {
        answerTheRequest = resolve
      }),
    )
    await mountReady()

    await act(async () => {
      window.dispatchEvent(new Event('studio-backend-http-unavailable'))
    })
    // The scheduled attempt fired and its request is in flight, unanswered.
    await advance(AUTO_RESTART_DELAYS_MS[0] + 1)
    expect(runtimeMocks.restartSidecarAutomatic).toHaveBeenCalledTimes(1)

    // The person does not wait for it. Retry restarts the sidecar itself.
    clickRetry()
    await flush()
    expect(runtimeMocks.restartSidecar).toHaveBeenCalledTimes(1)

    // Only now does the automatic attempt answer. It must change nothing: no
    // second ask, and no revived recovery loop.
    await act(async () => {
      answerTheRequest?.(RESTARTED)
      await Promise.resolve()
      await Promise.resolve()
    })
    await advance(120_000)

    expect(runtimeMocks.restartSidecarAutomatic).toHaveBeenCalledTimes(1)
    expect(bannerText().toLowerCase()).not.toContain('unavailable')
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
      .mockResolvedValueOnce(RESTARTED)
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
    resolveFirstAttempt: (value: typeof RESTARTED) => void
  }> {
    let resolveFirstAttempt: (value: typeof RESTARTED) => void = () => {}
    const firstAttempt = new Promise<typeof RESTARTED>((resolve) => {
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
      resolveFirstAttempt(RESTARTED)
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
      resolveFirstAttempt(RESTARTED)
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
