// @vitest-environment jsdom
import { act, createElement, useState } from "react"
import { createRoot, type Root } from "react-dom/client"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { configureApiBaseURL, configureApiToken, BACKEND_UNAVAILABLE_HTTP_EVENT } from "../api/client"
import { useBackendDownSignal } from "./useBackendDownSignal"
import { useStudioEventStream } from "./useStudioEventStream"

// Mirrors Workspace.tsx's own, permanently-enabled `useStudioEventStream`
// subscriber. Production always has at least one of these alive for the
// app's whole lifetime, which means the shared hub's `subscribers.size` never
// actually reaches zero while RuntimeGate's OWN subscription toggles off and
// back on — so `resetHubState()` never runs and stale hub state (in
// particular `hubConnectionLost`) survives across that toggle. A test with
// only `useBackendDownSignal` subscribed would hit zero subscribers on
// disable and get a full, masking reset — which is why the always-on
// permanent-holder test below needs this second subscriber to reproduce the
// real-machine race at all.
const PERMANENT_SUBSCRIBER_CALLBACKS = {
  onRegistryChanged: (): void => {},
  onRolesChanged: (): void => {},
}

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const toastMock = vi.hoisted(() => ({
  error: vi.fn(),
  success: vi.fn(),
  warning: vi.fn(),
  info: vi.fn(),
}))

vi.mock("sonner", () => ({
  toast: toastMock,
}))

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
    this.onopen?.(new Event("open"))
  }

  dropWith(code: number, reason = ""): void {
    this.readyState = FakeWebSocket.CLOSED
    this.onclose?.({ code, reason, wasClean: false })
  }

  close(): void {
    this.readyState = FakeWebSocket.CLOSED
  }
}

let container: HTMLDivElement
let root: Root
const originalWebSocket = globalThis.WebSocket

function mount(onDown: () => void): { setEnabled: (value: boolean) => void } {
  container = document.createElement("div")
  document.body.appendChild(container)
  root = createRoot(container)

  let externalSetEnabled: (value: boolean) => void = () => {}

  function Host(): null {
    const [enabled, setEnabled] = useState(true)
    externalSetEnabled = setEnabled
    // Always-on, mirroring Workspace.tsx — see the comment on
    // PERMANENT_SUBSCRIBER_CALLBACKS above for why this matters.
    useStudioEventStream(PERMANENT_SUBSCRIBER_CALLBACKS)
    useBackendDownSignal(enabled, onDown)
    return null
  }

  act(() => {
    root.render(createElement(Host))
  })

  return { setEnabled: (value) => act(() => externalSetEnabled(value)) }
}

function unmount(): void {
  act(() => {
    root.unmount()
  })
  container.remove()
}

beforeEach(() => {
  vi.useFakeTimers()
  FakeWebSocket.instances = []
  ;(globalThis as unknown as { WebSocket: typeof FakeWebSocket }).WebSocket = FakeWebSocket
  configureApiBaseURL("http://localhost:8787/api")
  configureApiToken("token")
})

afterEach(() => {
  unmount()
  vi.useRealTimers()
  ;(globalThis as unknown as { WebSocket: typeof WebSocket }).WebSocket = originalWebSocket
  configureApiToken(null)
})

describe("useBackendDownSignal", () => {
  it("fires onDown once the shared WS connection is reported lost", () => {
    const onDown = vi.fn()
    mount(onDown)

    act(() => {
      FakeWebSocket.instances[0].acceptOpen()
    })
    expect(onDown).not.toHaveBeenCalled()

    // Drop repeatedly with a non-auth code until the WS hub's own
    // flicker-avoiding threshold (3 consecutive failures) is crossed.
    for (let i = 0; i < 3; i += 1) {
      const current = FakeWebSocket.instances[FakeWebSocket.instances.length - 1]
      act(() => {
        current.dropWith(1006, "abnormal")
      })
      act(() => {
        vi.advanceTimersByTime(60_000)
      })
    }

    expect(onDown).toHaveBeenCalledTimes(1)
  })

  it("fires onDown immediately on a single BACKEND_UNAVAILABLE_HTTP_EVENT, without waiting on the WS threshold", () => {
    const onDown = vi.fn()
    mount(onDown)

    act(() => {
      window.dispatchEvent(new Event(BACKEND_UNAVAILABLE_HTTP_EVENT))
    })

    expect(onDown).toHaveBeenCalledTimes(1)
  })

  it("fires onDown only ONCE per episode even under repeated failures", () => {
    const onDown = vi.fn()
    mount(onDown)

    act(() => {
      window.dispatchEvent(new Event(BACKEND_UNAVAILABLE_HTTP_EVENT))
      window.dispatchEvent(new Event(BACKEND_UNAVAILABLE_HTTP_EVENT))
      window.dispatchEvent(new Event(BACKEND_UNAVAILABLE_HTTP_EVENT))
    })

    expect(onDown).toHaveBeenCalledTimes(1)
  })

  it("fires again for a NEW episode after being disabled and re-enabled", () => {
    const onDown = vi.fn()
    const { setEnabled } = mount(onDown)

    act(() => {
      window.dispatchEvent(new Event(BACKEND_UNAVAILABLE_HTTP_EVENT))
    })
    expect(onDown).toHaveBeenCalledTimes(1)

    // RuntimeGate disables detection while it reacts, then re-enables once the
    // sidecar is healthy again — that is a NEW episode.
    setEnabled(false)
    setEnabled(true)

    act(() => {
      window.dispatchEvent(new Event(BACKEND_UNAVAILABLE_HTTP_EVENT))
    })
    expect(onDown).toHaveBeenCalledTimes(2)
  })

  it("does not fire while disabled", () => {
    const onDown = vi.fn()
    const { setEnabled } = mount(onDown)
    setEnabled(false)

    act(() => {
      window.dispatchEvent(new Event(BACKEND_UNAVAILABLE_HTTP_EVENT))
    })

    expect(onDown).not.toHaveBeenCalled()
  })
})

