import { describe, expect, it } from 'vitest'

import type { CallbackEvent } from '../api/types'
import {
  countLlmFallbacks,
  errorStack,
  eventColor,
  eventMessage,
  eventModelName,
  eventTimeLabel,
  findPromptEvent,
  llmFallbackDetails,
  payloadPreview,
  retryBadge,
  runOutcomeFromEvents,
  toolCallSummary,
} from './trace'

function event(partial: Partial<CallbackEvent> & { event_type: string }): CallbackEvent {
  return {
    schema_version: '1.0',
    timestamp: '2026-06-14T00:00:00Z',
    ...partial,
  } as CallbackEvent
}

describe('findPromptEvent (D8 prompt 回溯)', () => {
  it('returns the selected event itself when it is a prompt_captured event', () => {
    const events = [
      event({ event_type: 'phase_start', phase_name: 'draft' }),
      event({ event_type: 'prompt_captured', phase_name: 'draft', template_source: 'tpl' }),
    ]
    expect(findPromptEvent(events, 1)).toBe(events[1])
  })

  it('walks back to the nearest prompt_captured in the same phase when an llm_call is selected', () => {
    const events = [
      event({ event_type: 'prompt_captured', phase_name: 'draft', template_source: 'draft-tpl' }),
      event({ event_type: 'prompt_captured', phase_name: 'review', template_source: 'review-tpl' }),
      event({ event_type: 'llm_call', phase_name: 'review' }),
    ]
    // Selecting the llm_call (index 2) must resolve to the review-phase prompt, not draft.
    expect(findPromptEvent(events, 2)).toBe(events[1])
  })

  it('falls back to the llm_call event itself when no prompt_captured precedes it', () => {
    const events = [
      event({ event_type: 'phase_start', phase_name: 'solo' }),
      event({ event_type: 'llm_call', phase_name: 'solo' }),
    ]
    expect(findPromptEvent(events, 1)).toBe(events[1])
  })

  it('returns null for a non-inspectable event with no upstream prompt', () => {
    const events = [event({ event_type: 'phase_start', phase_name: 'draft' })]
    expect(findPromptEvent(events, 0)).toBeNull()
  })

  it('returns null when the index is out of range', () => {
    expect(findPromptEvent([], 0)).toBeNull()
  })
})

describe('retryBadge (D10 validator retry nudge)', () => {
  it('returns null for events that carry no attempt information', () => {
    expect(retryBadge(event({ event_type: 'phase_start' }))).toBeNull()
  })

  it('derives an attempt/limit badge from attempt + max_attempts', () => {
    const badge = retryBadge(event({ event_type: 'validation_fail', attempt: 2, max_attempts: 3 }))
    expect(badge).not.toBeNull()
    expect(badge?.label).toBe('2/3')
    expect(badge?.exhausted).toBe(false)
  })

  it('reads retry_count and max_retries when attempt fields are absent', () => {
    const badge = retryBadge(event({ event_type: 'validation_fail', retry_count: 1, max_retries: 3 }))
    // retry_count is zero-based attempts already spent → human-facing attempt is +1.
    expect(badge?.label).toBe('2/3')
  })

  it('flags the badge as exhausted when the final attempt is reached', () => {
    const badge = retryBadge(event({ event_type: 'validation_fail', attempt: 3, max_attempts: 3 }))
    expect(badge?.exhausted).toBe(true)
  })

  it('reads nested attempt info from metadata when not at the top level', () => {
    const badge = retryBadge(
      event({ event_type: 'validation_fail', metadata: { attempt: 1, max_attempts: 2 } }),
    )
    expect(badge?.label).toBe('1/2')
  })

  it('shows a bare attempt count when no limit is known', () => {
    const badge = retryBadge(event({ event_type: 'validation_fail', attempt: 2 }))
    expect(badge?.label).toBe('#2')
    expect(badge?.exhausted).toBe(false)
  })
})

