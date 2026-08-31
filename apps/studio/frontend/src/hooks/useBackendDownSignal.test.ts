// @vitest-environment jsdom
import { act, createElement, StrictMode, useState } from "react"
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

// Every weak signal is now confirmed against the sidecar's port before `onDown`
// fires, so each test must say what that probe finds. The default is "connection
// refused" — the plain dead-sidecar case the older tests were written against,
// which keeps their expectations meaningful.
let healthFetch: ReturnType<typeof vi.fn>

/** Connection refused — on loopback, the unambiguous "nothing is there". */
function portRefusesConnections(): void {
  healthFetch.mockRejectedValue(new TypeError("Failed to fetch"))
}

function portAnswers(status = 200): void {
  healthFetch.mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => ({ status: "ok" }),
  })
}

/** Let the pending `/health` probe settle so its verdict can reach `onDown`. */
async function settleHealthProbe(): Promise<void> {
  await act(async () => {
    await Promise.resolve()
    await Promise.resolve()
  })
}

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

/**
 * Mounts inside `<StrictMode>`, exactly as `main.tsx` does. StrictMode runs
 * mount → cleanup → mount again on the SAME instance, so any effect that only
 * CLEARS a ref on cleanup leaves it cleared for that instance's whole life.
 */
function mountUnderStrictMode(onDown: () => void): void {
  container = document.createElement("div")
  document.body.appendChild(container)
  root = createRoot(container)

  function Host(): null {
    useStudioEventStream(PERMANENT_SUBSCRIBER_CALLBACKS)
    useBackendDownSignal(true, onDown)
    return null
  }

  act(() => {
    root.render(createElement(StrictMode, null, createElement(Host)))
  })
}

beforeEach(() => {
  vi.useFakeTimers()
  FakeWebSocket.instances = []
  ;(globalThis as unknown as { WebSocket: typeof FakeWebSocket }).WebSocket = FakeWebSocket
  healthFetch = vi.fn()
  vi.stubGlobal("fetch", healthFetch)
  portRefusesConnections()
  configureApiBaseURL("http://localhost:8787/api")
  configureApiToken("token")
})

afterEach(() => {
  unmount()
  vi.useRealTimers()
  vi.unstubAllGlobals()
  ;(globalThis as unknown as { WebSocket: typeof WebSocket }).WebSocket = originalWebSocket
  configureApiToken(null)
})

describe("useBackendDownSignal", () => {
  it("fires onDown once the shared WS connection is reported lost", async () => {
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
    await settleHealthProbe()

    expect(onDown).toHaveBeenCalledTimes(1)
  })

  it("fires onDown on a single BACKEND_UNAVAILABLE_HTTP_EVENT, without waiting on the WS threshold", async () => {
    const onDown = vi.fn()
    mount(onDown)

    act(() => {
      window.dispatchEvent(new Event(BACKEND_UNAVAILABLE_HTTP_EVENT))
    })
    await settleHealthProbe()

    expect(onDown).toHaveBeenCalledTimes(1)
  })

  it("fires onDown only ONCE per episode even under repeated failures", async () => {
    const onDown = vi.fn()
    mount(onDown)

    act(() => {
      window.dispatchEvent(new Event(BACKEND_UNAVAILABLE_HTTP_EVENT))
      window.dispatchEvent(new Event(BACKEND_UNAVAILABLE_HTTP_EVENT))
      window.dispatchEvent(new Event(BACKEND_UNAVAILABLE_HTTP_EVENT))
    })
    await settleHealthProbe()

    expect(onDown).toHaveBeenCalledTimes(1)
  })

  it("fires again for a NEW episode after being disabled and re-enabled", async () => {
    const onDown = vi.fn()
    const { setEnabled } = mount(onDown)

    act(() => {
      window.dispatchEvent(new Event(BACKEND_UNAVAILABLE_HTTP_EVENT))
    })
    await settleHealthProbe()
    expect(onDown).toHaveBeenCalledTimes(1)

    // RuntimeGate disables detection while it reacts, then re-enables once the
    // sidecar is healthy again — that is a NEW episode.
    setEnabled(false)
    setEnabled(true)

    act(() => {
      window.dispatchEvent(new Event(BACKEND_UNAVAILABLE_HTTP_EVENT))
    })
    await settleHealthProbe()
    expect(onDown).toHaveBeenCalledTimes(2)
  })

  it("does not fire while disabled", async () => {
    const onDown = vi.fn()
    const { setEnabled } = mount(onDown)
    setEnabled(false)

    act(() => {
      window.dispatchEvent(new Event(BACKEND_UNAVAILABLE_HTTP_EVENT))
    })
    await settleHealthProbe()

    expect(onDown).not.toHaveBeenCalled()
  })
})

