/**
 * A stop has two flavours and the canvas must not spell them the same.
 *
 * `paused` means "nothing is executing"; a reader seeing it on a node knows
 * only that. But a run stopped at a breakpoint is stopped where the READER
 * asked, and the phase it names has not run even once — `interrupt_before`
 * halts on the way in. The canvas vocabulary already had a word for that
 * (`breakpoint`, in `nodes/types.ts`) with nothing to produce it.
 *
 * The engine now says which (`InterruptedEvent.reason`), so it is read rather
 * than guessed. Guessing was never possible anyway: an empty `question` could
 * equally be a human-in-the-loop stop whose question failed to parse.
 *
 * Design: run-execution/mvp1-alignment.md F10 + RUN_EXECUTION-16.
 */

import { describe, expect, it } from 'vitest'
import type { CallbackEvent } from '@/api/types'
import { deriveNodeStatuses } from './run-status-projection'

function event(partial: Partial<CallbackEvent> & { event_type: string }): CallbackEvent {
  return {
    schema_version: '1.0',
    timestamp: '2026-08-21T00:00:00Z',
    ...partial,
  } as CallbackEvent
}

function interrupted(reason: 'awaiting_human' | 'breakpoint'): CallbackEvent {
  return event({ event_type: 'interrupted', phase_name: 'review', thread_id: 'run-1', run_id: 'run-1', reason })
}

describe('a node the run stopped before', () => {
  it('is marked as a breakpoint when that is why it stopped', () => {
    const statuses = deriveNodeStatuses([interrupted('breakpoint')], 'run-1')

    expect(statuses.review).toBe('breakpoint')
  })

  it('is marked paused when it stopped to ask a human something', () => {
    const statuses = deriveNodeStatuses([interrupted('awaiting_human')], 'run-1')

    expect(statuses.review).toBe('paused')
  })

  it('is marked paused when the stop does not say why', () => {
    // An old trace on disk, replayed. Nothing is executing, which is all
    // `paused` claims — the safe reading, and the one that does not invent a
    // breakpoint the reader never set.
    const statuses = deriveNodeStatuses(
      [event({ event_type: 'interrupted', phase_name: 'review', thread_id: 'run-1', run_id: 'run-1' })],
      'run-1',
    )

    expect(statuses.review).toBe('paused')
  })

  it('stays stopped even after the run reports it ended', () => {
    // The run's verdict closes out anything still RUNNING; a node that already
    // said where it stopped is not still running and must not be overwritten.
    const statuses = deriveNodeStatuses(
      [
        event({ event_type: 'phase_start', phase_name: 'collect', run_id: 'run-1' }),
        event({ event_type: 'phase_end', phase_name: 'collect', run_id: 'run-1' }),
        interrupted('breakpoint'),
        event({ event_type: 'run_ended', run_id: 'run-1', status: 'interrupted' }),
      ],
      'run-1',
    )

    expect(statuses.review).toBe('breakpoint')
    expect(statuses.collect).toBe('success')
  })
})
