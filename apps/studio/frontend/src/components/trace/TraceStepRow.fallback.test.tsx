import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import type { CallbackEvent } from '../../api/types'
import { eventPhase } from '../../utils/trace'
import { TraceStepRow } from './TraceStepRow'

// trace-observability F7: a gateway llm_fallback event must render as an explicit
// amber "Provider fallback" block (models + reason), and rows that know which
// model served the call must surface it as a chip — so a run that silently
// degraded from model A to model B is visible at a glance.

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

describe('TraceStepRow llm_fallback rendering', () => {
  const fallback = makeEvent({
    event_type: 'llm_fallback',
    phase_name: 'draft',
    from_provider: 'openai:gpt-4o',
    to_provider: 'zhipu:glm-4.7',
    reason: 'RateLimitError: 429 too many requests',
    context: {
      role_name: 'graph_agent',
      provider_status_code: 429,
      from_route: { route_id: 'openai:gpt-4o', provider_model_id: 'gpt-4o-2024-11-20' },
      to_route: { route_id: 'zhipu:glm-4.7', provider_model_id: 'glm-4.7' },
    },
  })

  it('renders an explicit Provider fallback block with both models and the reason', () => {
    const html = render(fallback)
    expect(html).toContain('Provider fallback')
    expect(html).toContain('gpt-4o-2024-11-20')
    expect(html).toContain('glm-4.7')
    expect(html).toContain('RateLimitError: 429 too many requests')
  })

  it('labels an exhausted chain when no route remains', () => {
    const html = render(makeEvent({
      event_type: 'llm_fallback',
      phase_name: 'draft',
      from_provider: 'openai:gpt-4o',
      to_provider: '<none>',
      reason: 'AuthenticationError: 401',
    }))
    expect(html).toContain('no remaining route')
  })

  it('does not render the fallback block for ordinary events', () => {
    const html = render(makeEvent({ event_type: 'llm_call', phase_name: 'draft', input_tokens: 1, output_tokens: 2 }))
    expect(html).not.toContain('Provider fallback')
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
