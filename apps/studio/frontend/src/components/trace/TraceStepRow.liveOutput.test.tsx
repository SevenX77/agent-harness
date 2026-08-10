import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import type { CallbackEvent } from '../../api/types'
import type { StepOutput } from '../../hooks/useRunDeltas'
import { eventPhase } from '../../utils/trace'
import { TraceStepRow } from './TraceStepRow'

// decision 2026-08-09 D6: the answer appears INSIDE the step producing it, not
// in a panel of its own. A second home would mean the same text twice from two
// sources — and the moment a piece is dropped under backpressure, two sources
// that disagree.

function makeEvent(partial: Partial<CallbackEvent> & { event_type: string }): CallbackEvent {
  return { schema_version: '1.0', timestamp: '2026-08-09T00:00:00Z', ...partial } as CallbackEvent
}

function render(
  event: CallbackEvent,
  {
    status = 'running',
    liveOutput,
    end = null,
  }: {
    status?: 'running' | 'done'
    liveOutput?: StepOutput
    end?: { event: CallbackEvent; index: number } | null
  } = {},
): string {
  return renderToStaticMarkup(
    <TraceStepRow
      step={{
        key: 'evt-0',
        phase: eventPhase(event),
        stepId: 'step-1',
        status,
        start: { event, index: 0 },
        end,
      }}
      eventId="evt-0"
      expanded={false}
      onToggleExpanded={() => undefined}
      liveOutput={liveOutput}
    />,
  )
}

const opener = makeEvent({ event_type: 'prompt_captured', phase_name: 'draft', step_id: 'step-1' })

describe('a running step shows the answer arriving', () => {
  it('renders the text produced so far inside the row', () => {
    const html = render(opener, { liveOutput: { text: 'Hello, wor', thinking: '' } })

    expect(html).toContain('data-trace-live-output')
    expect(html).toContain('Hello, wor')
  })

  it('shows thinking apart from the answer, not concatenated into it', () => {
    const html = render(opener, { liveOutput: { text: '42', thinking: 'let me think' } })

    expect(html).toContain('let me think')
    expect(html).toContain('42')
    expect(html).not.toContain('let me think42')
  })

  // Once the answer has landed the row has its own summary of it. Keeping the
  // live copy too would show the same text twice, from two sources that can
  // disagree after a dropped piece.
  it('stops showing the live copy once the step is done', () => {
    const html = render(opener, {
      status: 'done',
      liveOutput: { text: 'Hello, world', thinking: '' },
      end: {
        event: makeEvent({
          event_type: 'llm_call',
          phase_name: 'draft',
          step_id: 'step-1',
          input_tokens: 1,
          output_tokens: 2,
          response_data: { content: 'Hello, world' },
        }),
        index: 1,
      },
    })

    expect(html).not.toContain('data-trace-live-output')
  })

  it('renders nothing at all before the first piece arrives', () => {
    expect(render(opener, { liveOutput: { text: '', thinking: '' } })).not.toContain(
      'data-trace-live-output',
    )
    expect(render(opener)).not.toContain('data-trace-live-output')
  })
})
