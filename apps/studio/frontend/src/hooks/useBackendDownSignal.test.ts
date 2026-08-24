// @vitest-environment jsdom
import { act, createElement, useState } from "react"
import { createRoot, type Root } from "react-dom/client"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { configureApiBaseURL, configureApiToken, BACKEND_UNAVAILABLE_HTTP_EVENT } from "../api/client"
import { useBackendDownSignal } from "./useBackendDownSignal"

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
