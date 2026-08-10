import { useEffect, useRef, useState } from 'react'
import { runDeltasWsUrl } from '../lib/websocket'

/**
 * What a step has produced so far, as it is producing it.
 *
 * Two channels because they are two different things: `thinking` is the model
 * working out its answer, `text` is the answer. Concatenating them would show
 * the reader a reply the model never gave.
 */
export interface StepOutput {
  text: string
  thinking: string
}

/** Live output, keyed by the step it belongs to. */
export type RunDeltas = Record<string, StepOutput>

interface DeltaFrame {
  schema_version: string
  step_id: string
  channel: 'text' | 'thinking' | string
  text: string
  restarts_step: boolean
}

const NOTHING: RunDeltas = {}

function applied(current: RunDeltas, frame: DeltaFrame): RunDeltas {
  const step = current[frame.step_id] ?? { text: '', thinking: '' }
  if (frame.restarts_step) {
    // The gateway went back for a different answer, so what is on screen
    // belongs to an attempt nobody received. Appending past it would show one
    // reply stitched from two — which is not a display bug, it is a wrong
    // answer (decision 2026-08-09 D9).
    return { ...current, [frame.step_id]: { text: '', thinking: '' } }
  }
  const channel = frame.channel === 'thinking' ? 'thinking' : 'text'
  return {
    ...current,
    [frame.step_id]: { ...step, [channel]: step[channel] + frame.text },
  }
}

/**
 * Follow one run's output as it arrives.
 *
 * A separate socket from the run's events, because the two make opposite
 * promises: events are numbered and replayed from a cursor, while these may be
 * merged or dropped under backpressure and have nothing to replay. That is also
 * why this hook never reconnects — a delta missed while disconnected is gone by
 * design, and what it spelled out arrives whole on the step's closing event over
 * the other socket. Reconnecting could only re-show text the row already has.
 */
export function useRunDeltas(skillId: string | null, runId: string | null, live: boolean): RunDeltas {
  const [deltas, setDeltas] = useState<RunDeltas>(NOTHING)
  // Frames arrive far faster than a reader can read, so they are folded here
  // and handed to React on a timer. Setting state per frame would re-render the
  // whole trace list once per token.
  const pendingRef = useRef<DeltaFrame[]>([])

  useEffect(() => {
    if (!skillId || !runId || !live) {
      setDeltas(NOTHING)
      return undefined
    }
    setDeltas(NOTHING)

    const socket = new WebSocket(runDeltasWsUrl(skillId, runId))
    socket.onmessage = (message) => {
      try {
        const frame = JSON.parse(String(message.data)) as DeltaFrame
        if (typeof frame.step_id === 'string' && frame.step_id !== '') {
          pendingRef.current.push(frame)
        }
      } catch {
        // A frame this build cannot read is one piece of a preview whose
        // authoritative version arrives on the closing event. Dropping it is
        // what the contract already permits; failing the panel over it is not.
      }
    }

    const flush = window.setInterval(() => {
      if (pendingRef.current.length === 0) {
        return
      }
      const batch = pendingRef.current.splice(0)
      setDeltas((current) => batch.reduce(applied, current))
    }, 60)

    return () => {
      window.clearInterval(flush)
      pendingRef.current = []
      socket.close()
    }
  }, [skillId, runId, live])

  return deltas
}

export const __testing = { applied }
