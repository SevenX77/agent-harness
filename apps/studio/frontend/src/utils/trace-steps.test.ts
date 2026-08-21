import { describe, expect, it } from 'vitest'
import type { CallbackEvent } from '../api/types'
import type { IndexedTraceEvent } from './trace-steps'
import { buildTraceSteps } from './trace-steps'

function indexed(events: Partial<CallbackEvent>[]): IndexedTraceEvent[] {
  return events.map((event, index) => ({
    event: { schema_version: '1.0', timestamp: `2026-08-09T00:00:0${index}Z`, ...event } as CallbackEvent,
    index,
  }))
}

describe('buildTraceSteps (decision 2026-08-09 D4)', () => {
  it('opens an LLM step the moment the prompt is captured, before any answer exists', () => {
    // This is the whole point: the reader sees "this node is thinking, here is
    // what it was asked" while it happens, not a summary once it is over.
    const steps = buildTraceSteps(indexed([
      { event_type: 'prompt_captured', phase_name: 'draft', step_id: 's1' },
    ]))

    expect(steps).toHaveLength(1)
    expect(steps[0].status).toBe('running')
    expect(steps[0].end).toBeNull()
  })

  it('closes that same step when the call comes back — one step, not two rows', () => {
    const steps = buildTraceSteps(indexed([
      { event_type: 'prompt_captured', phase_name: 'draft', step_id: 's1' },
      { event_type: 'llm_call', phase_name: 'draft', step_id: 's1' },
    ]))

    expect(steps).toHaveLength(1)
    expect(steps[0].status).toBe('done')
    expect(steps[0].start.event.event_type).toBe('prompt_captured')
    expect(steps[0].end?.event.event_type).toBe('llm_call')
  })

  it('does not let one node\'s answer close another node\'s prompt', () => {
    const steps = buildTraceSteps(indexed([
      { event_type: 'prompt_captured', phase_name: 'draft', step_id: 's1' },
      { event_type: 'prompt_captured', phase_name: 'review', step_id: 's2' },
      { event_type: 'llm_call', phase_name: 'review', step_id: 's2' },
    ]))

    expect(steps).toHaveLength(2)
    expect(steps[0].phase).toBe('draft')
    expect(steps[0].status).toBe('running')
    expect(steps[1].phase).toBe('review')
    expect(steps[1].status).toBe('done')
  })

  // Pairing by phase was only ever adequate because two calls in one phase
  // never overlapped in the trace. An agent turn makes several, so the engine
  // mints a step id and puts it on both halves — the same reason tool halves
  // carry a call id.
  it('pairs LLM halves by step id even when both calls are in one phase', () => {
    const steps = buildTraceSteps(indexed([
      { event_type: 'prompt_captured', phase_name: 'draft', step_id: 's1' },
      { event_type: 'prompt_captured', phase_name: 'draft', step_id: 's2' },
      { event_type: 'llm_call', phase_name: 'draft', step_id: 's2' },
    ]))

    expect(steps).toHaveLength(2)
    expect(steps[0].stepId).toBe('s1')
    expect(steps[0].status).toBe('running')
    expect(steps[1].stepId).toBe('s2')
    expect(steps[1].status).toBe('done')
  })

  it('pairs tool halves by tool_call_id, not by position', () => {
    // An agent turn can have several calls in flight; whichever returns first
    // must close ITS OWN step (engine contract, PR #655).
    const steps = buildTraceSteps(indexed([
      { event_type: 'tool_call_started', phase_name: 'draft', tool_call_id: 'a', tool_name: 'Read' },
      { event_type: 'tool_call_started', phase_name: 'draft', tool_call_id: 'b', tool_name: 'Bash' },
      { event_type: 'tool_call', phase_name: 'draft', tool_call_id: 'b', tool_name: 'Bash' },
    ]))

    expect(steps).toHaveLength(2)
    expect(steps[0].status).toBe('running')
    expect(steps[1].status).toBe('done')
    expect(steps[1].end?.event.tool_call_id).toBe('b')
  })

  it('leaves unpaired events exactly as they are, one row each', () => {
    const steps = buildTraceSteps(indexed([
      { event_type: 'phase_start', phase_name: 'draft' },
      { event_type: 'nudge', phase_name: 'draft' },
      { event_type: 'phase_end', phase_name: 'draft' },
    ]))

    expect(steps).toHaveLength(3)
    expect(steps.every((step) => step.status === 'done')).toBe(true)
    expect(steps.every((step) => step.end === null)).toBe(true)
  })

  it('treats a completion with no start as a finished step of its own', () => {
    // A filter can hide the opening half, and a trace can be read from any
    // point. Neither is a reason to drop the event on the floor.
    const steps = buildTraceSteps(indexed([
      { event_type: 'llm_call', phase_name: 'draft', step_id: 's1' },
    ]))

    expect(steps).toHaveLength(1)
    expect(steps[0].status).toBe('done')
    expect(steps[0].start.event.event_type).toBe('llm_call')
  })

  it('keeps steps in the order they started', () => {
    const steps = buildTraceSteps(indexed([
      { event_type: 'prompt_captured', phase_name: 'draft', step_id: 's1' },
      { event_type: 'phase_start', phase_name: 'draft' },
      { event_type: 'llm_call', phase_name: 'draft', step_id: 's1' },
    ]))

    expect(steps.map((step) => step.start.index)).toEqual([0, 1])
  })
})