/**
 * recovery-stops-when-it-succeeds (2026-08-24): real-machine verification of
 * the dead-sidecar-says-so fix found the bounded auto-restart loop livelocked.
 * Root cause traced to THIS hook: re-arming (`enabled` false → true, which
 * RuntimeGate does the instant a restart attempt's promise resolves) used to
 * tear down and rebuild the underlying `useStudioEventStream` subscription,
 * and a brand-new subscription snapshots WHATEVER `connectionLost` reads on
 * the shared hub at that exact instant. A sidecar restart rotates the auth
 * token, so the hub's own reconnect can still be racing against the OLD
 * token in that same instant — re-arming read `connectionLost === true` (the
 * OLD token's rejection, not evidence of a NEW failure) and fired `onDown`
 * again immediately, restarting a sidecar that had, moments ago, come back up
 * clean. Three such rounds exhausted the Rust-side budget while the sidecar
 * sat healthy the whole time.
 *
 * The fix: the WS subscription is never torn down by `armed` toggling
 * (`useBackendDownSignal` now subscribes for its whole mounted lifetime), and
 * firing is edge-triggered off an OBSERVED false→true transition of
 * `connectionLost`, not off its level. Whatever `connectionLost` reads at the
 * exact moment we re-arm becomes the new baseline — "already known,"
 * never "new" — so a lagging reconnect can no longer be mistaken for a fresh
 * failure. A connection that genuinely goes down again afterward still
 * produces a real transition and still fires.
 */
describe("useBackendDownSignal — recovery-stops-when-it-succeeds (edge-triggered re-arm)", () => {
  it("re-arming while the WS signal is still stale-true does not immediately re-fire onDown", () => {
    const onDown = vi.fn()
    const { setEnabled } = mount(onDown)

    act(() => {
      FakeWebSocket.instances[0].acceptOpen()
    })

    // Drive the hub's own `connectionLost` to true, exactly like the first
    // test in this file — this is the "old token's evidence" standing in the
    // hub's shared state at the moment RuntimeGate would call markReady().
    for (let i = 0; i < 3; i += 1) {
      const current = FakeWebSocket.instances[FakeWebSocket.instances.length - 1]
      act(() => {
        current.dropWith(1006, "abnormal")
      })
      act(() => {
        vi.advanceTimersByTime(60_000)
      })
    }
    expect(onDown).toHaveBeenCalledTimes(1)

    // RuntimeGate's episode boundary: disarm the instant it reacts, then
    // re-arm the instant a restart attempt's promise resolves — WITHOUT
    // waiting for connectionLost to have caught up first. This is the exact
    // race the coordinator's real-machine repro hit.
    setEnabled(false)
    setEnabled(true)

    // No second onDown call: the stale `connectionLost === true` reading at
    // the moment of re-arm must not be mistaken for a brand-new failure.
    expect(onDown).toHaveBeenCalledTimes(1)

    // Detection must not be permanently blinded, though: let the connection
    // actually recover (mirroring the real reconnect that follows a
    // successful restart), then let it genuinely go down again — THIS is a
    // real post-rearm transition and must fire.
    act(() => {
      FakeWebSocket.instances[FakeWebSocket.instances.length - 1].acceptOpen()
    })
    for (let i = 0; i < 3; i += 1) {
      const current = FakeWebSocket.instances[FakeWebSocket.instances.length - 1]
      act(() => {
        current.dropWith(1006, "abnormal")
      })
      act(() => {
        vi.advanceTimersByTime(60_000)
      })
    }

    expect(onDown).toHaveBeenCalledTimes(2)
  })
})
