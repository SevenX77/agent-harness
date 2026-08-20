import { describe, expect, it } from 'vitest'
import type { CallbackEvent } from '../api/types'
import { eventInScope, scopeLabel, type TraceScope } from './trace-scope'

function event(partial: Partial<CallbackEvent> & { event_type: string }): CallbackEvent {
  return {
    schema_version: '1.0',
    timestamp: '2026-08-14T00:00:00Z',
    ...partial,
  } as CallbackEvent
}

// Decision 2026-08-13 D6 (选中即范围): the canvas selection IS the trace's
// display scope. These lock what each scope kind admits.
describe('eventInScope', () => {
  it('node scope admits the events that belong to that node, edge arrivals included', () => {
    const scope: TraceScope = { kind: 'node', phase: 'draft' }
    expect(eventInScope(event({ event_type: 'phase_start', phase_name: 'draft' }), scope)).toBe(true)
    expect(eventInScope(event({ event_type: 'input_dispatch', to_phase: 'draft' }), scope)).toBe(true)
    expect(eventInScope(event({ event_type: 'phase_start', phase_name: 'review' }), scope)).toBe(false)
    expect(eventInScope(event({ event_type: 'run_started' }), scope)).toBe(false)
  })

  it('edge scope admits exactly the edge-op events of that transition (D5)', () => {
    const scope: TraceScope = { kind: 'edge', source: 'draft', target: 'review' }
    expect(eventInScope(event({ event_type: 'input_dispatch', from_phases: ['draft'], to_phase: 'review' }), scope)).toBe(true)
    expect(eventInScope(event({ event_type: 'blackboard_reduce', from_phases: ['draft'], to_phase: 'review' }), scope)).toBe(true)
    expect(eventInScope(event({ event_type: 'input_file_injected', from_phases: ['draft'], to_phase: 'review' }), scope)).toBe(true)
    // artifact_saved carries only phase_name: it belongs to the edge whose
    // UPSTREAM phase persisted it (same attribution edge-context.ts used).
    expect(eventInScope(event({ event_type: 'artifact_saved', phase_name: 'draft' }), scope)).toBe(true)
    expect(eventInScope(event({ event_type: 'input_dispatch', from_phases: ['other'], to_phase: 'review' }), scope)).toBe(false)
    expect(eventInScope(event({ event_type: 'phase_start', phase_name: 'review' }), scope)).toBe(false)
  })

  it('an input-boundary edge matches the null from_phase the engine emits for the first phase', () => {
    // graph_assembler._emit_input_dispatch sets from_phase from
    // flow.current_phase, which is None before anything ran — exactly the
    // dispatches crossing the Input boundary edge.
    const scope: TraceScope = { kind: 'edge', source: '__global_input__', target: 'draft' }
    expect(eventInScope(event({ event_type: 'input_dispatch', to_phase: 'draft' }), scope)).toBe(true)
    expect(eventInScope(event({ event_type: 'input_dispatch', from_phases: ['other'], to_phase: 'draft' }), scope)).toBe(false)
  })

  it('edge scope keeps the segment brackets, not only the operations between them', () => {
    // The engine brackets every transition with edge_start / edge_end, and the
    // brackets carry the segment's own summary (changed_keys, operation_count).
    // Filtering them out left the selected edge showing its contents while
    // hiding the segment the reader clicked on.
    const scope: TraceScope = { kind: 'edge', source: 'draft', target: 'review' }
    expect(eventInScope(event({ event_type: 'edge_start', from_phases: ['draft'], to_phase: 'review' }), scope)).toBe(true)
    expect(eventInScope(event({ event_type: 'edge_end', from_phases: ['draft'], to_phase: 'review' }), scope)).toBe(true)
    expect(eventInScope(event({ event_type: 'edge_end', from_phases: ['other'], to_phase: 'review' }), scope)).toBe(false)
  })

  it('Input scope shows what leaves the input boundary; Output what arrives at it', () => {
    expect(eventInScope(event({ event_type: 'input_dispatch', to_phase: 'draft' }), { kind: 'input' })).toBe(true)
    expect(eventInScope(event({ event_type: 'input_dispatch', from_phases: ['draft'], to_phase: 'review' }), { kind: 'input' })).toBe(false)
    expect(eventInScope(event({ event_type: 'blackboard_reduce', from_phases: ['review'], to_phase: 'output' }), { kind: 'output' })).toBe(true)
    expect(eventInScope(event({ event_type: 'phase_end', phase_name: 'review' }), { kind: 'output' })).toBe(false)
  })
})

describe('scopeLabel', () => {
  it('names each scope the way the canvas does', () => {
    expect(scopeLabel({ kind: 'node', phase: 'draft' })).toBe('draft')
    expect(scopeLabel({ kind: 'edge', source: 'draft', target: 'review' })).toBe('draft → review')
    expect(scopeLabel({ kind: 'edge', source: '__global_input__', target: 'draft' })).toBe('Input → draft')
    expect(scopeLabel({ kind: 'edge', source: 'review', target: '__global_output__' })).toBe('review → Output')
    expect(scopeLabel({ kind: 'input' })).toBe('Input')
    expect(scopeLabel({ kind: 'output' })).toBe('Output')
  })
})
