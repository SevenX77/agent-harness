// @vitest-environment jsdom
import { act, createElement } from "react"
import { createRoot, type Root } from "react-dom/client"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

// R-F13: the hook under test reads `currentApiToken` via wsUrl() at every
// reconnect. We verify token freshness by mutating the api/client module-level
// state between reconnect attempts and asserting the new WebSocket URL reflects
// the latest token, not a cached one.
import { configureApiBaseURL, configureApiToken } from "../api/client"
import { useStudioEventStream } from "./useStudioEventStream"
import { WS_AUTH_FAILURE_GIVEUP_THRESHOLD, WS_AUTH_REJECTED_CLOSE_CODE } from "./event-stream-backoff"

// React 19's act() warns unless the environment opts in.
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

// Minimal CloseEvent-ish payload — jsdom CloseEvent is fine but spelling out the
// `code` field keeps the test readable and decoupled from the polyfill.
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

  /** Simulate the sidecar accepting the auth handshake. */
  acceptOpen(): void {
    this.readyState = FakeWebSocket.OPEN
    this.onopen?.(new Event("open"))
  }

  /** Simulate the sidecar dropping with a specific close code. */
  dropWith(code: number, reason = ""): void {
    this.readyState = FakeWebSocket.CLOSED
    this.onclose?.({ code, reason, wasClean: false })
  }

  receiveJson(payload: unknown): void {
    this.onmessage?.(new MessageEvent("message", { data: JSON.stringify(payload) }))
  }

  close(): void {
    this.readyState = FakeWebSocket.CLOSED
  }
}

const noopCallbacks = {
  onRegistryChanged: vi.fn(),
  onRolesChanged: vi.fn(),
}

let container: HTMLDivElement
let root: Root
const originalWebSocket = globalThis.WebSocket

function mountHook(): void {
  container = document.createElement("div")
  document.body.appendChild(container)
  root = createRoot(container)

  function HookHost(): null {
    useStudioEventStream(noopCallbacks)
    return null
  }
  act(() => {
    root.render(createElement(HookHost))
  })
}

function unmountHook(): void {
  act(() => {
    root.unmount()
  })
  container.remove()
}

beforeEach(() => {
  vi.useFakeTimers()
  FakeWebSocket.instances = []
  toastMock.error.mockClear()
  toastMock.success.mockClear()
  toastMock.warning.mockClear()
  toastMock.info.mockClear()
  noopCallbacks.onRegistryChanged.mockClear()
  noopCallbacks.onRolesChanged.mockClear()
  ;(globalThis as unknown as { WebSocket: typeof FakeWebSocket }).WebSocket = FakeWebSocket
  configureApiBaseURL("http://localhost:8787/api")
  configureApiToken("token-initial")
})

afterEach(() => {
  unmountHook()
  vi.useRealTimers()
  ;(globalThis as unknown as { WebSocket: typeof WebSocket }).WebSocket = originalWebSocket
  configureApiToken(null)
})

describe("useStudioEventStream — R-F13 token refresh on reconnect", () => {
  it("does not dispatch data refresh callbacks on websocket open or reconnect without a change event", () => {
    mountHook()

    act(() => {
      FakeWebSocket.instances[0].acceptOpen()
    })

    expect(noopCallbacks.onRegistryChanged).not.toHaveBeenCalled()
    expect(noopCallbacks.onRolesChanged).not.toHaveBeenCalled()

    act(() => {
      FakeWebSocket.instances[0].dropWith(1006)
    })
    act(() => {
      vi.advanceTimersByTime(60_000)
    })
    const reconnected = FakeWebSocket.instances[FakeWebSocket.instances.length - 1]
    act(() => {
      reconnected.acceptOpen()
    })

    expect(noopCallbacks.onRegistryChanged).not.toHaveBeenCalled()
    expect(noopCallbacks.onRolesChanged).not.toHaveBeenCalled()
  })

  it("rebuilds the WebSocket URL with the latest token on every reconnect", () => {
    mountHook()

    // First connect uses the token that was current at mount.
    expect(FakeWebSocket.instances).toHaveLength(1)
    expect(FakeWebSocket.instances[0].url).toContain("token=token-initial")

    // Sidecar drops the socket with a non-auth code (transient transport blip).
    act(() => {
      FakeWebSocket.instances[0].dropWith(1006)
    })

    // While the hook is waiting on backoff, a sidecar restart rotates the
    // token via configureApiToken — exactly what `sidecar-restarted` does.
    configureApiToken("token-rotated")

    // Advance past the backoff delay; the next connect must use the rotated
    // token, NOT a cached value from the initial mount.
    act(() => {
      vi.advanceTimersByTime(60_000)
    })

    expect(FakeWebSocket.instances.length).toBeGreaterThanOrEqual(2)
    const latest = FakeWebSocket.instances[FakeWebSocket.instances.length - 1]
    expect(latest.url).toContain("token=token-rotated")
    expect(latest.url).not.toContain("token=token-initial")
  })
})

