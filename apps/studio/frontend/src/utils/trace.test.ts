import { describe, expect, it } from 'vitest'

import type { CallbackEvent } from '../api/types'
import {
  countRouteDegradations,
  errorStack,
  eventColor,
  eventMessageIsRedundant,
  eventMessage,
  eventModelName,
  eventSeverity,
  eventPhase,
  eventTimeLabel,
  isRunScopedEvent,
  routeDecisionDetails,
  payloadPreview,
  retryBadge,
  RUN_SCOPE,
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

// The gateway emits llm_route_decision (graph_agent_gateway/events.py) for
// every candidate it skips, probes, retries, escalates, falls back from or
// answers on. The trace must surface it so a model comparison never silently
// reads "model A" results that model B produced, and so a call that took two
// minutes on the second-choice endpoint does not just look slow.
function decisionEvent(overrides: Partial<CallbackEvent> = {}): CallbackEvent {
  return event({
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
    voided_streamed_answer: false,
    code: '[F-v3-gateway-llm-route-decision]',
    ...overrides,
  })
}

describe('llm_route_decision visibility (trace-observability F7)', () => {
  it('renders a human-readable sentence per outcome instead of the raw event name', () => {
    expect(eventMessage(decisionEvent())).toBe('openai:gpt-4o failed → zhipu:glm-4.7')
    expect(eventMessage(decisionEvent({ decision: 'answered' }))).toBe('Answered by openai:gpt-4o')
    expect(eventMessage(decisionEvent({ decision: 'skipped_circuit_open' })))
      .toBe('Skipped openai:gpt-4o — circuit open')
    expect(eventMessage(decisionEvent({ decision: 'probe_failed' })))
      .toBe('Probe failed on openai:gpt-4o')
    expect(eventMessage(decisionEvent({ decision: 'retried_same_route' })))
      .toBe('Retrying openai:gpt-4o')
    expect(eventMessage(decisionEvent({ decision: 'escalated_budget' })))
      .toBe('Answer was cut off — retrying openai:gpt-4o with a bigger budget')
    expect(eventMessage(decisionEvent({ decision: 'failed_terminal' })))
      .toBe('openai:gpt-4o failed — no fallback allowed')
  })

  it('says the chain is exhausted when every candidate failed', () => {
    expect(eventMessage(decisionEvent({ decision: 'exhausted', route_id: null })))
      .toBe('No route left — every candidate failed')
  })

  // Severity is a property of the DECISION, not of the event type: the same
  // type reports the route that answered and the run that died.
  it('colors a degraded routing decision as a warning', () => {
    expect(eventColor(decisionEvent())).toBe('bg-warning')
    expect(eventColor(decisionEvent({ decision: 'retried_same_route' }))).toBe('bg-warning')
    expect(eventColor(decisionEvent({ decision: 'escalated_budget' }))).toBe('bg-warning')
  })

  it('leaves the route that answered uncoloured, so a healthy run stays monochrome', () => {
    expect(eventColor(decisionEvent({ decision: 'answered' }))).toBe('bg-muted-foreground/50')
    expect(eventSeverity(decisionEvent({ decision: 'answered' }))).toBe('normal')
  })

  it('colors a terminal routing failure as destructive, like any other run-killer', () => {
    expect(eventColor(decisionEvent({ decision: 'exhausted' }))).toBe('bg-destructive')
    expect(eventColor(decisionEvent({ decision: 'failed_terminal' }))).toBe('bg-destructive')
  })

  // Colour means severity, never kind (FRONTEND_UI_SPEC 2.2): a run that went
  // fine reads monochrome, so the one coloured dot is the one worth looking at.
  it('leaves every ordinary event kind uncoloured', () => {
    for (const eventType of ['phase_start', 'phase_end', 'run_ended', 'llm_call', 'prompt_captured', 'tool_call']) {
      expect(eventColor(event({ event_type: eventType }))).toBe('bg-muted-foreground/50')
    }
  })

  it('colors only failures as destructive', () => {
    expect(eventColor(event({ event_type: 'internal_error' }))).toBe('bg-destructive')
    expect(eventColor(event({ event_type: 'validation_fail' }))).toBe('bg-destructive')
  })

  it('extracts the route identity, reason and status code from the event', () => {
    const details = routeDecisionDetails(decisionEvent())
    expect(details).not.toBeNull()
    expect(details?.decision).toBe('fell_back')
    expect(details?.routeId).toBe('openai:gpt-4o')
    expect(details?.endpointId).toBe('openai')
    expect(details?.providerModelId).toBe('gpt-4o-2024-11-20')
    expect(details?.protocol).toBe('openai_compatible')
    expect(details?.nextRouteId).toBe('zhipu:glm-4.7')
    expect(details?.reason).toBe('RateLimitError: 429 too many requests')
    expect(details?.statusCode).toBe(429)
    expect(details?.voidedStreamedAnswer).toBe(false)
  })

  // Retrying is only possible AFTER a truncated answer has streamed, so the
  // panel is showing text the decision just threw away.
  it('reports that a decision discarded text the panel had already shown', () => {
    const details = routeDecisionDetails(
      decisionEvent({ decision: 'escalated_budget', voided_streamed_answer: true }),
    )
    expect(details?.voidedStreamedAnswer).toBe(true)
  })

  it('survives a decision that names no route at all', () => {
    const details = routeDecisionDetails(
      event({ event_type: 'llm_route_decision', phase_name: 'draft', decision: 'exhausted' }),
    )
    expect(details?.decision).toBe('exhausted')
    expect(details?.routeId).toBeNull()
    expect(details?.endpointId).toBeNull()
    expect(details?.providerModelId).toBeNull()
    expect(details?.statusCode).toBeNull()
    expect(details?.voidedStreamedAnswer).toBe(false)
  })

  // An outcome this build has never heard of must not be rendered as one it
  // has: the row prints the raw event instead of guessing a severity.
  it('refuses to interpret an unknown decision', () => {
    const unknown = decisionEvent({ decision: 'teleported' })
    expect(routeDecisionDetails(unknown)).toBeNull()
    expect(eventMessage(unknown)).toBe('llm_route_decision')
    expect(eventColor(unknown)).toBe('bg-muted-foreground/50')
  })

  it('returns null for events that are not routing decisions', () => {
    expect(routeDecisionDetails(event({ event_type: 'llm_call', phase_name: 'draft' }))).toBeNull()
  })

  // Every healthy call ends on `answered`, so counting it would put a permanent
  // warning badge on every run.
  it('counts the routing decisions that went the wrong way, not the ones that worked', () => {
    const events = [
      event({ event_type: 'phase_start', phase_name: 'draft' }),
      decisionEvent(),
      decisionEvent({ phase_name: 'review', decision: 'retried_same_route' }),
      decisionEvent({ phase_name: 'review', decision: 'answered' }),
      event({ event_type: 'llm_call', phase_name: 'draft' }),
    ]
    expect(countRouteDegradations(events)).toBe(2)
    expect(countRouteDegradations([decisionEvent({ decision: 'answered' })])).toBe(0)
    expect(countRouteDegradations([event({ event_type: 'phase_start' })])).toBe(0)
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

describe('eventPhase (which node an event belongs to)', () => {
  const ev = (partial: Partial<CallbackEvent> & { event_type: string }): CallbackEvent => ({
    schema_version: '1.0',
    timestamp: '2026-08-08T00:00:00Z',
    ...partial,
  } as CallbackEvent)

  it('uses the phase the event names', () => {
    expect(eventPhase(ev({ event_type: 'phase_start', phase_name: 'segment' }))).toBe('segment')
  })

  it('files an edge event under the node it dispatches into', () => {
    // input_dispatch / blackboard_reduce carry from_phase → to_phase instead of
    // phase_name; they describe what arrives at `to_phase`, so that is the node
    // they belong to. They used to fall through to a bucket called "system".
    expect(eventPhase(ev({ event_type: 'input_dispatch', from_phase: 'setup', to_phase: 'segment' }))).toBe('segment')
  })

  it('files run-level events under the run, never under a node named after the run id', () => {
    // run_started / run_ended belong to no node. Falling back to run_id turned a
    // 40-character id into a "node" — a filter chip and a document heading.
    expect(eventPhase(ev({ event_type: 'run_started', run_id: 'predict-a7b54afac9774857bf81a99e62fa284c' })))
      .toBe(RUN_SCOPE)
    expect(RUN_SCOPE).toBe('run')
  })

  it('tells run-scoped events apart from node events', () => {
    expect(isRunScopedEvent(ev({ event_type: 'run_ended', run_id: 'r1' }))).toBe(true)
    expect(isRunScopedEvent(ev({ event_type: 'phase_start', phase_name: 'segment' }))).toBe(false)
  })
})

describe('llm_call model', () => {
  it('names the model that answered', () => {
    expect(
      eventMessage({
        schema_version: '1.0',
        event_type: 'llm_call',
        timestamp: '2026-08-08T00:00:00Z',
        phase_name: 'review',
        resolved_model: 'deepseek-v4-flash',
      } as CallbackEvent),
    ).toBe('LLM call completed · deepseek-v4-flash')
  })

  it('stays generic when the provider reported no model', () => {
    expect(
      eventMessage({
        schema_version: '1.0',
        event_type: 'llm_call',
        timestamp: '2026-08-08T00:00:00Z',
        phase_name: 'review',
      } as CallbackEvent),
    ).toBe('LLM call completed')
  })
})

describe('redundant row messages', () => {
  const ev = (partial: Partial<CallbackEvent> & { event_type: string }): CallbackEvent => ({
    schema_version: '1.0',
    timestamp: '2026-08-08T00:00:00Z',
    ...partial,
  } as CallbackEvent)

  // A row prints the kind and then a sentence about it; when `eventMessage` has
  // no sentence for that kind it falls through to the kind itself, and the row
  // would say the same word twice (decision 2026-08-08 D3).
  it('spots the kinds whose message only repeats the kind', () => {
    for (const eventType of ['input_dispatch', 'agent_loop_iteration', 'run_started']) {
      expect(eventMessageIsRedundant(ev({ event_type: eventType }))).toBe(true)
    }
  })

  it('keeps a message that actually says something', () => {
    expect(eventMessageIsRedundant(ev({ event_type: 'phase_start', phase_name: 'segment' }))).toBe(false)
  })
})
