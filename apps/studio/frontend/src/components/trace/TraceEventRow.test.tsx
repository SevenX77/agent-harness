import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import type { CallbackEvent } from '../../api/types'
import { TraceEventRow } from './TraceEventRow'

function event(partial: Partial<CallbackEvent> & { event_type: string }): CallbackEvent {
  return {
    schema_version: '1.0',
    timestamp: '2026-06-14T00:00:00Z',
    ...partial,
  } as CallbackEvent
}

function renderRow(event: CallbackEvent, expanded = false): string {
  return renderToStaticMarkup(
    <TraceEventRow
      event={event}
      index={0}
      eventId="evt-0"
      expanded={expanded}
      onToggleExpanded={() => undefined}
      onSelectPrompt={() => undefined}
    />,
  )
}

describe('TraceEventRow retry badge (D10)', () => {
  it('renders a 2/3 retry badge for a validation_fail with attempt info', () => {
    const html = renderRow(event({ event_type: 'validation_fail', attempt: 2, max_attempts: 3, error_message: 'schema mismatch' }))

    expect(html).toContain('aria-label="Retry attempt 2/3"')
    expect(html).toContain('2/3')
    // The error stack message is still surfaced for the failed attempt.
    expect(html).toContain('schema mismatch')
  })

  it('marks the final attempt badge with the exhausted (red) styling', () => {
    const html = renderRow(event({ event_type: 'validation_fail', attempt: 3, max_attempts: 3 }))

    expect(html).toContain('Final attempt (3/3)')
    expect(html).toContain('text-red-700')
  })

  it('omits the retry badge entirely for events without attempt info', () => {
    const html = renderRow(event({ event_type: 'phase_start', phase_name: 'draft' }))

    expect(html).not.toContain('Retry attempt')
  })
})

describe('TraceEventRow payload collapse (D1 / §4)', () => {
  it('renders the full payload inline when it is under the ~2KB auto-expand limit', () => {
    const html = renderRow(event({ event_type: 'phase_start', phase_name: 'draft' }), true)

    // Small payload: no "show full" affordance — it is already fully shown.
    expect(html).not.toContain('Show full payload')
    expect(html).toContain('phase_start')
  })

  it('collapses an oversized payload and offers a sized "show full" toggle', () => {
    const big = 'z'.repeat(4000)
    const html = renderRow(event({ event_type: 'llm_call', big_field: big }), true)

    expect(html).toContain('Show full payload')
    // The size label is surfaced so the PM knows how big the hidden blob is.
    expect(html).toContain('KB)')
    // The collapsed head must not contain the full 4000-char blob verbatim.
    expect(html).not.toContain(big)
  })
})

describe('TraceEventRow inspect-prompt affordance (D8 click target)', () => {
  it('renders the Inspect prompt control for an llm_call event', () => {
    const html = renderRow(event({ event_type: 'llm_call', phase_name: 'draft' }))

    expect(html).toContain('Inspect prompt')
  })

  it('does not render the Inspect prompt control for a plain phase event', () => {
    const html = renderRow(event({ event_type: 'phase_start', phase_name: 'draft' }))

    expect(html).not.toContain('Inspect prompt')
  })
})
