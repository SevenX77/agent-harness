import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import type { Mock } from 'vitest'
import type { CallbackEvent } from '../api/types'
import type { WebSocketStatus } from '../lib/websocket'

interface RunStreamState {
  events: CallbackEvent[]
  status: WebSocketStatus
  reconnectInMs: number | null
  error: string | null
}

// Define mock refs to capture react hook states
let stateVal: RunStreamState | null = null
let stateSetter: Mock | null = null
let effectFn: (() => (void | (() => void))) | null = null
let effectDeps: unknown[] | null = null
const refVal: { current: unknown[] } = { current: [] }

// Mock React before importing the hook
vi.mock('react', () => ({
  useState: (initial: RunStreamState) => {
    stateVal = initial
    stateSetter = vi.fn((updater) => {
      if (typeof updater === 'function') {
        stateVal = updater(stateVal as RunStreamState)
      } else {
        stateVal = updater
      }
    })
    return [stateVal, stateSetter]
  },
  useRef: (initial: unknown[]) => {
    refVal.current = initial
    return refVal
  },
  useEffect: (fn: () => (void | (() => void)), deps: unknown[]) => {
    effectFn = fn
    effectDeps = deps
  },
}))

// Mock websocket helpers
vi.mock('../lib/websocket', () => ({
  runEventsWsUrl: (runId: string) => `ws://127.0.0.1:8787/ws/runs/${runId}/events`,
  nextBackoffMs: () => 100,
}))

// Import the hook now that React is mocked
import { useRunStream } from './useRunStream'

// Mock socket structure that holds callbacks
interface MockSocketContainer {
  url?: string
  close: Mock
  onopen: (() => void) | null
  onmessage: ((event: MessageEvent) => void) | null
  onerror: (() => void) | null
  onclose: (() => void) | null
}

describe('useRunStream WS-3 Hook contracts (Regression Lock)', () => {
  let mockSocket: MockSocketContainer
  let wsConstructorSpy: Mock
  let intervalCallback: (() => void) | null = null
  const intervalId = 999

  beforeEach(() => {
    vi.stubGlobal('window', {
      setInterval: vi.fn((cb: () => void) => {
        intervalCallback = cb
        return intervalId
      }),
      clearInterval: vi.fn(),
      setTimeout: vi.fn(),
      clearTimeout: vi.fn(),
    })

    mockSocket = {
      close: vi.fn(),
      onopen: null,
      onmessage: null,
      onerror: null,
      onclose: null,
    }

    class MockWebSocket {
      url: string
      constructor(url: string) {
        this.url = url
        mockSocket.url = url
        wsConstructorSpy(url)
      }
      close() {
        mockSocket.close()
      }
      set onopen(val: (() => void) | null) { mockSocket.onopen = val }
      get onopen() { return mockSocket.onopen }
      set onmessage(val: ((event: MessageEvent) => void) | null) { mockSocket.onmessage = val }
      get onmessage() { return mockSocket.onmessage }
      set onerror(val: (() => void) | null) { mockSocket.onerror = val }
      get onerror() { return mockSocket.onerror }
      set onclose(val: (() => void) | null) { mockSocket.onclose = val }
      get onclose() { return mockSocket.onclose }
    }

    wsConstructorSpy = vi.fn()
    vi.stubGlobal('WebSocket', MockWebSocket)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    stateVal = null
    stateSetter = null
    effectFn = null
    effectDeps = null
    refVal.current = []
  })

  it('initializes in idle state when runId is null', () => {
    useRunStream(null)
    expect(effectFn).toBeDefined()
    expect(effectDeps).toEqual([null])

    // Trigger effect
    const cleanup = effectFn ? effectFn() : undefined
    expect(cleanup).toBeUndefined()
    expect(stateVal).toBeDefined()
    expect(stateVal?.status).toBe('idle')
    expect(stateVal?.events).toEqual([])
  })

  it('connects to WS and appends events through the flush queue', () => {
    useRunStream('run-ws-123')
    
    // Trigger effect
    const cleanup = effectFn ? effectFn() : undefined
    expect(wsConstructorSpy).toHaveBeenCalledWith('ws://127.0.0.1:8787/ws/runs/run-ws-123/events')
    expect(stateSetter).toHaveBeenCalled()

    // Trigger websocket onmessage
    const mockMsg: CallbackEvent = {
      schema_version: '1.0',
      event_type: 'phase_start',
      phase_name: 'draft',
      event_id: 'evt-1',
      parent_id: null,
      timestamp: '2026-06-08T12:00:00Z',
    }
    if (mockSocket.onmessage) {
      mockSocket.onmessage({ data: JSON.stringify(mockMsg) } as MessageEvent)
    }

    // Simulate setInterval flush triggering
    expect(intervalCallback).toBeDefined()
    if (intervalCallback) intervalCallback()

    // Expect the state to contain the event
    expect(stateVal?.events).toContainEqual(mockMsg)

    // Verify cleanup closes the socket and clears interval
    if (cleanup) cleanup()
    expect(mockSocket.close).toHaveBeenCalled()
    expect(window.clearInterval).toHaveBeenCalledWith(intervalId)
  })

  it('sets error state when receiving malformed JSON', () => {
    useRunStream('run-ws-123')
    if (effectFn) effectFn()

    // Send malformed JSON message
    if (mockSocket.onmessage) {
      mockSocket.onmessage({ data: '{badjson' } as MessageEvent)
    }

    // Expect the hook state to reflect error
    expect(stateVal?.error).toContain('JSON')
  })

  it('closes the old socket when runId changes', () => {
    useRunStream('run-first')
    const cleanup1 = effectFn ? effectFn() : undefined

    // Change runId
    useRunStream('run-second')
    
    // Simulate cleanup1 call from React on change
    if (cleanup1) cleanup1()
    
    expect(mockSocket.close).toHaveBeenCalled()
  })
})
