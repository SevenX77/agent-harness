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

  it('marks the final attempt badge with the exhausted (destructive) styling', () => {
    const html = renderRow(event({ event_type: 'validation_fail', attempt: 3, max_attempts: 3 }))

    expect(html).toContain('aria-label="Retry attempt 3/3"')
    expect(html).toContain('text-destructive')
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

describe('TraceEventRow agent tool-call folding (D1/P2, n4-trace #16)', () => {
  it('renders the classified verb headline (Explored · Read) for an agent tool_call instead of raw JSON', () => {
    const html = renderRow(
      event({ event_type: 'tool_call', phase_name: 'agent', tool_name: 'Read', args: { path: 'a.py' }, result: 'file body' }),
    )

    expect(html).toContain('Explored · Read')
  })

  it('renders the classified subtree (not a JSON.stringify dump) when an agent tool_call row is expanded', () => {
    const html = renderRow(
      event({ event_type: 'tool_call', phase_name: 'agent', tool_name: 'Bash', args: { cmd: 'ls -la' }, result: 'total 0' }),
      true,
    )

    // The expanded view shows the classified Input/Result subtree, not a raw payload toggle.
    expect(html).toContain('Input')
    expect(html).toContain('Result')
    expect(html).toContain('ls -la')
    expect(html).not.toContain('Show full payload')
  })
})

describe('TraceEventRow agent execution subtree inline expand (D9, n4-trace #24)', () => {
  it("renders a '+' inline expand affordance on an agent tool_call row", () => {
    const html = renderRow(event({ event_type: 'tool_call', phase_name: 'agent', tool_name: 'Read', result: 'x' }))

    expect(html).toContain('aria-label="Expand execution subtree"')
  })

  it('does not render the subtree affordance for a non-tool event', () => {
    const html = renderRow(event({ event_type: 'phase_start', phase_name: 'draft' }))

    expect(html).not.toContain('execution subtree')
  })
})

describe('TraceEventRow retry-exhausted Error Stack (D10, n4-trace #25)', () => {
  it('renders an Error Stack listing each prior failure reason when retries are exhausted', () => {
    const html = renderRow(
      event({ event_type: 'retry_exhausted', phase_name: 'draft', max_retries: 3, final_errors: ['schema mismatch', 'missing field x'] }),
    )

    expect(html).toContain('Error Stack (2)')
    expect(html).toContain('schema mismatch')
    expect(html).toContain('missing field x')
  })

  it('surfaces the per-attempt errors list for a validation_fail event', () => {
    const html = renderRow(event({ event_type: 'validation_fail', phase_name: 'draft', errors: ['line 3 invalid'] }))

    expect(html).toContain('Error Stack (1)')
    expect(html).toContain('line 3 invalid')
  })

  it('omits the Error Stack entirely for a passing phase event', () => {
    const html = renderRow(event({ event_type: 'phase_end', phase_name: 'draft' }))

    expect(html).not.toContain('Error Stack')
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