describe('toolCallSummary (D1/P2 agent tool-call folding, n4-trace #16/#24)', () => {
  it('returns null for events that are not tool_call', () => {
    expect(toolCallSummary(event({ event_type: 'llm_call', phase_name: 'draft' }))).toBeNull()
    expect(toolCallSummary(event({ event_type: 'phase_start' }))).toBeNull()
  })

  it('folds a Read tool_call under the Explored verb', () => {
    const summary = toolCallSummary(event({ event_type: 'tool_call', tool_name: 'Read', args: { path: 'a.py' }, result: 'ok' }))
    expect(summary?.verb).toBe('Explored')
    expect(summary?.headline).toBe('Explored · Read')
  })

  it('folds a Write/Edit tool_call under the Worked verb and a Bash call under Ran', () => {
    expect(toolCallSummary(event({ event_type: 'tool_call', tool_name: 'Write', result: '' }))?.verb).toBe('Worked')
    expect(toolCallSummary(event({ event_type: 'tool_call', tool_name: 'Edit', result: '' }))?.verb).toBe('Worked')
    expect(toolCallSummary(event({ event_type: 'tool_call', tool_name: 'Bash', result: '' }))?.verb).toBe('Ran')
  })

  it('falls back to a generic verb for an unknown tool name', () => {
    expect(toolCallSummary(event({ event_type: 'tool_call', tool_name: 'CustomTool', result: '' }))?.verb).toBe('Called')
  })

  it('serializes args and trims an oversized result for the subtree summary', () => {
    const summary = toolCallSummary(
      event({ event_type: 'tool_call', tool_name: 'Bash', args: { cmd: 'ls' }, result: 'l1\nl2\nl3\nl4\nl5\nl6' }),
    )
    expect(summary?.args).toContain('"cmd": "ls"')
    // Only the leading lines are kept, with an ellipsis marker appended.
    expect(summary?.resultSummary).toContain('l4')
    expect(summary?.resultSummary).not.toContain('l6')
    expect(summary?.resultSummary).toContain('…')
  })

  it('exposes a rounded duration label when duration_ms is present', () => {
    const summary = toolCallSummary(event({ event_type: 'tool_call', tool_name: 'Read', result: '', duration_ms: 12.7 }))
    expect(summary?.durationLabel).toBe('13 ms')
  })
})

describe('errorStack (D10 retry-exhausted error stack, n4-trace #25)', () => {
  it('returns the final_errors list for a retry_exhausted event', () => {
    const stack = errorStack(
      event({ event_type: 'retry_exhausted', max_retries: 3, final_errors: ['schema mismatch', 'missing field x'] }),
    )
    expect(stack).toEqual(['schema mismatch', 'missing field x'])
  })

  it('returns the per-attempt errors list for a validation_fail event', () => {
    const stack = errorStack(event({ event_type: 'validation_fail', errors: ['line 3 invalid'], retry_count: 1 }))
    expect(stack).toEqual(['line 3 invalid'])
  })

  it('drops non-string and blank entries from the error list', () => {
    const stack = errorStack(
      event({ event_type: 'retry_exhausted', final_errors: ['real', '', '   ', 7 as unknown as string] }),
    )
    expect(stack).toEqual(['real'])
  })

  it('returns an empty array for events that are neither failure type', () => {
    expect(errorStack(event({ event_type: 'phase_end', phase_name: 'draft' }))).toEqual([])
  })
})

describe('payloadPreview (D1 / §4 default-collapse big payloads)', () => {
  it('returns the full serialized payload untruncated when it is under the auto-expand limit', () => {
    const preview = payloadPreview(event({ event_type: 'phase_start', phase_name: 'draft' }))
    expect(preview.truncated).toBe(false)
    expect(preview.text).toContain('phase_start')
    expect(preview.sizeBytes).toBeGreaterThan(0)
  })

  it('marks the payload as truncated once it exceeds the ~2KB auto-expand limit', () => {
    const bigText = 'x'.repeat(4000)
    const preview = payloadPreview(event({ event_type: 'llm_call', big_field: bigText }))
    expect(preview.truncated).toBe(true)
    expect(preview.sizeBytes).toBeGreaterThan(2048)
    // The collapsed preview text must be shorter than the full payload.
    expect(preview.text.length).toBeLessThan(JSON.stringify(event({ event_type: 'llm_call', big_field: bigText }), null, 2).length)
  })

  it('reports a human-readable size label in kilobytes', () => {
    const bigText = 'y'.repeat(4000)
    const preview = payloadPreview(event({ event_type: 'llm_call', big_field: bigText }))
    expect(preview.sizeLabel).toMatch(/KB$/)
  })
})

