import { describe, expect, it } from 'vitest'

import type { CallbackEvent, EventEnvelope } from '@/api/types'
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

function edgeTransitionEnvelope(): EventEnvelope {
  return {
    schema_version: 'studio.event.v1',
    stream_id: 'run:run-1',
    seq: 4,
    cursor: 'run:run-1:4',
    run_id: 'run-1',
    event_type: 'edge_transition',
    timestamp: '2026-06-14T00:00:00Z',
    payload: {
      schema_version: '1.0',
      event_type: 'edge_transition',
      timestamp: '2026-06-14T00:00:00Z',
      edge_transition_id: 'edge-run-1-4',
      run_id: 'run-1',
      execution_id: 'exec-1',
      attempt: 2,
      from_phase: 'planner',
      to_phase: 'executor',
      before: { query: 'old' },
      after: { query: 'new', max_iterations: 5 },
      diff: { changed_keys: ['query', 'max_iterations'] },
    } as CallbackEvent,
  }
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

  it('maps an EventEnvelope edge_transition payload into edge context', () => {
    const result = edgeContextFromEvents([edgeTransitionEnvelope()], 'planner', 'executor')

    expect(result?.inputs).toEqual({ query: 'new', max_iterations: 5 })
    expect(result?.blackboard_snapshot).toEqual({ query: 'new', max_iterations: 5 })
    expect(result?.changed_keys).toEqual(['query', 'max_iterations'])
    expect(result?.edge_transition_id).toBe('edge-run-1-4')
    expect(result?.run_id).toBe('run-1')
    expect(result?.execution_id).toBe('exec-1')
    expect(result?.attempt).toBe(2)
    expect(result?.before).toEqual({ query: 'old' })
    expect(result?.after).toEqual({ query: 'new', max_iterations: 5 })
    expect(result?.diff).toEqual({ changed_keys: ['query', 'max_iterations'] })
  })

  it('preserves checkpoint identity for downstream resume from edge context', () => {
    const result = edgeContextFromEvents([
      dispatchEvent('planner', 'executor', { query: 'new' }, {
        checkpoint_id: 'checkpoint-executor',
        checkpoint_ns: 'agent:executor',
      }),
    ], 'planner', 'executor')

    expect(result?.checkpoint_id).toBe('checkpoint-executor')
    expect(result?.checkpoint_ns).toBe('agent:executor')
  })

  it('preserves tamper diff, audit, and resume validity for the edge inspection panel', () => {
    const result = edgeContextFromEvents([
      dispatchEvent('planner', 'executor', { query: 'new' }, {
        tamper_diff: {
          changed_keys: ['query'],
          before: { query: 'old' },
          after: { query: 'new' },
        },
        tamper_audit: {
          actor: 'manual-debugger',
          reason: 'D10.4 browser validation',
        },
        resume_validity: {
          resume_allowed: false,
          reason: 'dirty_upstream',
        },
      }),
    ], 'planner', 'executor')

    expect(result?.tamper_diff).toEqual({
      changed_keys: ['query'],
      before: { query: 'old' },
      after: { query: 'new' },
    })
    expect(result?.tamper_audit).toEqual({
      actor: 'manual-debugger',
      reason: 'D10.4 browser validation',
    })
    expect(result?.resume_validity).toEqual({
      resume_allowed: false,
      reason: 'dirty_upstream',
    })
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

  it('matches a literal input dependency only when the event reports input', () => {
    const snapshot = { query: 'kick off' }
    const fromNull = edgeContextFromEvents(
      [dispatchEvent(null, 'planner', snapshot)],
      'input',
      'planner',
    )
    const fromInput = edgeContextFromEvents(
      [dispatchEvent('input', 'planner', snapshot)],
      'input',
      'planner',
    )

    expect(fromNull).toBeNull()
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

  it('collects the end -> start operation log (reduce / dispatch / inject / persist) in stream order', () => {
    const reduceEvent: CallbackEvent = {
      schema_version: '1.0',
      event_type: 'blackboard_reduce',
      timestamp: '2026-06-14T00:00:00Z',
      from_phase: 'planner',
      to_phase: 'executor',
      changed_keys: ['plan'],
      blackboard_snapshot: { plan: 'x' },
      reducer: 'merge_dicts',
    } as CallbackEvent
    const persistEvent: CallbackEvent = {
      schema_version: '1.0',
      event_type: 'artifact_saved',
      timestamp: '2026-06-14T00:00:00Z',
      phase_name: 'planner',
      name: 'plan.json',
      path: 'runs/r1/plan.json',
      size_bytes: 128,
    } as CallbackEvent
    const injectEvent: CallbackEvent = {
      schema_version: '1.0',
      event_type: 'input_file_injected',
      timestamp: '2026-06-14T00:00:00Z',
      from_phase: 'planner',
      to_phase: 'executor',
      changed_keys: ['spec'],
      blackboard_snapshot: { spec: '<file>' },
      file_ref: 'runs/r1/plan.json',
      target_field: 'spec',
    } as CallbackEvent

    const result = edgeContextFromEvents(
      [
        reduceEvent,
        persistEvent,
        injectEvent,
        dispatchEvent('planner', 'executor', { plan: 'x', spec: '<file>' }, {
          dispatched_keys: ['plan', 'spec'],
          changed_keys: ['plan', 'spec'],
        }),
      ],
      'planner',
      'executor',
    )

    expect(result?.operations).toEqual([
      { kind: 'reduce', reducer: 'merge_dicts', changed_keys: ['plan'] },
      { kind: 'persist', name: 'plan.json', path: 'runs/r1/plan.json', size_bytes: 128 },
      { kind: 'inject', file_ref: 'runs/r1/plan.json', target_field: 'spec' },
      { kind: 'dispatch', dispatched_keys: ['plan', 'spec'], changed_keys: ['plan', 'spec'] },
    ])
  })

  it('attributes artifact_saved to the edge whose upstream phase persisted it', () => {
    const persistForOtherPhase: CallbackEvent = {
      schema_version: '1.0',
      event_type: 'artifact_saved',
      timestamp: '2026-06-14T00:00:00Z',
      phase_name: 'reviewer',
      name: 'review.json',
      path: 'runs/r1/review.json',
      size_bytes: 64,
    } as CallbackEvent

    const result = edgeContextFromEvents(
      [
        persistForOtherPhase,
        dispatchEvent('planner', 'executor', { plan: 'x' }),
      ],
      'planner',
      'executor',
    )

    // The reviewer-owned artifact must NOT appear on the planner -> executor edge.
    expect(result?.operations).toEqual([
      { kind: 'dispatch', dispatched_keys: ['plan'], changed_keys: ['plan'] },
    ])
  })

  it('returns an empty operation log when only the dispatch snapshot exists', () => {
    const result = edgeContextFromEvents(
      [dispatchEvent('planner', 'executor', { query: 'x' }, { dispatched_keys: ['query'] })],
      'planner',
      'executor',
    )

    expect(result?.operations).toEqual([
      { kind: 'dispatch', dispatched_keys: ['query'], changed_keys: ['query'] },
    ])
  })
})
