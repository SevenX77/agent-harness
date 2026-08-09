import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import type { CallbackEvent } from '../../api/types'
import { eventPhase } from '../../utils/trace'
import { TraceStepRow } from './TraceStepRow'

function event(partial: Partial<CallbackEvent> & { event_type: string }): CallbackEvent {
  return {
    schema_version: '1.0',
    timestamp: '2026-06-14T00:00:00Z',
    ...partial,
  } as CallbackEvent
}

function renderRow(event: CallbackEvent, expanded = false): string {
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
      expanded={expanded}
      onToggleExpanded={() => undefined}
    />,
  )
}

describe('TraceStepRow retry badge (D10)', () => {
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

describe('TraceStepRow payload collapse (D1 / §4)', () => {
  it('renders the full payload inline when it is under the ~2KB auto-expand limit', () => {
    const html = renderRow(event({ event_type: 'phase_start', phase_name: 'draft' }), true)

    // Small payload: no "show full" affordance — it is already fully shown.
    expect(html).not.toContain('Show full payload')
    expect(html).toContain('phase_start')
  })

  it('collapses an oversized payload and offers a sized "show full" toggle', () => {
    const big = 'z'.repeat(4000)
    const html = renderRow(event({ event_type: 'phase_end', big_field: big }), true)

    expect(html).toContain('Show full payload')
    // The size label is surfaced so the PM knows how big the hidden blob is.
    expect(html).toContain('KB)')
    // The collapsed head must not contain the full 4000-char blob verbatim.
    expect(html).not.toContain(big)
  })
})

describe('TraceStepRow agent tool-call folding (D1/P2, n4-trace #16)', () => {
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

describe('TraceStepRow has one expander, not two (decision 2026-08-09 D4)', () => {
  it('opens the tool subtree from the row itself, with no second control', () => {
    // The row used to carry a separate '+ Expand' for the subtree next to its
    // own chevron: two controls for one fold, disagreeing about what was open.
    const collapsed = renderRow(event({ event_type: 'tool_call', phase_name: 'agent', tool_name: 'Read', result: 'x' }))
    const opened = renderRow(event({ event_type: 'tool_call', phase_name: 'agent', tool_name: 'Read', result: 'x' }), true)

    expect(collapsed).not.toContain('execution subtree')
    expect(collapsed).toContain('Explored · Read')
    expect(opened).toContain('Result')
  })
})

describe('TraceStepRow retry-exhausted Error Stack (D10, n4-trace #25)', () => {
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

describe('TraceStepRow shows the prompt in place (decision 2026-08-09 D5)', () => {
  it('puts template, variables and rendered prompt inside the opened step', () => {
    const html = renderRow(
      event({
        event_type: 'prompt_captured',
        phase_name: 'draft',
        template_source: 'draft.md',
        variables: { topic: 'venus' },
        resolved_prompt: [{ role: 'user', content: 'write about venus' }],
      }),
      true,
    )

    expect(html).toContain('Template')
    expect(html).toContain('draft.md')
    expect(html).toContain('Variables')
    expect(html).toContain('venus')
    expect(html).toContain('Rendered')
  })

  it('offers no link out to a separate inspector', () => {
    // A second home for the prompt is a second thing to keep in sync, and the
    // step has to show it on open anyway.
    const html = renderRow(event({ event_type: 'llm_call', phase_name: 'draft' }), true)

    expect(html).not.toContain('Inspect prompt')
  })
})

describe('TraceStepRow status (decision 2026-08-09 D4)', () => {
  it('says it is still running, so a long call does not look like a dead panel', () => {
    const running = renderToStaticMarkup(
      <TraceStepRow
        step={{
          key: 'evt-0',
          phase: 'draft',
          status: 'running',
          start: { event: event({ event_type: 'prompt_captured', phase_name: 'draft' }), index: 0 },
          end: null,
        }}
        eventId="evt-0"
        expanded
        onToggleExpanded={() => undefined}
      />,
    )

    expect(running).toContain('data-trace-step-status="running"')
    expect(running).toContain('aria-label="Step in progress"')
  })

  it('reports the finished half\'s numbers once the answer arrives', () => {
    const done = renderToStaticMarkup(
      <TraceStepRow
        step={{
          key: 'evt-0',
          phase: 'draft',
          status: 'done',
          start: { event: event({ event_type: 'prompt_captured', phase_name: 'draft' }), index: 0 },
          end: { event: event({ event_type: 'llm_call', phase_name: 'draft', input_tokens: 10, output_tokens: 20 }), index: 1 },
        }}
        eventId="evt-0"
        expanded={false}
        onToggleExpanded={() => undefined}
      />,
    )

    expect(done).toContain('data-trace-step-status="done"')
    expect(done).not.toContain('aria-label="Step in progress"')
    expect(done).toContain('10/20')
  })
})