// ── 决议 2026-08-13 D1:Iteration 分层 + 判定归并 ─────────────────────────────

describe('iteration layering (decision 2026-08-13 D1)', () => {
  it('agent_loop_iteration becomes the layer marker, not a row of its own', () => {
    const steps = buildTraceSteps(indexed([
      { event_type: 'agent_loop_iteration', phase_name: 'work', iteration: 1 },
      { event_type: 'prompt_captured', phase_name: 'work', step_id: 's1' },
    ]))

    expect(steps).toHaveLength(1)
    expect(steps[0].iteration).toBe(1)
  })

  it('steps opened after the next iteration marker carry the new number', () => {
    const steps = buildTraceSteps(indexed([
      { event_type: 'agent_loop_iteration', phase_name: 'work', iteration: 1 },
      { event_type: 'prompt_captured', phase_name: 'work', step_id: 's1' },
      { event_type: 'llm_call', phase_name: 'work', step_id: 's1' },
      { event_type: 'agent_loop_iteration', phase_name: 'work', iteration: 2 },
      { event_type: 'tool_call_started', phase_name: 'work', tool_call_id: 't1' },
    ]))

    expect(steps).toHaveLength(2)
    expect(steps[0].iteration).toBe(1)
    expect(steps[1].iteration).toBe(2)
  })

  it('does NOT read loop_index as the layer — it counts calls, not turns', () => {
    // One ReAct turn can spend several LLM calls: a rejected finish_task is
    // retried without a new `before_model`, so the engine's own batch fixture
    // spends three calls over two turns (engine
    // tests/core/test_agent_loop_iteration_is_per_execution.py). Reading the
    // call number as the turn number put a prompt under a divider that had not
    // opened yet.
    const steps = buildTraceSteps(indexed([
      { event_type: 'agent_loop_iteration', phase_name: 'work', iteration: 1 },
      { event_type: 'prompt_captured', phase_name: 'work', step_id: 's1', loop_index: 1 },
      { event_type: 'prompt_captured', phase_name: 'work', step_id: 's2', loop_index: 2 },
      { event_type: 'agent_loop_iteration', phase_name: 'work', iteration: 2 },
      { event_type: 'prompt_captured', phase_name: 'work', step_id: 's3', loop_index: 3 },
    ]))

    // Three calls become three steps (the turn markers are dividers, not
    // steps): the first two both belong to turn 1, only the third to turn 2.
    expect(steps.map((step) => step.iteration)).toEqual([1, 1, 2])
  })

  it('leaves an LLM call before any turn marker flat rather than guessing', () => {
    const steps = buildTraceSteps(indexed([
      { event_type: 'prompt_captured', phase_name: 'work', step_id: 's1', loop_index: 3 },
    ]))

    expect(steps[0].iteration).toBeNull()
  })

  it('a phase without loop markers stays flat (iteration null)', () => {
    const steps = buildTraceSteps(indexed([
      { event_type: 'phase_start', phase_name: 'setup' },
    ]))

    expect(steps[0].iteration).toBeNull()
  })
})

describe('verdict attachment (decision 2026-08-13 D1 sub-entry order)', () => {
  it('a route decision during the only open LLM step of its phase nests into that step', () => {
    const steps = buildTraceSteps(indexed([
      { event_type: 'prompt_captured', phase_name: 'work', step_id: 's1' },
      { event_type: 'llm_route_decision', phase_name: 'work', decision: 'answered' },
      { event_type: 'llm_call', phase_name: 'work', step_id: 's1' },
    ]))

    expect(steps).toHaveLength(1)
    expect(steps[0].verdicts).toHaveLength(1)
    expect(steps[0].verdicts[0].event.event_type).toBe('llm_route_decision')
  })

  it('with two open steps in one phase the verdict stays its own row — never guess', () => {
    const steps = buildTraceSteps(indexed([
      { event_type: 'prompt_captured', phase_name: 'work', step_id: 's1' },
      { event_type: 'prompt_captured', phase_name: 'work', step_id: 's2' },
      { event_type: 'llm_call_settings', phase_name: 'work', settings: [] },
    ]))

    expect(steps).toHaveLength(3)
  })

  it('with no open step the verdict stays its own row', () => {
    const steps = buildTraceSteps(indexed([
      { event_type: 'llm_route_decision', phase_name: 'work', decision: 'exhausted' },
    ]))

    expect(steps).toHaveLength(1)
    expect(steps[0].verdicts).toHaveLength(0)
  })
})

