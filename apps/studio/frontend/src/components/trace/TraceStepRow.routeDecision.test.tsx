import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import type { CallbackEvent } from '../../api/types'
import { eventPhase } from '../../utils/trace'
import { TraceStepRow } from './TraceStepRow'

// trace-observability F7: a gateway llm_route_decision event must render as an
// explicit block naming the route, the endpoint behind it and what the gateway
// decided — and rows that know which model served the call must surface it as a
// chip. Without it a run that silently degraded from model A to model B, or that
// spent two minutes on the second-choice endpoint, looks like nothing happened.

function makeEvent(partial: Partial<CallbackEvent> & { event_type: string }): CallbackEvent {
  return {
    schema_version: '1.0',
    timestamp: '2026-07-16T00:00:00Z',
    ...partial,
  } as CallbackEvent
}

function render(event: CallbackEvent): string {
  return renderToStaticMarkup(
    <TraceStepRow
      step={{
        key: 'evt-0',
        phase: eventPhase(event),
        status: 'done',
        start: { event, index: 0 },
        end: null,
      }}
      eventId="evt-0"
      expanded={false}
      onToggleExpanded={() => undefined}
    />,
  )
}

describe('TraceStepRow llm_route_decision rendering', () => {
  const decision = (overrides: Partial<CallbackEvent> = {}) => makeEvent({
    event_type: 'llm_route_decision',
    phase_name: 'draft',
    decision: 'fell_back',
    route_id: 'openai:gpt-4o',
    endpoint_id: 'openai',
    provider_model_id: 'gpt-4o-2024-11-20',
    protocol: 'openai_compatible',
    next_route_id: 'zhipu:glm-4.7',
    reason: 'RateLimitError: 429 too many requests',
    provider_status_code: 429,
    ...overrides,
  })

  it('renders an explicit Provider fallback block with both routes and the reason', () => {
    const html = render(decision())
    expect(html).toContain('Provider fallback')
    expect(html).toContain('gpt-4o-2024-11-20')
    expect(html).toContain('zhipu:glm-4.7')
    expect(html).toContain('HTTP 429')
    expect(html).toContain('RateLimitError: 429 too many requests')
  })

  // The endpoint is the one thing llm_call never carried: two routes can serve
  // the same model id from different providers.
  it('names the endpoint and model of the route that answered', () => {
    const html = render(decision({ decision: 'answered', next_route_id: null, reason: null }))
    expect(html).toContain('Route used')
    expect(html).toContain('endpoint: openai')
    expect(html).toContain('gpt-4o-2024-11-20')
  })

  it('labels an exhausted chain when no route remains', () => {
    const html = render(decision({ decision: 'exhausted', reason: 'AuthenticationError: 401' }))
    expect(html).toContain('All routes exhausted')
    expect(html).toContain('no remaining route')
  })

  // Retrying is only possible after a truncated answer has already streamed, so
  // the panel is showing text this decision threw away.
  it('says when a decision discarded the partial answer already on screen', () => {
    const html = render(decision({ decision: 'escalated_budget', voided_streamed_answer: true }))
    expect(html).toContain('Token budget raised')
    expect(html).toContain('Discarded the partial answer already shown above.')
  })

  it('does not claim anything was discarded when nothing was', () => {
    const html = render(decision())
    expect(html).not.toContain('Discarded the partial answer')
  })

  it('does not render the routing block for ordinary events', () => {
    const html = render(makeEvent({ event_type: 'llm_call', phase_name: 'draft', input_tokens: 1, output_tokens: 2 }))
    expect(html).not.toContain('Provider fallback')
    expect(html).not.toContain('Route used')
  })
})

describe('TraceStepRow model chip', () => {
  it('shows the resolved model on a prompt_captured row', () => {
    const html = render(makeEvent({
      event_type: 'prompt_captured',
      phase_name: 'draft',
      resolved_model: 'claude-sonnet-4-6',
    }))
    expect(html).toContain('claude-sonnet-4-6')
  })

  it('shows the provider-reported model on an llm_call row', () => {
    const html = render(makeEvent({
      event_type: 'llm_call',
      phase_name: 'draft',
      input_tokens: 10,
      output_tokens: 20,
      response_data: { model_name: 'glm-4.7' },
    }))
    expect(html).toContain('glm-4.7')
  })

  it('renders no model chip when the event carries no model info', () => {
    const html = render(makeEvent({ event_type: 'phase_start', phase_name: 'draft' }))
    expect(html).not.toContain('trace-model-chip')
  })
})
