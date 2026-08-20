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
    from_phases: fromPhase === null ? [] : [fromPhase],
    to_phase: toPhase,
    changed_keys: Object.keys(snapshot),
    blackboard_snapshot: snapshot,
    dispatched_keys: Object.keys(snapshot),
    branch_index: null,
    ...extra,
  } as CallbackEvent
}

function runEndedEvent(phaseOutputs: Record<string, Record<string, unknown>>): CallbackEvent {
  return {
    schema_version: '1.0',
    event_type: 'run_ended',
    timestamp: '2026-06-14T00:00:10Z',
    run_id: 'run-1',
    status: 'completed',
    final_context: { inputs: {}, phase_outputs: phaseOutputs, scratch: {} },
    wall_time_seconds: 10,
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

  it('resolves the Input-boundary edge, whether or not the engine names the boundary', () => {
    // The first phase has no predecessor, so the engine emits from_phases: []
    // (core/edge_transition.py sets it from the compiled upstream list). That
    // empty list IS the root transition — reading it as "no match" is what left
    // the run's first edge dot showing the pre-run static guess after a green
    // run (ledger T6 缺陷①).
    const snapshot = { query: 'kick off' }
    const fromEmpty = edgeContextFromEvents(
      [dispatchEvent(null, 'planner', snapshot)],
      'input',
      'planner',
    )
    const fromNamed = edgeContextFromEvents(
      [dispatchEvent('input', 'planner', snapshot)],
      'input',
      'planner',
    )
    const fromCanvasId = edgeContextFromEvents(
      [dispatchEvent(null, 'planner', snapshot)],
      '__global_input__',
      'planner',
    )

    expect(fromEmpty?.inputs).toEqual(snapshot)
    expect(fromNamed?.inputs).toEqual(snapshot)
    expect(fromCanvasId?.inputs).toEqual(snapshot)
  })

  it('does not hand a root transition to an ordinary phase-to-phase edge', () => {
    const snapshot = { query: 'kick off' }
    expect(edgeContextFromEvents(
      [dispatchEvent(null, 'planner', snapshot)],
      'upstream',
      'planner',
    )).toBeNull()
  })

  it('returns null when no event matches the edge', () => {
    const events: CallbackEvent[] = [
      dispatchEvent('planner', 'executor', { query: 'x' }),
    ]

    expect(edgeContextFromEvents(events, 'planner', 'reviewer')).toBeNull()
    expect(edgeContextFromEvents([], 'planner', 'executor')).toBeNull()
  })

  it('shows what the run handed out on the edge into the Output boundary', () => {
    // `__global_output__` is a canvas node, not a graph node: it appears zero
    // times in the engine, the gateway and the studio backend (buildEdges.ts
    // mints it). So no transition ever runs into it and no `input_dispatch`
    // ever names it — the run's own report of what it produced is
    // `run_ended.final_context.phase_outputs[<the output phase>]`, and reading
    // that is what makes this dot show the run instead of a static guess
    // (ledger E14). Emitting a second event carrying the same values would be
    // the same "two answers to one question" defect as OB11/OB12.
    const framework = { acts: 3, title: 'a story' }
    const result = edgeContextFromEvents(
      [
        dispatchEvent('story_analysis', 'global_synthesis', { batch_outputs: [] }),
        runEndedEvent({
          story_analysis: { batch_outputs: [] },
          global_synthesis: { story_framework: framework },
        }),
      ],
      'global_synthesis',
      '__global_output__',
    )

    expect(result?.inputs).toEqual({ story_framework: framework })
    expect(result?.blackboard_snapshot).toEqual({ story_framework: framework })
    expect(result?.from_phase).toBe('global_synthesis')
    expect(result?.to_phase).toBe('__global_output__')
    expect(result?.changed_keys).toEqual(['story_framework'])
  })

  it('leaves the Output edge to the static inference until the run reports an end', () => {
    // Mid-run there is nothing produced yet, and a premature "this is what the
    // run handed out" is worse than the honest pre-run inference.
    expect(edgeContextFromEvents(
      [dispatchEvent('story_analysis', 'global_synthesis', { batch_outputs: [] })],
      'global_synthesis',
      '__global_output__',
    )).toBeNull()
  })

  it('does not hand one phase’s outputs to another phase’s Output edge', () => {
    // A run can end without the output phase having produced anything; showing
    // the previous phase's outputs there would name the wrong producer.
    expect(edgeContextFromEvents(
      [runEndedEvent({ story_analysis: { batch_outputs: [] } })],
      'global_synthesis',
      '__global_output__',
    )).toBeNull()
  })

  it('leaves an edge into a literal `output` phase on the dispatch path', () => {
    // `output` is also an id the boundary helpers accept, because a skill may
    // declare a phase by that name — but such a phase is a real graph node with
    // real transitions, so its dot must keep reading its own dispatch.
    const dispatched = { draft: 'text to publish' }
    const result = edgeContextFromEvents(
      [
        dispatchEvent('writer', 'output', dispatched),
        runEndedEvent({ writer: { draft: 'text to publish' }, output: { published: true } }),
      ],
      'writer',
      'output',
    )

    expect(result?.inputs).toEqual(dispatched)
  })

  it('ignores non-dispatch events with matching phases', () => {
    const reduceEvent: CallbackEvent = {
      schema_version: '1.0',
      event_type: 'blackboard_reduce',
      timestamp: '2026-06-14T00:00:00Z',
      from_phases: ['planner'],
      to_phase: 'executor',
      changed_keys: ['query'],
      blackboard_snapshot: { query: 'should be ignored' },
      reducer: 'last_write_wins',
    } as CallbackEvent

    expect(edgeContextFromEvents([reduceEvent], 'planner', 'executor')).toBeNull()
  })

})