// The gateway emits llm_fallback (graph_agent_gateway/events.py) when a provider
// route fails and a peer-group fallback takes over. The trace must surface it so
// a model comparison never silently reads "model A" results that model B produced.
function fallbackEvent(overrides: Partial<CallbackEvent> = {}): CallbackEvent {
  return event({
    event_type: 'llm_fallback',
    phase_name: 'draft',
    from_provider: 'openai:gpt-4o',
    to_provider: 'zhipu:glm-4.7',
    reason: 'RateLimitError: 429 too many requests',
    code: '[F-v3-gateway-llm-fallback]',
    context: {
      role_name: 'graph_agent',
      fallback_decision: 'fallback_allowed',
      error_type: 'RateLimitError',
      provider_status_code: 429,
      from_route: {
        route_id: 'openai:gpt-4o',
        endpoint_id: 'openai',
        provider_model_id: 'gpt-4o-2024-11-20',
        canonical_id: 'gpt-4o',
        protocol: 'openai',
      },
      to_route: {
        route_id: 'zhipu:glm-4.7',
        endpoint_id: 'zhipu',
        provider_model_id: 'glm-4.7',
        canonical_id: 'glm-4.7',
        protocol: 'openai',
      },
    },
    ...overrides,
  })
}

describe('llm_fallback visibility (trace-observability F7)', () => {
  it('renders a human-readable fallback message instead of the raw event name', () => {
    expect(eventMessage(fallbackEvent())).toBe('LLM fallback: openai:gpt-4o → zhipu:glm-4.7')
  })

  it('says the chain is exhausted when the gateway reports no remaining route', () => {
    const message = eventMessage(fallbackEvent({ to_provider: '<none>' }))
    expect(message).toBe('LLM fallback: openai:gpt-4o failed — no remaining route')
  })

  it('colors the fallback timeline dot as a warning', () => {
    expect(eventColor('llm_fallback')).toBe('bg-warning')
  })

  it('extracts provider ids, models, reason and status code from the event', () => {
    const details = llmFallbackDetails(fallbackEvent())
    expect(details).not.toBeNull()
    expect(details?.fromProvider).toBe('openai:gpt-4o')
    expect(details?.toProvider).toBe('zhipu:glm-4.7')
    expect(details?.fromModel).toBe('gpt-4o-2024-11-20')
    expect(details?.toModel).toBe('glm-4.7')
    expect(details?.reason).toBe('RateLimitError: 429 too many requests')
    expect(details?.roleName).toBe('graph_agent')
    expect(details?.statusCode).toBe(429)
    expect(details?.exhausted).toBe(false)
  })

  it('marks the "<none>" next candidate as exhausted with a null toProvider', () => {
    const details = llmFallbackDetails(fallbackEvent({ to_provider: '<none>' }))
    expect(details?.exhausted).toBe(true)
    expect(details?.toProvider).toBeNull()
  })

  it('survives a fallback event with no context payload', () => {
    const details = llmFallbackDetails(
      event({ event_type: 'llm_fallback', phase_name: 'draft', from_provider: 'a', to_provider: 'b', reason: 'x' }),
    )
    expect(details?.fromModel).toBeNull()
    expect(details?.toModel).toBeNull()
    expect(details?.roleName).toBeNull()
    expect(details?.statusCode).toBeNull()
  })

  it('returns null for non-fallback events', () => {
    expect(llmFallbackDetails(event({ event_type: 'llm_call', phase_name: 'draft' }))).toBeNull()
  })

  it('counts the fallback events in a trace', () => {
    const events = [
      event({ event_type: 'phase_start', phase_name: 'draft' }),
      fallbackEvent(),
      fallbackEvent({ phase_name: 'review' }),
      event({ event_type: 'llm_call', phase_name: 'draft' }),
    ]
    expect(countLlmFallbacks(events)).toBe(2)
    expect(countLlmFallbacks([event({ event_type: 'phase_start' })])).toBe(0)
  })
})