describe('buildTraceSteps × run verdict (decision 2026-08-13 D7 铁律)', () => {
  it('severs a step the run ended out from under — no spinner after the verdict', () => {
    // The cancel/crash case: the prompt went out, the worker died, the answer
    // will never come. "running" would be a lie the reader has to disprove.
    const steps = buildTraceSteps(indexed([
      { event_type: 'prompt_captured', phase_name: 'draft', step_id: 's1' },
    ]), 'cancelled')

    expect(steps).toHaveLength(1)
    expect(steps[0].status).toBe('severed')
  })

  it('leaves closed steps alone when severing', () => {
    const steps = buildTraceSteps(indexed([
      { event_type: 'prompt_captured', phase_name: 'draft', step_id: 's1' },
      { event_type: 'llm_call', phase_name: 'draft', step_id: 's1' },
      { event_type: 'tool_call_started', phase_name: 'draft', tool_call_id: 't1' },
    ]), 'failed')

    expect(steps[0].status).toBe('done')
    expect(steps[1].status).toBe('severed')
  })

  it('keeps steps running while the run is live or merely paused', () => {
    const open = [{ event_type: 'prompt_captured', phase_name: 'draft', step_id: 's1' }]
    expect(buildTraceSteps(indexed(open), 'running')[0].status).toBe('running')
    // A paused run resumes into the same step ids — the step is suspended, not
    // dead, and the resume's llm_call will close it properly.
    expect(buildTraceSteps(indexed(open), 'paused')[0].status).toBe('running')
  })
})

describe('run segments: an edge is peer to a node (decision 2026-08-15)', () => {
  it('pairs edge_start with edge_end into ONE segment row', () => {
    const steps = buildTraceSteps(indexed([
      { event_type: 'edge_start', edge_transition_id: 't1', from_phases: ['outline'], to_phase: 'draft' },
      { event_type: 'edge_end', edge_transition_id: 't1', from_phases: ['outline'], to_phase: 'draft' },
    ]))

    expect(steps).toHaveLength(1)
    expect(steps[0].status).toBe('done')
    expect(steps[0].segment).toEqual({ kind: 'edge', id: 't1' })
    expect(steps[0].end?.event.event_type).toBe('edge_end')
  })

  it('does not let one transition close another', () => {
    const steps = buildTraceSteps(indexed([
      { event_type: 'edge_start', edge_transition_id: 't1', to_phase: 'draft' },
      { event_type: 'edge_start', edge_transition_id: 't2', to_phase: 'review' },
      { event_type: 'edge_end', edge_transition_id: 't2', to_phase: 'review' },
    ]))

    expect(steps).toHaveLength(2)
    expect(steps[0].status).toBe('running')
    expect(steps[1].status).toBe('done')
  })

  it('puts an edge operation in the edge segment, not in the node that follows it', () => {
    const steps = buildTraceSteps(indexed([
      { event_type: 'edge_start', edge_transition_id: 't1', from_phases: ['outline'], to_phase: 'draft' },
      { event_type: 'input_dispatch', edge_transition_id: 't1', from_phases: ['outline'], to_phase: 'draft' },
      { event_type: 'edge_end', edge_transition_id: 't1', from_phases: ['outline'], to_phase: 'draft' },
      { event_type: 'phase_start', phase_name: 'draft', phase_execution_id: 'e1' },
    ]))

    const dispatch = steps.find((step) => step.start.event.event_type === 'input_dispatch')
    expect(dispatch?.segment).toEqual({ kind: 'edge', id: 't1' })
    const phaseStart = steps.find((step) => step.start.event.event_type === 'phase_start')
    expect(phaseStart?.segment).toEqual({ kind: 'phase', id: 'e1' })
  })

  it('groups a phase\'s events by the execution they ran in, not by the phase name', () => {
    const steps = buildTraceSteps(indexed([
      { event_type: 'phase_start', phase_name: 'draft', phase_execution_id: 'e1' },
      { event_type: 'prompt_captured', phase_name: 'draft', step_id: 's1' },
      { event_type: 'llm_call', phase_name: 'draft', step_id: 's1' },
      { event_type: 'phase_end', phase_name: 'draft', phase_execution_id: 'e1' },
      { event_type: 'phase_start', phase_name: 'draft', phase_execution_id: 'e2' },
      { event_type: 'prompt_captured', phase_name: 'draft', step_id: 's2' },
    ]))

    const first = steps.find((step) => step.stepId === 's1')
    const second = steps.find((step) => step.stepId === 's2')
    expect(first?.segment).toEqual({ kind: 'phase', id: 'e1' })
    expect(second?.segment).toEqual({ kind: 'phase', id: 'e2' })
  })

  it('starts each execution\'s turn counter fresh instead of inheriting the last one', () => {
    // A phase run twice by an outer loop is two executions. Carrying the first
    // execution's iteration into the second stamped its steps "Iteration 3"
    // before its own marker arrived.
    const steps = buildTraceSteps(indexed([
      { event_type: 'phase_start', phase_name: 'draft', phase_execution_id: 'e1' },
      { event_type: 'agent_loop_iteration', phase_name: 'draft', iteration: 3 },
      { event_type: 'prompt_captured', phase_name: 'draft', step_id: 's1' },
      { event_type: 'phase_end', phase_name: 'draft', phase_execution_id: 'e1' },
      { event_type: 'phase_start', phase_name: 'draft', phase_execution_id: 'e2' },
      { event_type: 'prompt_captured', phase_name: 'draft', step_id: 's2' },
    ]))

    expect(steps.find((step) => step.stepId === 's1')?.iteration).toBe(3)
    expect(steps.find((step) => step.stepId === 's2')?.iteration).toBeNull()
  })

  it('severs an unclosed transition when the run reaches a verdict', () => {
    const steps = buildTraceSteps(indexed([
      { event_type: 'edge_start', edge_transition_id: 't1', to_phase: 'draft' },
    ]), 'failed')

    expect(steps[0].status).toBe('severed')
  })
})

