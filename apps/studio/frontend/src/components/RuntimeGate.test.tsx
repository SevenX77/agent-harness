// @vitest-environment jsdom
import { act, createElement } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { renderToStaticMarkup } from 'react-dom/server'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { configureApiBaseURL, configureApiToken } from '../api/client'
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

async function mountReady(): Promise<void> {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  const mountedRoot = root

  await act(async () => {
    mountedRoot.render(createElement(RuntimeGate, null, createElement('div', null, 'app-shell-content')))
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

beforeEach(() => {
  vi.useFakeTimers()
  FakeWebSocket.instances = []
  ;(globalThis as unknown as { WebSocket: typeof FakeWebSocket }).WebSocket = FakeWebSocket
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
  ;(globalThis as unknown as { WebSocket: typeof WebSocket }).WebSocket = originalWebSocket
  configureApiToken(null)
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
