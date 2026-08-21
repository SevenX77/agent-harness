import { describe, expect, it } from 'vitest'
import type { CallbackEvent } from '../api/types'
import i18n from '../i18n'
import { traceHeadlineText, type TraceCopy } from '../components/trace/trace-copy'
import { eventHeadline } from './trace'
import { buildTraceSteps, type TraceStep } from './trace-steps'
import {
  NO_NARROWING,
  isNarrowingActive,
  narrowTraceSteps,
  type TraceNarrowing,
} from './trace-narrowing'

const traceCopy = i18n.getFixedT(null, ['trace', 'canvas']) as unknown as TraceCopy
const headlineOf = (event: CallbackEvent): string =>
  traceHeadlineText(eventHeadline(event), traceCopy)

function event(overrides: Partial<CallbackEvent> & { event_type: string }): CallbackEvent {
  return { schema_version: '1.0', timestamp: '2026-08-21T00:00:00Z', ...overrides } as CallbackEvent
}

function stepsOf(events: CallbackEvent[]): TraceStep[] {
  return buildTraceSteps(events.map((item, index) => ({ event: item, index })))
}

/** One LLM step: the prompt opens it, the call closes it and carries the model. */
function llmStep(): CallbackEvent[] {
  return [
    event({ event_type: 'prompt_captured', phase_name: 'draft', step_id: 's1' }),
    event({
      event_type: 'llm_call',
      phase_name: 'draft',
      step_id: 's1',
      response_data: { model_name: 'deepseek-v4-flash-260425' },
    }),
  ]
}

function narrowing(overrides: Partial<TraceNarrowing> = {}): TraceNarrowing {
  return { ...NO_NARROWING, ...overrides }
}

describe('narrowTraceSteps — the unit of narrowing is the step the reader sees', () => {
  it('keeps nothing back when no narrowing is on', () => {
    const steps = stepsOf(llmStep())

    expect(narrowTraceSteps(steps, NO_NARROWING, headlineOf)).toEqual(steps)
    expect(isNarrowingActive(NO_NARROWING)).toBe(false)
  })

  it('keeps the WHOLE step when only its closing half matches', () => {
    // The defect this replaces filtered events: matching the closing `llm_call`
    // dropped the `prompt_captured` that opened the step, leaving an answer with
    // no question — a row the reader cannot account for. 呈现单位 = 步骤 (F9).
    const steps = stepsOf(llmStep())
    expect(steps).toHaveLength(1)

    const kept = narrowTraceSteps(steps, narrowing({ searchTerm: 'deepseek-v4-flash' }), headlineOf)

    expect(kept).toHaveLength(1)
    expect(kept[0].start.event.event_type).toBe('prompt_captured')
    expect(kept[0].end?.event.event_type).toBe('llm_call')
  })

  it('matches the values in an event, not the shape of its payload', () => {
    // `phase_name` is a field NAME. Matching the serialized JSON made every
    // event in the run a hit for it, and every such hit is a row whose reason
    // the reader cannot see anywhere on it.
    const steps = stepsOf(llmStep())

    expect(narrowTraceSteps(steps, narrowing({ searchTerm: 'phase_name' }), headlineOf)).toEqual([])
    expect(narrowTraceSteps(steps, narrowing({ searchTerm: 'draft' }), headlineOf)).toHaveLength(1)
  })

  it('matches the event type and the rendered headline', () => {
    const steps = stepsOf(llmStep())

    expect(narrowTraceSteps(steps, narrowing({ searchTerm: 'llm_call' }), headlineOf)).toHaveLength(1)
    expect(narrowTraceSteps(steps, narrowing({ searchTerm: 'nothing here' }), headlineOf)).toEqual([])
  })

  it('keeps only steps whose route actually degraded when route issues are on', () => {
    // The chip counts degradations (`decision !== 'answered'`), so what it
    // reveals has to be those same degradations. Revealing every route decision
    // makes the count a promise the list does not keep (F3, 2026-08-20).
    const answered = [
      ...llmStep(),
      event({
        event_type: 'llm_route_decision',
        phase_name: 'draft',
        step_id: 's1',
        decision: 'answered',
      }),
    ]
    const degraded = [
      event({ event_type: 'prompt_captured', phase_name: 'review', step_id: 's2' }),
      event({
        event_type: 'llm_route_decision',
        phase_name: 'review',
        step_id: 's2',
        decision: 'fell_back',
      }),
      event({ event_type: 'llm_call', phase_name: 'review', step_id: 's2' }),
    ]
    const steps = stepsOf([...answered, ...degraded])

    const kept = narrowTraceSteps(steps, narrowing({ routeIssuesOnly: true }), headlineOf)

    expect(kept).toHaveLength(1)
    expect(kept[0].phase).toBe('review')
  })

  it('narrows by category and by phase, and combines every criterion with AND', () => {
    const steps = stepsOf([
      ...llmStep(),
      event({ event_type: 'phase_start', phase_name: 'review' }),
    ])

    expect(narrowTraceSteps(steps, narrowing({ selectedPhases: ['review'] }), headlineOf)).toHaveLength(1)
    expect(
      narrowTraceSteps(steps, narrowing({ selectedPhases: ['review'], searchTerm: 'deepseek' }), headlineOf),
    ).toEqual([])
  })

  it('reports itself as active for every kind of criterion', () => {
    expect(isNarrowingActive(narrowing({ searchTerm: 'x' }))).toBe(true)
    expect(isNarrowingActive(narrowing({ searchTerm: '   ' }))).toBe(false)
    expect(isNarrowingActive(narrowing({ selectedCategories: ['llm'] }))).toBe(true)
    expect(isNarrowingActive(narrowing({ selectedPhases: ['draft'] }))).toBe(true)
    expect(isNarrowingActive(narrowing({ routeIssuesOnly: true }))).toBe(true)
  })
})
