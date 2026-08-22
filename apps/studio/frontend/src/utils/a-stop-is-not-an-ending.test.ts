/**
 * `run_ended` is fired when the engine returns, which a stopped run also does.
 *
 * The event has said which of the three it was since it was written —
 * `RunEndedEvent.status` is `completed | crashed | interrupted` — but the two
 * readers that decide "is this run over" never looked at it. So a run stopped
 * at a breakpoint was read as finished: the stream stopped reconnecting, and
 * the copilot bar offered to analyse a run that had not run.
 *
 * Design: run-execution/mvp1-alignment.md F10 + RUN_EXECUTION-16.
 */

import { describe, expect, it } from 'vitest'
import type { EventEnvelope } from '@/api/types'
import { endsTheRun } from './run-status-projection'

function envelope(payload: Record<string, unknown>): EventEnvelope {
  return {
    schema_version: 'studio.event.v1',
    run_id: 'run-1',
    seq: 1,
    event_type: String(payload.event_type ?? ''),
    payload,
  } as unknown as EventEnvelope
}

describe('endsTheRun', () => {
  it('says no to a run that stopped and can be continued', () => {
    expect(endsTheRun(envelope({ event_type: 'run_ended', status: 'interrupted' }))).toBe(false)
  })

  it('says yes to a run that reached its outputs', () => {
    expect(endsTheRun(envelope({ event_type: 'run_ended', status: 'completed' }))).toBe(true)
  })

  it('says yes to a run that died', () => {
    expect(endsTheRun(envelope({ event_type: 'run_ended', status: 'crashed' }))).toBe(true)
  })

  it('says yes to an ending that does not say how it ended', () => {
    // The old default, kept deliberately: mistaking a stop for an ending
    // freezes the canvas, and mistaking an ending for a stop leaves a socket
    // reconnecting and replaying the whole log forever. An unlabelled ending
    // is far likelier to be an old completed run than a stop, which has said
    // `interrupted` since the field existed.
    expect(endsTheRun(envelope({ event_type: 'run_ended' }))).toBe(true)
  })

  it('says no to anything that is not the end', () => {
    expect(endsTheRun(envelope({ event_type: 'phase_end', phase_name: 'alpha' }))).toBe(false)
    expect(endsTheRun(envelope({ event_type: 'interrupted', reason: 'breakpoint' }))).toBe(false)
  })

  it('reads a raw callback event too, not only an envelope', () => {
    // Replayed traces arrive unwrapped; the same question has one answer.
    const raw = (status: string) =>
      ({
        schema_version: 'graph_agent.callbacks.v1',
        timestamp: '2026-08-22T00:00:00Z',
        event_type: 'run_ended',
        status,
      }) as unknown as Parameters<typeof endsTheRun>[0]

    expect(endsTheRun(raw('interrupted'))).toBe(false)
    expect(endsTheRun(raw('completed'))).toBe(true)
  })
})