describe('eventModelName (which model a call actually used)', () => {
  it('reads resolved_model from prompt_captured', () => {
    const model = eventModelName(
      event({ event_type: 'prompt_captured', phase_name: 'draft', resolved_model: 'claude-sonnet-4-6' }),
    )
    expect(model).toBe('claude-sonnet-4-6')
  })

  it('reads resolved_model from model_resolved', () => {
    const model = eventModelName(
      event({ event_type: 'model_resolved', phase_name: 'draft', resolved_model: 'gpt-4o', role_name: 'writer' }),
    )
    expect(model).toBe('gpt-4o')
  })

  it('reads the provider-reported model_name from llm_call response_data', () => {
    const model = eventModelName(
      event({ event_type: 'llm_call', phase_name: 'draft', response_data: { model_name: 'glm-4.7' } }),
    )
    expect(model).toBe('glm-4.7')
  })

  it('renders the model into the model_resolved timeline message', () => {
    expect(eventMessage(event({ event_type: 'model_resolved', phase_name: 'draft', resolved_model: 'gpt-4o' })))
      .toBe('Model resolved: gpt-4o')
  })

  it('returns null when the model is missing or blank', () => {
    expect(eventModelName(event({ event_type: 'prompt_captured', phase_name: 'draft' }))).toBeNull()
    expect(eventModelName(event({ event_type: 'prompt_captured', phase_name: 'draft', resolved_model: '' }))).toBeNull()
    expect(eventModelName(event({ event_type: 'llm_call', phase_name: 'draft' }))).toBeNull()
    expect(eventModelName(event({ event_type: 'phase_start', phase_name: 'draft' }))).toBeNull()
  })
})

describe('eventTimeLabel (timeline rows carry the wall-clock time)', () => {
  it('formats a valid ISO timestamp as local HH:MM:SS', () => {
    const label = eventTimeLabel(event({ event_type: 'phase_start', timestamp: '2026-06-14T08:05:09Z' }))
    expect(label).toMatch(/^\d{2}:\d{2}:\d{2}$/)
  })

  it('returns null for a missing or unparseable timestamp', () => {
    expect(eventTimeLabel(event({ event_type: 'phase_start', timestamp: 'not-a-date' }))).toBeNull()
    expect(eventTimeLabel({ schema_version: '1.0', event_type: 'phase_start' } as never)).toBeNull()
  })
})

describe('runOutcomeFromEvents', () => {
  const event = (partial: Partial<CallbackEvent> & { event_type: string }): CallbackEvent => ({
    schema_version: '1.0',
    timestamp: '2026-08-08T00:00:00Z',
    ...partial,
  } as CallbackEvent)

  it('reports running while no run_ended has arrived', () => {
    expect(runOutcomeFromEvents([event({ event_type: 'phase_start' })])).toBe('running')
  })

  it('reads the verdict off run_ended', () => {
    expect(runOutcomeFromEvents([event({ event_type: 'run_ended', status: 'completed' })])).toBe('success')
    expect(runOutcomeFromEvents([event({ event_type: 'run_ended', status: 'crashed' })])).toBe('failed')
    expect(runOutcomeFromEvents([event({ event_type: 'run_ended', status: 'interrupted' })])).toBe('interrupted')
  })

  it('treats a run_ended with no status as a completed run', () => {
    expect(runOutcomeFromEvents([event({ event_type: 'run_ended' })])).toBe('success')
  })
})