describe('a degradation is explained once, not re-explained on every call', () => {
  // Real shape, run 2026-08-19T06-58-15_179d1440: one endpoint timed out, and
  // the gateway re-probed it on the next call, and the one after that. Three
  // steps, three full "Probe failed — APITimeoutError…" blocks, one fact.
  const degraded = indexed([
    { event_type: 'prompt_captured', phase_name: 'segment', step_id: 's1', loop_index: 1 },
    { event_type: 'llm_route_decision', phase_name: 'segment', decision: 'probe_failed', endpoint_id: 'ep-a', reason: 'APITimeoutError' },
    { event_type: 'llm_call', phase_name: 'segment', step_id: 's1' },
    { event_type: 'prompt_captured', phase_name: 'review', step_id: 's2', loop_index: 1 },
    { event_type: 'llm_route_decision', phase_name: 'review', decision: 'probe_failed', endpoint_id: 'ep-a', reason: 'APITimeoutError' },
    { event_type: 'llm_call', phase_name: 'review', step_id: 's2' },
  ])

  it('numbers each repeat of an identical degradation', () => {
    const steps = buildTraceSteps(degraded)

    expect(steps[0].verdicts.map((verdict) => verdict.occurrence)).toEqual([1])
    expect(steps[1].verdicts.map((verdict) => verdict.occurrence)).toEqual([2])
  })

  it('treats a different outcome on the same endpoint as its own fact', () => {
    const steps = buildTraceSteps(indexed([
      { event_type: 'prompt_captured', phase_name: 'a', step_id: 's1' },
      { event_type: 'llm_route_decision', phase_name: 'a', decision: 'probe_failed', endpoint_id: 'ep-a', reason: 'timeout' },
      { event_type: 'llm_call', phase_name: 'a', step_id: 's1' },
      { event_type: 'prompt_captured', phase_name: 'b', step_id: 's2' },
      { event_type: 'llm_route_decision', phase_name: 'b', decision: 'skipped_circuit_open', endpoint_id: 'ep-a' },
      { event_type: 'llm_call', phase_name: 'b', step_id: 's2' },
    ]))

    expect(steps[1].verdicts[0].occurrence).toBe(1)
  })

  it('does not fold a healthy route decision — which endpoint served THIS call is per-call', () => {
    const steps = buildTraceSteps(indexed([
      { event_type: 'prompt_captured', phase_name: 'a', step_id: 's1' },
      { event_type: 'llm_route_decision', phase_name: 'a', decision: 'answered', endpoint_id: 'ep-b' },
      { event_type: 'llm_call', phase_name: 'a', step_id: 's1' },
      { event_type: 'prompt_captured', phase_name: 'b', step_id: 's2' },
      { event_type: 'llm_route_decision', phase_name: 'b', decision: 'answered', endpoint_id: 'ep-b' },
      { event_type: 'llm_call', phase_name: 'b', step_id: 's2' },
    ]))

    expect(steps[1].verdicts[0].occurrence).toBe(1)
  })
})
