import { describe, expect, it } from 'vitest'

import type { CallbackEvent } from '../api/types'
import { ENGINE_EVENT_TYPES } from './engine-event-types'
import {
  countRouteDegradations,
  eventColor,
  eventFacts,
  machineryNarration,
  promptMessages,
  eventHeadline,
  eventModelName,
  eventSeverity,
  eventPhase,
  eventTimeLabel,
  isRunScopedEvent,
  routeDecisionDetails,
  RUN_SCOPE,
  toolCallSummary,
} from './trace'

function event(partial: Partial<CallbackEvent> & { event_type: string }): CallbackEvent {
  return {
    schema_version: '1.0',
    timestamp: '2026-06-14T00:00:00Z',
    ...partial,
  } as CallbackEvent
}

describe('toolCallSummary (D1/P2 agent tool-call folding, n4-trace #16/#24)', () => {
  it('returns null for events that are not tool_call', () => {
    expect(toolCallSummary(event({ event_type: 'llm_call', phase_name: 'draft' }))).toBeNull()
    expect(toolCallSummary(event({ event_type: 'phase_start' }))).toBeNull()
  })

  it('folds a Read tool_call under the Explored verb', () => {
    const summary = toolCallSummary(event({ event_type: 'tool_call', tool_name: 'Read', args: { path: 'a.py' }, result: 'ok' }))
    expect(summary?.verb).toBe('explored')
    expect(summary?.toolName).toBe('Read')
  })

  it('folds a Write/Edit tool_call under the Worked verb and a Bash call under Ran', () => {
    expect(toolCallSummary(event({ event_type: 'tool_call', tool_name: 'Write', result: '' }))?.verb).toBe('worked')
    expect(toolCallSummary(event({ event_type: 'tool_call', tool_name: 'Edit', result: '' }))?.verb).toBe('worked')
    expect(toolCallSummary(event({ event_type: 'tool_call', tool_name: 'Bash', result: '' }))?.verb).toBe('ran')
  })

  it('falls back to a generic verb for an unknown tool name', () => {
    expect(toolCallSummary(event({ event_type: 'tool_call', tool_name: 'CustomTool', result: '' }))?.verb).toBe('called')
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

  it('rounds the duration to whole milliseconds when duration_ms is present', () => {
    const summary = toolCallSummary(event({ event_type: 'tool_call', tool_name: 'Read', result: '', duration_ms: 12.7 }))
    expect(summary?.durationMs).toBe(13)
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
  it('hands the row the decision itself, for the copy exit to word', () => {
    for (const decision of [
      'answered', 'skipped_circuit_open', 'probe_failed', 'retried_same_route',
      'escalated_budget', 'failed_terminal', 'fell_back',
    ]) {
      const headline = eventHeadline(decisionEvent({ decision }))
      expect(headline.kind).toBe('routeDecision')
      expect(headline.kind === 'routeDecision' && headline.details.decision).toBe(decision)
    }
  })

  // Runtime settings are preferences: a provider that will not take one still
  // answers, and the reader has to be told the answer was produced without it.
  it('says when an answer came back without the settings that were asked for', () => {
    const headline = eventHeadline(decisionEvent({ decision: 'dropped_rejected_settings' }))
    expect(headline.kind === 'routeDecision' && headline.details.decision)
      .toBe('dropped_rejected_settings')
    expect(eventColor(decisionEvent({ decision: 'dropped_rejected_settings' })))
      .toBe('bg-warning')
  })

  it('says the chain is exhausted when every candidate failed', () => {
    const headline = eventHeadline(decisionEvent({ decision: 'exhausted', route_id: null }))
    expect(headline.kind === 'routeDecision' && headline.details.decision).toBe('exhausted')
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
    expect(eventColor(event({ event_type: 'protocol_violation', phase_name: 'draft' }))).toBe('bg-destructive')
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
    expect(eventHeadline(unknown).kind).toBe('nothingToAdd')
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

  it('reads the provider-reported model_name from llm_call response_data', () => {
    const model = eventModelName(
      event({ event_type: 'llm_call', phase_name: 'draft', response_data: { model_name: 'glm-4.7' } }),
    )
    expect(model).toBe('glm-4.7')
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
      eventHeadline({
        schema_version: '1.0',
        event_type: 'llm_call',
        timestamp: '2026-08-08T00:00:00Z',
        phase_name: 'review',
        resolved_model: 'deepseek-v4-flash',
      } as CallbackEvent),
    ).toEqual({ kind: 'llmCallCompleted', model: 'deepseek-v4-flash' })
  })

  it('stays generic when the provider reported no model', () => {
    expect(
      eventHeadline({
        schema_version: '1.0',
        event_type: 'llm_call',
        timestamp: '2026-08-08T00:00:00Z',
        phase_name: 'review',
      } as CallbackEvent),
    ).toEqual({ kind: 'llmCallCompleted', model: null })
  })
})

describe('redundant row messages', () => {
  const ev = (partial: Partial<CallbackEvent> & { event_type: string }): CallbackEvent => ({
    schema_version: '1.0',
    timestamp: '2026-08-08T00:00:00Z',
    ...partial,
  } as CallbackEvent)

  // A row prints the kind and then a sentence about it; a kind this build
  // has no statement for would make the row say the same word twice
  // (decision 2026-08-08 D3), so it says so instead of inventing one.
  it('spots the kinds that have nothing to add beyond the kind', () => {
    for (const eventType of ['input_dispatch', 'agent_loop_iteration', 'run_started']) {
      expect(eventHeadline(ev({ event_type: eventType })).kind).toBe('nothingToAdd')
    }
  })

  it('keeps a statement that actually says something', () => {
    expect(eventHeadline(ev({ event_type: 'phase_start', phase_name: 'segment' })))
      .toEqual({ kind: 'phaseStarted', phase: 'segment' })
  })
})

describe('every machinery step says what it did (glass-box D4)', () => {
  function ev(payload: Partial<CallbackEvent>): CallbackEvent {
    return { schema_version: '1.0', timestamp: '2026-08-20T00:00:00Z', ...payload } as CallbackEvent
  }

  it('folds the single-sentence channels into the narration, not just the list ones', () => {
    // The engine says what a decision was in `message` (D4: "带完整句子的
    // message"), and only two of its 37 event classes carry the list channels.
    // Reading only the lists sent every other decision to the raw payload.
    expect(machineryNarration(ev({
      event_type: 'loop_detected', phase_name: 'work', tool_name: 'search', count: 3,
      message: 'Broke a no-progress loop on search after 3 identical results.',
    }))?.details).toContain('Broke a no-progress loop on search after 3 identical results.')
  })

  it('puts a swallowed exception among the problems, not the narration', () => {
    const narration = machineryNarration(ev({
      event_type: 'tool_error_handled', phase_name: 'work', tool_name: 'fetch',
      error: 'TimeoutError: timed out', message: 'Turned a fetch failure into model feedback.',
    }))

    expect(narration?.problems).toContain('TimeoutError: timed out')
    expect(narration?.details).toContain('Turned a fetch failure into model feedback.')
  })

  it('names the numbers a machinery step turned on', () => {
    expect(eventFacts(ev({
      event_type: 'tool_history_repaired', phase_name: 'work',
      synthesized_count: 2, dropped_count: 1, message: 'Repaired the history.',
    }))).toEqual([
      { label: 'synthesized', value: { kind: 'data', text: '2' } },
      { label: 'dropped', value: { kind: 'data', text: '1' } },
    ])
  })

  it('reads a transition as the transition it was', () => {
    expect(eventFacts(ev({
      event_type: 'input_dispatch', from_phases: ['draft'], to_phase: 'review',
      dispatched_keys: ['topic', 'draft'], changed_keys: ['draft'],
    }))).toEqual([
      { label: 'transition', value: { kind: 'transition', ends: { from: ['draft'], to: 'review' } } },
      { label: 'dispatched', value: { kind: 'data', text: 'topic, draft' } },
      { label: 'changed', value: { kind: 'data', text: 'draft' } },
    ])
  })

  it('says whether the loop stopped without making the reader parse the decision name', () => {
    expect(eventFacts(ev({
      event_type: 'agent_exit_decision', decision: 'exit_success', iteration: 2,
    }))).toEqual([
      { label: 'outcome', value: { kind: 'word', word: 'phaseEnded' } },
      { label: 'iteration', value: { kind: 'data', text: '2' } },
    ])
    expect(eventFacts(ev({
      event_type: 'agent_exit_decision', decision: 'continue_nudged', iteration: 1,
    }))).toEqual([
      { label: 'outcome', value: { kind: 'word', word: 'loopContinues' } },
      { label: 'iteration', value: { kind: 'data', text: '1' } },
    ])
  })

  it('has a reading for every event the engine can emit', () => {
    // The point of the whole unit: a type with neither a sentence nor facts is
    // exactly the silent raw-JSON fallback this replaces. If the engine adds an
    // event, this fails until someone gives it a reading.
    const unread = ENGINE_EVENT_TYPES.filter((type) => eventFacts(ev({ event_type: type })) === null)

    expect(unread).toEqual([])
  })
})

describe('a prompt says where each part of it came from', () => {
  function ev(payload: Partial<CallbackEvent>): CallbackEvent {
    return { schema_version: '1.0', timestamp: '2026-08-20T00:00:00Z', ...payload } as CallbackEvent
  }

  it('splits the sent messages by who spoke', () => {
    expect(promptMessages(ev({
      event_type: 'prompt_captured',
      resolved_prompt: [
        { role: 'system', content: 'you are an analyst' },
        { role: 'human', content: 'summarize this' },
      ],
    }))).toEqual([
      { role: 'System', text: 'you are an analyst' },
      { role: 'User', text: 'summarize this' },
    ])
  })

  it('names a role it has no friendly word for rather than dropping the message', () => {
    expect(promptMessages(ev({
      event_type: 'prompt_captured',
      resolved_prompt: [{ role: 'tool', content: 'result' }],
    }))).toEqual([{ role: 'tool', text: 'result' }])
  })

  it('keeps a structured content block readable instead of "[object Object]"', () => {
    const messages = promptMessages(ev({
      event_type: 'prompt_captured',
      resolved_prompt: [{ role: 'human', content: [{ type: 'text', text: 'hello' }] }],
    }))

    expect(messages[0].text).toContain('hello')
    expect(messages[0].text).not.toContain('[object Object]')
  })

  it('is empty when the call carried no messages, rather than inventing one', () => {
    expect(promptMessages(ev({ event_type: 'prompt_captured' }))).toEqual([])
  })
})

// The engine states a phase execution's outcome on `phase_end` (engine
// observability OB13). The canvas believes it and the run report believes it;
// this panel was the third reader, and it printed "Phase finished: impossible"
// under a run that died in that very phase (real machine, run
// 2026-08-20T17-13-16_4e586d15, ledger E17).
describe('a phase_end row says how the phase ended', () => {
  it('names the outcome in the sentence, not just that it stopped', () => {
    expect(eventHeadline(event({ event_type: 'phase_end', phase_name: 'impossible', status: 'failed' })))
      .toEqual({ kind: 'phaseFailed', phase: 'impossible' })
    expect(eventHeadline(event({ event_type: 'phase_end', phase_name: 'draft', status: 'completed' })))
      .toEqual({ kind: 'phaseFinished', phase: 'draft' })
  })

  it('mirrors the outcome in the fact table, the way run_ended does', () => {
    expect(eventFacts(event({
      event_type: 'phase_end', phase_name: 'impossible', phase_execution_id: 'b29e2df598cf', status: 'failed',
    }))).toEqual([
      { label: 'outcome', value: { kind: 'data', text: 'failed' } },
      { label: 'execution', value: { kind: 'data', text: 'b29e2df598cf' } },
    ])
  })

  // Severity reads the event, not its type — the same rule the canvas applies
  // in `run-status-projection`: an event that reports its own outcome is
  // believed. One rule, so a failed phase and a crashed run both earn the dot
  // without either being special-cased by type.
  it('earns the one coloured dot on the rail', () => {
    expect(eventSeverity(event({ event_type: 'phase_end', phase_name: 'impossible', status: 'failed' }))).toBe('error')
    expect(eventColor(event({ event_type: 'phase_end', phase_name: 'impossible', status: 'failed' }))).toBe('bg-destructive')
    expect(eventSeverity(event({ event_type: 'run_ended', status: 'crashed' }))).toBe('error')
    expect(eventSeverity(event({ event_type: 'phase_end', phase_name: 'draft', status: 'completed' }))).toBe('normal')
    expect(eventSeverity(event({ event_type: 'run_ended', status: 'completed' }))).toBe('normal')
  })
})
