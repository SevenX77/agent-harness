import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const reactHarness = vi.hoisted(() => ({
  state: undefined as unknown,
  states: [] as unknown[],
  cleanup: undefined as undefined | (() => void),
}))

vi.mock('react', () => ({
  useEffect(effect: () => void | (() => void)) {
    reactHarness.cleanup = effect() || undefined
  },
  useRef<T>(initial: T) {
    return { current: initial }
  },
  useState<T>(initial: T) {
    reactHarness.state = initial
    reactHarness.states.push(initial)
    const setState = (next: T | ((current: T) => T)) => {
      reactHarness.state = typeof next === 'function' ? (next as (current: T) => T)(reactHarness.state as T) : next
      reactHarness.states.push(reactHarness.state)
    }
    return [reactHarness.state, setState] as const
  },
}))

import { configureApiBaseURL } from '../api/client'
import { useRunStream } from './useRunStream'

interface FakeMessageEvent {
  data: string
}

class FakeWebSocket {
  static instances: FakeWebSocket[] = []

  readonly url: string
  onopen: (() => void) | null = null
  onmessage: ((message: FakeMessageEvent) => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null

  constructor(url: string) {
    this.url = url
    FakeWebSocket.instances.push(this)
  }

  emit(payload: unknown): void {
    this.onmessage?.({ data: JSON.stringify(payload) })
  }

  close(): void {
    this.onclose?.()
  }
}

function envelope(seq: number, payload: Record<string, unknown>, extra: Record<string, unknown> = {}) {
  return {
    schema_version: 'studio.event.v1',
    stream_id: 'run:run-1',
    seq,
    cursor: `run:run-1:${seq}`,
    run_id: 'run-1',
    event_type: String(payload.event_type ?? 'phase_start'),
    timestamp: '2026-06-17T00:00:00Z',
    payload,
    ...extra,
  }
}

function state() {
  return reactHarness.state as {
    events: Array<{ seq: number; cursor: string }>
    cursor: string | null
    error: string | null
  }
}

describe('useRunStream EventEnvelope handling', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    FakeWebSocket.instances = []
    reactHarness.state = undefined
    reactHarness.states = []
    reactHarness.cleanup = undefined
    configureApiBaseURL('http://localhost:8787/api')
    vi.stubGlobal('window', {
      location: { origin: 'http://localhost:5173' },
      setInterval: globalThis.setInterval,
      clearInterval: globalThis.clearInterval,
      setTimeout: globalThis.setTimeout,
      clearTimeout: globalThis.clearTimeout,
    })
    vi.stubGlobal('WebSocket', FakeWebSocket)
  })

  afterEach(() => {
    reactHarness.cleanup?.()
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it('stores cursors, ignores duplicate seq events, and exposes a local gap error', () => {
    useRunStream('run-1')
    const socket = FakeWebSocket.instances[0]
    socket.onopen?.()

    socket.emit(envelope(1, { event_type: 'phase_start', phase_name: 'draft' }))
    socket.emit(envelope(1, { event_type: 'phase_start', phase_name: 'draft' }))
    vi.advanceTimersByTime(100)

    expect(state().events.map((event) => event.seq)).toEqual([1])
    expect(state().cursor).toBe('run:run-1:1')

    socket.emit(envelope(3, { event_type: 'phase_end', phase_name: 'draft' }))
    vi.advanceTimersByTime(100)

    expect(state().events.map((event) => event.seq)).toEqual([1])
    expect(state().error).toContain('gap')
  })

  it('reconnects with the latest cursor', () => {
    useRunStream('run-1')
    const socket = FakeWebSocket.instances[0]
    socket.onopen?.()
    socket.emit(envelope(1, { event_type: 'phase_start', phase_name: 'draft' }))
    vi.advanceTimersByTime(100)

    socket.onclose?.()
    vi.advanceTimersByTime(1000)

    expect(FakeWebSocket.instances).toHaveLength(2)
    expect(FakeWebSocket.instances[1].url).toContain('/ws/runs/run-1?cursor=run%3Arun-1%3A1')
  })

  it('surfaces stream error envelopes without appending them as trace events', () => {
    useRunStream('run-1')
    const socket = FakeWebSocket.instances[0]
    socket.onopen?.()

    socket.emit(
      envelope(
        2,
        {},
        {
          event_type: 'stream.error',
          error_code: 'stream.cursor_expired',
          error_payload: {
            error_code: 'stream.cursor_expired',
            message: 'Cursor expired',
            details: {},
            retryable: false,
          },
        },
      ),
    )
    vi.advanceTimersByTime(100)

    expect(state().events).toEqual([])
    expect(state().error).toBe('Cursor expired')
  })
})
