import { describe, expect, it } from 'vitest'

import type { CallbackEvent } from '@/api/types'
import { edgeContextFromEvents } from './edge-context'

function dispatchEvent(
  fromPhase: string | null,
  toPhase: string,
  snapshot: Record<string, unknown>,
  extra: Partial<CallbackEvent> = {},
): CallbackEvent {
  return {
    schema_version: '1.0',
    event_type: 'input_dispatch',
    timestamp: '2026-06-14T00:00:00Z',
    from_phase: fromPhase,
    to_phase: toPhase,
    changed_keys: Object.keys(snapshot),
    blackboard_snapshot: snapshot,
    dispatched_keys: Object.keys(snapshot),
    branch_index: null,
    ...extra,
  } as CallbackEvent
}

describe('edgeContextFromEvents', () => {
  it('maps a matching dispatch event into the panel render shape', () => {
    const snapshot = { query: 'build a router', max_iterations: 5 }
    const events: CallbackEvent[] = [
      dispatchEvent('planner', 'executor', snapshot, { changed_keys: ['query'] }),
    ]

    const result = edgeContextFromEvents(events, 'planner', 'executor')

    expect(result).not.toBeNull()
    // Inputs subsection of the Properties panel renders the flat snapshot.
    expect(result?.inputs).toEqual(snapshot)
    expect(result?.blackboard_snapshot).toEqual(snapshot)
    expect(result?.phase_outputs).toEqual({})
    expect(result?.from_phase).toBe('planner')
    expect(result?.to_phase).toBe('executor')
    expect(result?.changed_keys).toEqual(['query'])
  })

  it('picks the LAST matching event when several exist', () => {
    const events: CallbackEvent[] = [
      dispatchEvent('planner', 'executor', { attempt: 1 }),
      dispatchEvent('other', 'sink', { unrelated: true }),
      dispatchEvent('planner', 'executor', { attempt: 2 }),
    ]

    const result = edgeContextFromEvents(events, 'planner', 'executor')

    expect(result?.inputs).toEqual({ attempt: 2 })
  })

  it('matches the graph-entry edge when from_phase is null or "input"', () => {
    const snapshot = { query: 'kick off' }
    const fromNull = edgeContextFromEvents(
      [dispatchEvent(null, 'planner', snapshot)],
      '__global_input__',
      'planner',
    )
    const fromInput = edgeContextFromEvents(
      [dispatchEvent('input', 'planner', snapshot)],
      '__global_input__',
      'planner',
    )

    expect(fromNull?.inputs).toEqual(snapshot)
    expect(fromInput?.inputs).toEqual(snapshot)
  })

  it('returns null when no event matches the edge', () => {
    const events: CallbackEvent[] = [
      dispatchEvent('planner', 'executor', { query: 'x' }),
    ]

    expect(edgeContextFromEvents(events, 'planner', 'reviewer')).toBeNull()
    expect(edgeContextFromEvents([], 'planner', 'executor')).toBeNull()
  })

  it('ignores non-dispatch events with matching phases', () => {
    const reduceEvent: CallbackEvent = {
      schema_version: '1.0',
      event_type: 'blackboard_reduce',
      timestamp: '2026-06-14T00:00:00Z',
      from_phase: 'planner',
      to_phase: 'executor',
      changed_keys: ['query'],
      blackboard_snapshot: { query: 'should be ignored' },
      reducer: 'last_write_wins',
    } as CallbackEvent

    expect(edgeContextFromEvents([reduceEvent], 'planner', 'executor')).toBeNull()
  })
})
