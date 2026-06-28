import { useEffect, useRef, useState } from 'react'
import type { EventEnvelope } from '../api/types'
import { nextBackoffMs, runEventsWsUrl, type WebSocketStatus } from '../lib/websocket'

interface RunStreamState {
  events: EventEnvelope[]
  status: WebSocketStatus
  reconnectInMs: number | null
  error: string | null
  cursor: string | null
}

export function useRunStream(runId: string | null) {
  const [state, setState] = useState<RunStreamState>({
    events: [],
    status: 'idle',
    reconnectInMs: null,
    error: null,
    cursor: null,
  })
  const queueRef = useRef<EventEnvelope[]>([])

  useEffect(() => {
    if (!runId) {
      setState({ events: [], status: 'idle', reconnectInMs: null, error: null, cursor: null })
      return undefined
    }

    let closed = false
    // Once the run terminates the backend replays its full event log on every
    // reconnect; without this guard a closed-then-reconnect loop re-appends all
    // events unboundedly (observed: a 3-phase run growing to thousands of events).
    let runEnded = false
    let socket: WebSocket | null = null
    let attempt = 0
    let reconnectTimer: number | undefined
    const seenSeqs = new Set<number>()
    const cursorRef = { current: null as string | null }
    const lastSeqRef = { current: null as number | null }

    const flushTimer = window.setInterval(() => {
      if (queueRef.current.length === 0) {
        return
      }
      const batch = queueRef.current.splice(0)
      setState((current) => ({ ...current, events: [...current.events, ...batch], cursor: cursorRef.current }))
    }, 100)

    const connect = () => {
      attempt += 1
      setState((current) => ({
        ...current,
        status: attempt === 1 ? 'connecting' : 'reconnecting',
        reconnectInMs: null,
        error: null,
      }))

      socket = new WebSocket(runEventsWsUrl(runId, cursorRef.current))
      socket.onopen = () => {
        attempt = 0
        setState((current) => ({ ...current, status: 'open', reconnectInMs: null, error: null }))
      }
      socket.onmessage = (message) => {
        try {
          const event = JSON.parse(String(message.data)) as EventEnvelope
          if (event.event_type === 'stream.error' || event.error_payload) {
            setState((current) => ({
              ...current,
              error: event.error_payload?.message || event.error_code || 'Run stream error',
            }))
            return
          }
          if (seenSeqs.has(event.seq)) {
            return
          }
          const lastSeq = lastSeqRef.current
          if (lastSeq !== null && event.seq !== lastSeq + 1) {
            setState((current) => ({
              ...current,
              error: `Run stream gap: expected seq ${lastSeq + 1}, received ${event.seq}`,
            }))
            return
          }
          seenSeqs.add(event.seq)
          lastSeqRef.current = event.seq
          cursorRef.current = event.cursor
          queueRef.current.push(event)
          if (event.event_type === 'run_ended') {
            // Terminal: stop reconnecting so the backend's replay-on-connect
            // can't re-append the whole event log.
            runEnded = true
          }
        } catch (error) {
          setState((current) => ({ ...current, error: error instanceof Error ? error.message : 'Invalid run event' }))
        }
      }
      socket.onerror = () => {
        setState((current) => ({ ...current, status: 'error', error: 'Run stream connection failed' }))
      }
      socket.onclose = () => {
        if (closed || runEnded) {
          setState((current) => ({ ...current, status: 'closed', reconnectInMs: null }))
          return
        }
        const delay = nextBackoffMs(attempt + 1)
        setState((current) => ({ ...current, status: 'reconnecting', reconnectInMs: delay }))
        reconnectTimer = window.setTimeout(connect, delay)
      }
    }

    connect()

    return () => {
      closed = true
      window.clearInterval(flushTimer)
      if (reconnectTimer) {
        window.clearTimeout(reconnectTimer)
      }
      socket?.close()
      queueRef.current = []
    }
  }, [runId])

  return state
}