/**
 * confirm-before-you-kill — both of this hook's inputs are WEAK evidence, and
 * acting on either alone had RuntimeGate restarting healthy sidecars.
 *
 * `BACKEND_UNAVAILABLE_HTTP_EVENT` fires whenever a call got no HTTP RESPONSE.
 * "No response" is not the same fact as "no process": a 500 whose body the
 * browser discards for lacking `Access-Control-Allow-Origin` reaches axios as
 * ERR_NETWORK and is indistinguishable, from inside the interceptor, from a
 * dead port. `connectionLost` is weaker still — it is a reconnect heuristic
 * that also trips on a rotated auth token.
 *
 * `/health` is the strong evidence, and the same evidence the Rust supervisor
 * itself uses (`sidecar.rs::wait_for_health` polls
 * `http://127.0.0.1:{port}/health`). Until now no frontend code called it once.
 * Confirming there before firing costs one request on a path that only runs
 * when something already looks wrong, and the failure it prevents is severe:
 * an unnecessary restart rotates the sidecar's token and port and drops every
 * in-flight run.
 */
describe("useBackendDownSignal — confirm-before-you-kill (/health recheck)", () => {
  it("does NOT fire onDown when /health still answers ok after an HTTP failure signal", async () => {
    portAnswers()
    const onDown = vi.fn()
    mount(onDown)

    act(() => {
      window.dispatchEvent(new Event(BACKEND_UNAVAILABLE_HTTP_EVENT))
    })
    await settleHealthProbe()

    expect(healthFetch).toHaveBeenCalledTimes(1)
    expect(onDown).not.toHaveBeenCalled()
  })

  it("does NOT fire onDown when /health still answers ok after the WS connectionLost edge", async () => {
    portAnswers()
    const onDown = vi.fn()
    mount(onDown)

    act(() => {
      FakeWebSocket.instances[0].acceptOpen()
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
    await settleHealthProbe()

    expect(healthFetch).toHaveBeenCalled()
    expect(onDown).not.toHaveBeenCalled()
  })

  it("probes /health, not /api/health, and never through the axios client", async () => {
    portAnswers()
    const onDown = vi.fn()
    mount(onDown)

    act(() => {
      window.dispatchEvent(new Event(BACKEND_UNAVAILABLE_HTTP_EVENT))
    })
    await settleHealthProbe()

    // `/health` is the ONLY registered route (`app/routers/system.py:20`);
    // `/api/health` appears in the auth whitelist but has no route and 404s.
    expect(healthFetch.mock.calls[0][0]).toBe("http://localhost:8787/health")
  })

  it("a 503 is a REPLY, so it vetoes the restart instead of confirming it", async () => {
    // A process that answers 503 has just proved it is running, and "the process
    // is gone" is the only claim an auto-restart rests on. Restarting here would
    // kill a live sidecar that told us it was alive — and would disagree with the
    // Rust supervisor, whose own probe never looks past the status line.
    portAnswers(503)
    const onDown = vi.fn()
    mount(onDown)

    act(() => {
      window.dispatchEvent(new Event(BACKEND_UNAVAILABLE_HTTP_EVENT))
    })
    await settleHealthProbe()

    expect(onDown).not.toHaveBeenCalled()
  })

  it("a timeout is ambiguous, so it vetoes rather than confirming a dead process", async () => {
    // Timing out does not mean the port is closed: it is also what a live
    // sidecar looks like while its event loop runs a synchronous compile. No
    // timeout value separates the two, so the tie goes to not restarting — the
    // person still has Retry, and a delayed banner is cheaper than killing work
    // in flight.
    const abortError = new Error("The operation was aborted")
    abortError.name = "AbortError"
    healthFetch.mockRejectedValue(abortError)
    const onDown = vi.fn()
    mount(onDown)

    act(() => {
      window.dispatchEvent(new Event(BACKEND_UNAVAILABLE_HTTP_EVENT))
    })
    await settleHealthProbe()

    expect(onDown).not.toHaveBeenCalled()
  })

  it("a refused connection is the one unambiguous answer, and fires onDown once", async () => {
    portRefusesConnections()
    const onDown = vi.fn()
    mount(onDown)

    act(() => {
      window.dispatchEvent(new Event(BACKEND_UNAVAILABLE_HTTP_EVENT))
      window.dispatchEvent(new Event(BACKEND_UNAVAILABLE_HTTP_EVENT))
    })
    await settleHealthProbe()

    expect(onDown).toHaveBeenCalledTimes(1)
  })

  it("a suppressed episode is not spent: a later failure can still fire once /health stops answering", async () => {
    // The edge-trigger budget must be spent on FIRING, not on being asked. A
    // recheck that vetoes the signal leaves the episode open, otherwise one
    // early false alarm would blind detection for the rest of the episode.
    portAnswers()
    const onDown = vi.fn()
    mount(onDown)

    act(() => {
      window.dispatchEvent(new Event(BACKEND_UNAVAILABLE_HTTP_EVENT))
    })
    await settleHealthProbe()
    expect(onDown).not.toHaveBeenCalled()

    portRefusesConnections()
    act(() => {
      window.dispatchEvent(new Event(BACKEND_UNAVAILABLE_HTTP_EVENT))
    })
    await settleHealthProbe()

    expect(onDown).toHaveBeenCalledTimes(1)
  })

  it("a signal that arrives DURING a probe is re-checked, not dropped", async () => {
    // The overlap case. Probe A is a false alarm and will answer "healthy". The
    // real outage happens while it is still in flight, and its signal must not
    // be consumed by A's verdict: the WS edge that carried it is gone (the
    // baseline already advanced, and a level that stays true yields no second
    // edge), so a dropped signal here would blind detection for the rest of the
    // episode — a dead backend that never gets restarted.
    let resolveFirstProbe: ((value: unknown) => void) | undefined
    healthFetch.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveFirstProbe = resolve
        }),
    )
    const onDown = vi.fn()
    mount(onDown)

    act(() => {
      window.dispatchEvent(new Event(BACKEND_UNAVAILABLE_HTTP_EVENT))
    })
    // The real outage, while probe A is still pending.
    act(() => {
      window.dispatchEvent(new Event(BACKEND_UNAVAILABLE_HTTP_EVENT))
    })

    // Probe A says healthy — and the second probe (the default: unreachable)
    // must then run because a signal arrived while A was in flight.
    portRefusesConnections()
    resolveFirstProbe?.({ ok: true, status: 200, json: async () => ({ status: "ok" }) })
    await settleHealthProbe()

    expect(healthFetch).toHaveBeenCalledTimes(2)
    expect(onDown).toHaveBeenCalledTimes(1)
  })

  it("stops re-probing once a probe completes with no signal behind it", async () => {
    portAnswers()
    const onDown = vi.fn()
    mount(onDown)

    act(() => {
      window.dispatchEvent(new Event(BACKEND_UNAVAILABLE_HTTP_EVENT))
    })
    await settleHealthProbe()

    expect(healthFetch).toHaveBeenCalledTimes(1)
    expect(onDown).not.toHaveBeenCalled()
  })

  it("does not fire when the episode ends while the /health probe is still in flight", async () => {
    // RuntimeGate disarms the instant it reacts. A verdict that arrives after
    // that belongs to an episode that is already over.
    let resolveProbe: ((value: unknown) => void) | undefined
    healthFetch.mockReturnValue(
      new Promise((resolve) => {
        resolveProbe = resolve
      }),
    )
    const onDown = vi.fn()
    const { setEnabled } = mount(onDown)

    act(() => {
      window.dispatchEvent(new Event(BACKEND_UNAVAILABLE_HTTP_EVENT))
    })
    setEnabled(false)

    resolveProbe?.({ ok: false, status: 503, json: async () => ({}) })
    await settleHealthProbe()

    expect(onDown).not.toHaveBeenCalled()
  })

  it("a vetoed WS episode still fires after a real reconnect and a real second loss", async () => {
    // What a veto must not do is disarm the branch permanently. It does spend
    // the current edge — `connectionLost` stays true until a reconnect, and
    // React re-runs that effect only when the value changes, so nothing can
    // re-trigger on a level that never moves (the HTTP branch covers that
    // window). What it must preserve is the NEXT genuine transition.
    portAnswers()
    const onDown = vi.fn()
    mount(onDown)

    act(() => {
      FakeWebSocket.instances[0].acceptOpen()
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
    await settleHealthProbe()
    expect(onDown).not.toHaveBeenCalled()

    // A real reconnect drives connectionLost back to false...
    act(() => {
      FakeWebSocket.instances[FakeWebSocket.instances.length - 1].acceptOpen()
    })
    // ...and this time the process really is gone.
    portRefusesConnections()
    for (let i = 0; i < 3; i += 1) {
      const current = FakeWebSocket.instances[FakeWebSocket.instances.length - 1]
      act(() => {
        current.dropWith(1006, "abnormal")
      })
      act(() => {
        vi.advanceTimersByTime(60_000)
      })
    }
    await settleHealthProbe()

    expect(onDown).toHaveBeenCalledTimes(1)
  })

  it("a signal that arrives mid-probe is answered for the NEW episode after a re-arm", async () => {
    // The verdict of a probe belongs to the episode that started it, but a
    // signal that arrived while it ran is evidence for whatever episode is
    // current when it lands. Conflating the two let the pending signal be
    // discarded together with the stale verdict, blinding the new episode.
    let resolveFirstProbe: ((value: unknown) => void) | undefined
    healthFetch.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveFirstProbe = resolve
        }),
    )
    const onDown = vi.fn()
    const { setEnabled } = mount(onDown)

    act(() => {
      window.dispatchEvent(new Event(BACKEND_UNAVAILABLE_HTTP_EVENT))
    })
    // RuntimeGate closes the episode and opens a new one while the probe runs.
    setEnabled(false)
    setEnabled(true)
    // A fresh signal for the NEW episode, still while the old probe is pending.
    act(() => {
      window.dispatchEvent(new Event(BACKEND_UNAVAILABLE_HTTP_EVENT))
    })

    portRefusesConnections()
    resolveFirstProbe?.({ ok: true, status: 200, json: async () => ({ status: "ok" }) })
    await settleHealthProbe()

    expect(onDown).toHaveBeenCalledTimes(1)
  })

  it("still detects an outage under StrictMode's mount/cleanup/mount cycle", async () => {
    // `main.tsx` renders the app inside <StrictMode>. If the unmount guard were
    // only cleared on cleanup and never re-set on mount, StrictMode's
    // double-invoke would latch this instance to "unmounted" and silently
    // disable down-detection for the entire dev session.
    const onDown = vi.fn()
    mountUnderStrictMode(onDown)

    act(() => {
      window.dispatchEvent(new Event(BACKEND_UNAVAILABLE_HTTP_EVENT))
    })
    await settleHealthProbe()

    expect(onDown).toHaveBeenCalledTimes(1)
  })

  it("does not fire when the hook unmounts while the /health probe is still in flight", async () => {
    // RuntimeGate's own timer cleanup runs on unmount. A verdict landing after
    // that would schedule an auto-restart with nothing left to cancel it.
    let resolveProbe: ((value: unknown) => void) | undefined
    healthFetch.mockReturnValue(
      new Promise((resolve) => {
        resolveProbe = resolve
      }),
    )
    const onDown = vi.fn()
    mount(onDown)

    act(() => {
      window.dispatchEvent(new Event(BACKEND_UNAVAILABLE_HTTP_EVENT))
    })
    unmount()

    resolveProbe?.({ ok: false, status: 503, json: async () => ({}) })
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(onDown).not.toHaveBeenCalled()
    // `mount` again so the shared afterEach's unconditional `unmount()` has a
    // live root to tear down.
    mount(vi.fn())
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
  it("re-arming while the WS signal is still stale-true does not immediately re-fire onDown", async () => {
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
    await settleHealthProbe()
    expect(onDown).toHaveBeenCalledTimes(1)

    // RuntimeGate's episode boundary: disarm the instant it reacts, then
    // re-arm the instant a restart attempt's promise resolves — WITHOUT
    // waiting for connectionLost to have caught up first. This is the exact
    // race the coordinator's real-machine repro hit.
    setEnabled(false)
    setEnabled(true)
    await settleHealthProbe()

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
    await settleHealthProbe()

    expect(onDown).toHaveBeenCalledTimes(2)
  })
})
