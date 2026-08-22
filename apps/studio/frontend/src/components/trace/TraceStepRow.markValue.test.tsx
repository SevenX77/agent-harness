import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import type { CallbackEvent } from '../../api/types'
import { eventPhase } from '../../utils/trace'
import { TraceStepRow } from './TraceStepRow'
import { TraceMarkTermProvider } from './trace-mark-term'

/**
 * A row that matched has to show WHY it matched — F13:「一个看不出理由的命中,
 * 比没有命中更坏」(trace-observability/mvp1-alignment.md).
 *
 * Several of these rows print a value inside a sentence this app wrote —
 * `endpoint: {{id}}`, `HTTP {{status}}`, `Loaded — {{path}}`. Marking the whole
 * sentence would light up our own vocabulary; marking none of it left the
 * reader with a hit and no reason. Measured on the real app before this fix:
 * searching an endpoint id over a 179-step run kept 27 steps and put a mark on
 * 6 — the other 21 showed nothing, expanded or not.
 */

function makeEvent(partial: Partial<CallbackEvent> & { event_type: string }): CallbackEvent {
  return {
    schema_version: '1.0',
    timestamp: '2026-07-16T00:00:00Z',
    ...partial,
  } as CallbackEvent
}

/**
 * An LLM-call step carrying the gateway's route verdict — the shape the defect
 * actually showed up in.
 *
 * A STANDALONE route-decision row was never the broken case: its headline reads
 * `Answered by ark-official:deepseek-v4-flash`, and #973 already marks
 * headlines, so the endpoint id inside the route id lit up there. The row that
 * showed nothing is this one, whose headline is about the call
 * (`LLM call completed · deepseek-v4-flash`) and whose only mention of the
 * endpoint is the `endpoint: {{id}}` line in the attached verdict.
 */
function render(verdict: CallbackEvent, term: string): string {
  const call = makeEvent({
    event_type: 'llm_call',
    phase_name: 'draft',
    model: 'deepseek-v4-flash',
  })
  return renderToStaticMarkup(
    <TraceMarkTermProvider value={term}>
      <TraceStepRow
        step={{
          key: 'evt-0',
          phase: eventPhase(call),
          segment: null,
          stepId: null,
          status: 'done',
          start: { event: call, index: 0 },
          iteration: null,
          verdicts: [{ event: verdict, index: 1, occurrence: 1 }],
          end: null,
        }}
        eventId="evt-0"
        expanded
        onToggleExpanded={() => undefined}
      />
    </TraceMarkTermProvider>,
  )
}

const routeDecision = makeEvent({
  event_type: 'llm_route_decision',
  phase_name: 'draft',
  decision: 'fell_back',
  route_id: 'r-primary',
  endpoint_id: 'ark-official',
  provider_model_id: 'deepseek-v4-flash',
  protocol: 'ark_runtime',
  next_route_id: 'r-backup',
  reason: 'RateLimitError',
  provider_status_code: 429,
})

describe('a matched row shows why it matched', () => {
  it('marks the endpoint id the reader searched for', () => {
    const html = render(routeDecision, 'ark-official')

    expect(html).toContain('<mark class="rounded-[2px] bg-warning/40 text-foreground">ark-official</mark>')
  })

  it('marks only part of an endpoint id when only part of it was typed', () => {
    const html = render(routeDecision, 'offic')

    expect(html).toContain('>offic</mark>')
  })

  it('never marks the word this app wrote around the value', () => {
    // `end` is inside our own label "endpoint:" and inside no event value here.
    // A mark on it would tell the reader this row matched on something it did
    // not — and the label is on EVERY route row, so it would be a wall of them.
    const html = render(routeDecision, 'end')

    expect(html).not.toContain('<mark')
  })

  it('marks a status code, which is a value even though it is a number', () => {
    const html = render(routeDecision, '429')

    expect(html).toContain('>429</mark>')
  })
})
