import { describe, expect, it } from 'vitest'
import type { CallbackEvent } from '../api/types'
import { EDGE_SEGMENT_EVENT_TYPES, eventCrossesEdge, isInputBoundaryId, isOutputBoundaryId } from './edge-identity'

function event(partial: Partial<CallbackEvent> & { event_type: string }): CallbackEvent {
  return {
    schema_version: '1.0',
    timestamp: '2026-08-20T00:00:00Z',
    ...partial,
  } as CallbackEvent
}

// One predicate answers "does this event belong to the edge source → target",
// and every surface that asks the question consumes it. It exists because two
// modules used to answer it separately and disagreed: the trace scope handled
// the root edge, the canvas edge-dot did not, so a run's first edge showed the
// static guess forever (ledger T6 缺陷① / IO1).
describe('eventCrossesEdge', () => {
  it('matches a phase-to-phase transition by upstream membership', () => {
    expect(eventCrossesEdge(
      event({ event_type: 'input_dispatch', from_phases: ['draft'], to_phase: 'review' }),
      'draft',
      'review',
    )).toBe(true)
    expect(eventCrossesEdge(
      event({ event_type: 'input_dispatch', from_phases: ['other'], to_phase: 'review' }),
      'draft',
      'review',
    )).toBe(false)
  })

  it('reads an EMPTY upstream list as "the run input is upstream", not as "no match"', () => {
    // The engine sets from_phases = list(upstream_phases) (core/edge_transition.py),
    // so an empty list is the root transition: its upstream IS the run input.
    const rootDispatch = event({ event_type: 'input_dispatch', from_phases: [], to_phase: 'draft' })
    expect(eventCrossesEdge(rootDispatch, '__global_input__', 'draft')).toBe(true)
    expect(eventCrossesEdge(rootDispatch, 'input', 'draft')).toBe(true)
    expect(eventCrossesEdge(rootDispatch, 'planner', 'draft')).toBe(false)
  })

  it('still matches a root transition that names the boundary outright', () => {
    expect(eventCrossesEdge(
      event({ event_type: 'input_dispatch', from_phases: ['input'], to_phase: 'draft' }),
      '__global_input__',
      'draft',
    )).toBe(true)
  })

  it('accepts either output alias on the terminal edge', () => {
    expect(eventCrossesEdge(
      event({ event_type: 'input_dispatch', from_phases: ['review'], to_phase: 'output' }),
      'review',
      '__global_output__',
    )).toBe(true)
  })

  it('attributes artifact_saved to the edge leaving the phase that persisted it', () => {
    const saved = event({ event_type: 'artifact_saved', phase_name: 'draft' })
    expect(eventCrossesEdge(saved, 'draft', 'review')).toBe(true)
    expect(eventCrossesEdge(saved, 'review', 'ship')).toBe(false)
  })

  it('admits the edge segment brackets themselves, not only the operations inside them', () => {
    // edge_start / edge_end carry the segment's own summary (changed_keys,
    // operation_count, snapshot). Leaving them out of the edge's own identity
    // hid the segment from the scope that selected it.
    expect(eventCrossesEdge(
      event({ event_type: 'edge_start', from_phases: ['draft'], to_phase: 'review' }),
      'draft',
      'review',
    )).toBe(true)
    expect(eventCrossesEdge(
      event({ event_type: 'edge_end', from_phases: ['draft'], to_phase: 'review' }),
      'draft',
      'review',
    )).toBe(true)
  })

  it('rejects events that are not part of any edge segment', () => {
    expect(eventCrossesEdge(
      event({ event_type: 'phase_start', phase_name: 'review' }),
      'draft',
      'review',
    )).toBe(false)
    expect(eventCrossesEdge(
      event({ event_type: 'llm_call', phase_name: 'draft' }),
      'draft',
      'review',
    )).toBe(false)
  })

  it('names the segment event family in one place', () => {
    expect([...EDGE_SEGMENT_EVENT_TYPES].sort()).toEqual([
      'blackboard_reduce',
      'edge_end',
      'edge_start',
      'input_dispatch',
      'input_file_injected',
    ])
  })
})

describe('boundary ids', () => {
  it('knows both aliases the canvas mints for each boundary node', () => {
    expect(isInputBoundaryId('__global_input__')).toBe(true)
    expect(isInputBoundaryId('input')).toBe(true)
    expect(isInputBoundaryId('draft')).toBe(false)
    expect(isOutputBoundaryId('__global_output__')).toBe(true)
    expect(isOutputBoundaryId('output')).toBe(true)
    expect(isOutputBoundaryId('draft')).toBe(false)
  })
})