describe("useStudioEventStream — LLM probe progress", () => {
  it("dispatches active model atoms from llm_probe_active events", () => {
    const onLlmProbeActive = vi.fn()
    container = document.createElement("div")
    document.body.appendChild(container)
    root = createRoot(container)

    function HookHost(): null {
      useStudioEventStream({ ...noopCallbacks, onLlmProbeActive })
      return null
    }

    act(() => {
      root.render(createElement(HookHost))
    })
    act(() => {
      FakeWebSocket.instances[0].acceptOpen()
      FakeWebSocket.instances[0].receiveJson({
        type: "llm_probe_active",
        endpoint_id: "wavespeed-openai",
        active_model_ids: ["anthropic/claude-opus-4.8", 123, ""],
      })
    })

    expect(onLlmProbeActive).toHaveBeenCalledWith({
      endpointId: "wavespeed-openai",
      activeModelIds: ["anthropic/claude-opus-4.8"],
    })
  })
})

describe("useStudioEventStream — R-F13 give-up after 5 consecutive 4401 closes", () => {
  it("stops reconnecting and toasts after the threshold of consecutive auth rejections", () => {
    mountHook()

    // Drive `WS_AUTH_FAILURE_GIVEUP_THRESHOLD` consecutive 4401 closes,
    // each separated by enough simulated time for the backoff timer to fire.
    for (let i = 0; i < WS_AUTH_FAILURE_GIVEUP_THRESHOLD; i += 1) {
      const current = FakeWebSocket.instances[FakeWebSocket.instances.length - 1]
      act(() => {
        current.dropWith(WS_AUTH_REJECTED_CLOSE_CODE, "Unauthorized")
      })
      // Advance past the worst-case jittered backoff (cap is 30s) so the next
      // reconnect attempt fires (or, at the final iteration, would fire if the
      // hook hadn't given up — we assert below that it didn't).
      act(() => {
        vi.advanceTimersByTime(60_000)
      })
    }

    // After the Nth 4401 the hook must stop scheduling new connects: the count
    // of WebSocket constructions is bounded by the threshold itself (one open
    // per failure round, with no new socket after give-up).
    expect(FakeWebSocket.instances.length).toBe(WS_AUTH_FAILURE_GIVEUP_THRESHOLD)
    expect(toastMock.error).toHaveBeenCalledTimes(1)
    expect(toastMock.error).toHaveBeenCalledWith("与 sidecar 连接已断开，请重启 Studio")
  })

  it("does NOT count non-4401 transport drops toward the give-up threshold", () => {
    mountHook()

    // Hammer the hook with non-auth drops; the hook must keep reconnecting
    // indefinitely without ever toasting (these are normal transport blips).
    for (let i = 0; i < WS_AUTH_FAILURE_GIVEUP_THRESHOLD + 3; i += 1) {
      const current = FakeWebSocket.instances[FakeWebSocket.instances.length - 1]
      act(() => {
        current.dropWith(1006, "abnormal")
      })
      act(() => {
        vi.advanceTimersByTime(60_000)
      })
    }

    expect(toastMock.error).not.toHaveBeenCalled()
    // Each iteration scheduled exactly one reconnect → one new socket each round
    // (plus the initial mount socket).
    expect(FakeWebSocket.instances.length).toBe(WS_AUTH_FAILURE_GIVEUP_THRESHOLD + 4)
  })

  it("resets the auth-failure counter on a successful open between 4401s", () => {
    mountHook()

    // Three 4401 closes, then a successful open, then three more 4401s.
    // Neither half of the run alone should hit the give-up threshold, and the
    // successful open in the middle MUST clear the counter.
    for (let i = 0; i < 3; i += 1) {
      const current = FakeWebSocket.instances[FakeWebSocket.instances.length - 1]
      act(() => {
        current.dropWith(WS_AUTH_REJECTED_CLOSE_CODE, "Unauthorized")
      })
      act(() => {
        vi.advanceTimersByTime(60_000)
      })
    }

    // A reconnect attempt succeeds (e.g. user rotated token in time).
    const reconnected = FakeWebSocket.instances[FakeWebSocket.instances.length - 1]
    act(() => {
      reconnected.acceptOpen()
    })

    // Now three more 4401s — without the counter reset on open this would
    // total 6 and trip the threshold. With the reset, we stay under it.
    for (let i = 0; i < 3; i += 1) {
      const current = FakeWebSocket.instances[FakeWebSocket.instances.length - 1]
      act(() => {
        current.dropWith(WS_AUTH_REJECTED_CLOSE_CODE, "Unauthorized")
      })
      act(() => {
        vi.advanceTimersByTime(60_000)
      })
    }

    expect(toastMock.error).not.toHaveBeenCalled()
  })
})
