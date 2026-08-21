import { describe, expect, it } from 'vitest'
import i18n from '../../i18n'
import type { CallbackEvent } from '../../api/types'
import {
  ROUTE_DECISIONS,
  SETTING_VERDICTS,
  eventFacts,
  eventHeadline,
  toolCallSummary,
  type RouteDecisionDetails,
} from '../../utils/trace'
import { ENGINE_EVENT_TYPES } from '../../utils/engine-event-types'
import {
  factLabelText,
  factValueText,
  toolCallHeadline,
  traceHeadlineText,
  transitionText,
  type TraceCopy,
} from './trace-copy'

/**
 * Every word the trace panel says, in both languages.
 *
 * `utils/trace.ts` returns descriptors and this module turns them into
 * sentences, so a missing phrase does not fail to compile — it renders as its
 * own key, which looks like text and passes every structural test. These cases
 * therefore drive the SAME descriptors the panel produces through the SAME
 * exit and assert nothing comes back looking like a key.
 */
const LANGUAGES = ['en', 'zh-CN'] as const

function copyFor(language: (typeof LANGUAGES)[number]): TraceCopy {
  // Same narrowing the panel does (`useTraceCopy`): these keys are built
  // from descriptors, which i18next's literal key type cannot express.
  return i18n.getFixedT(language, ['trace', 'canvas']) as unknown as TraceCopy
}

/** A rendered phrase must not be the key that asked for it, nor empty. */
function expectSaidSomething(text: string, key: string): void {
  expect(text, `${key} rendered as its own key`).not.toBe(key)
  expect(text.trim(), `${key} rendered blank`).not.toBe('')
}

function event(partial: Partial<CallbackEvent> & { event_type: string }): CallbackEvent {
  return { schema_version: '1.0', timestamp: '2026-08-21T00:00:00Z', ...partial } as CallbackEvent
}

function decisionEvent(decision: RouteDecisionDetails['decision']): CallbackEvent {
  return event({
    event_type: 'llm_route_decision',
    phase_name: 'draft',
    decision,
    route_id: 'openai:gpt-4o',
    next_route_id: 'zhipu:glm-4.7',
    endpoint_id: 'openai-official',
    provider_model_id: 'gpt-4o',
  })
}

describe.each(LANGUAGES)('the trace speaks %s', (language) => {
  const t = copyFor(language)

  it('has a sentence for every headline a row can carry', () => {
    const headlines = [
      event({ event_type: 'predict_chain_start' }),
      event({ event_type: 'phase_start', phase_name: 'draft' }),
      event({ event_type: 'phase_end', phase_name: 'draft', status: 'failed' }),
      event({ event_type: 'phase_end', phase_name: 'draft', status: 'completed' }),
      event({ event_type: 'edge_start', from_phases: ['draft'], to_phase: 'review' }),
      event({ event_type: 'edge_end', from_phases: [], to_phase: 'review' }),
      event({ event_type: 'prompt_captured', template_source: 'v030' }),
      event({ event_type: 'prompt_captured' }),
      event({ event_type: 'llm_call', resolved_model: 'gpt-4o' }),
      event({ event_type: 'llm_call' }),
      event({ event_type: 'run_ended', status: 'completed' }),
    ]

    for (const source of headlines) {
      const text = traceHeadlineText(eventHeadline(source), t)
      expectSaidSomething(text, source.event_type)
    }
  })

  it('has a sentence for every routing decision the gateway can report', () => {
    for (const decision of ROUTE_DECISIONS) {
      const text = traceHeadlineText(eventHeadline(decisionEvent(decision)), t)
      expectSaidSomething(text, decision)
      // The route's own name is data, and must survive into the sentence.
      if (decision !== 'exhausted') {
        expect(text).toContain('openai:gpt-4o')
      }
    }
  })

  it('has a word for every verdict a runtime setting can get', () => {
    for (const verdict of SETTING_VERDICTS) {
      expectSaidSomething(t(`settings.${verdict}`), `settings.${verdict}`)
    }
  })

  it('has a verb for every tool class', () => {
    for (const [tool, expectedVerb] of [['Read', 'explored'], ['Write', 'worked'], ['Bash', 'ran'], ['Fetch', 'called']]) {
      const summary = toolCallSummary(event({ event_type: 'tool_call', tool_name: tool, result: 'ok' }))
      expect(summary?.verb).toBe(expectedVerb)
      const headline = toolCallHeadline(summary!, t)
      expectSaidSomething(headline, expectedVerb)
      expect(headline).toContain(tool)
    }
  })

  it('has a label for every fact any engine event can turn on', () => {
    for (const eventType of ENGINE_EVENT_TYPES) {
      // Every field the reader could see, so the fact table is exercised whole
      // rather than only where a bare event happens to carry values.
      const facts = eventFacts(event({
        event_type: eventType,
        phase_name: 'draft',
        from_phases: ['draft'],
        to_phase: 'review',
        status: 'completed',
        decision: 'exit_success',
        is_resume: true,
      })) ?? []
      for (const fact of facts) {
        expectSaidSomething(factLabelText(fact, t), `fact.${fact.label}`)
        expect(factValueText(fact.value, t).trim()).not.toBe('')
      }
    }
  })

  it('has a word for every judgement a fact value can be', () => {
    for (const word of ['yes', 'no', 'phaseEnded', 'loopContinues'] as const) {
      expectSaidSomething(t(`factValue.${word}`), `factValue.${word}`)
    }
  })

  it('calls a transition from the graph boundary what the canvas calls it', () => {
    // Not a second copy of the word: the same `canvas:boundary.input` entry the
    // Input node itself is drawn with, so the two can never drift.
    const fromBoundary = transitionText({ from: [], to: 'draft' }, t)
    expect(fromBoundary).toBe(`${t('canvas:boundary.input')} → draft`)
    expect(transitionText({ from: ['a', 'b'], to: 'c' }, t)).toBe('a + b → c')
  })
})

describe('the engine keeps its own words', () => {
  it('passes a machinery sentence through untranslated', () => {
    const text = traceHeadlineText(
      eventHeadline(event({ event_type: 'nudge', message: 'Nudged the agent back on task.' })),
      copyFor('zh-CN'),
    )

    expect(text).toBe('Nudged the agent back on task.')
  })

  it('says nothing at all for a kind that would only repeat itself', () => {
    expect(traceHeadlineText(eventHeadline(event({ event_type: 'run_started' })), copyFor('en'))).toBe('')
  })
})
