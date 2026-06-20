import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, expectTypeOf, it } from 'vitest'

import type { CallbackEvent, EventEnvelope } from '../api/types'
import { TracePanel } from './TracePanel'

const events = [
  {
    schema_version: 'studio.event.v1',
    stream_id: 'run:run-1',
    seq: 1,
    cursor: 'run:run-1:1',
    run_id: 'run-1',
    event_type: 'run_started',
    timestamp: '2026-06-14T00:00:00Z',
    payload: {
      schema_version: '1.0',
      event_type: 'run_started',
      phase_name: 'phase1',
      timestamp: '2026-06-14T00:00:00Z',
    },
  } satisfies EventEnvelope,
]

const hitlEvents = [
  events[0],
  {
    schema_version: 'studio.event.v1',
    stream_id: 'run:run-1',
    seq: 2,
    cursor: 'run:run-1:2',
    run_id: 'run-1',
    event_type: 'interrupted',
    timestamp: '2026-06-14T00:00:01Z',
    payload: {
      schema_version: '1.0',
      event_type: 'interrupted',
      phase_name: 'review',
      timestamp: '2026-06-14T00:00:01Z',
      question: 'Approve the generated draft?',
      options: ['Approve', 'Revise'],
      tool_call_id: 'tool-1',
      checkpoint_id: 'checkpoint-review',
      checkpoint_ns: 'agent:review',
    },
  } satisfies EventEnvelope,
]

const multiPendingHitlEvents = [
  events[0],
  {
    schema_version: 'studio.event.v1',
    stream_id: 'run:run-1',
    seq: 2,
    cursor: 'run:run-1:2',
    run_id: 'run-1',
    event_type: 'interrupted',
    timestamp: '2026-06-14T00:00:01Z',
    payload: {
      schema_version: '1.0',
      event_type: 'interrupted',
      phase_name: 'review',
      timestamp: '2026-06-14T00:00:01Z',
      question: 'Choose the pending human input to answer.',
      pending_tool_calls: [
        { id: 'tool-a', question: 'Approve outline?', options: ['Approve outline', 'Revise outline'] },
        { id: 'tool-b', question: 'Approve citations?', options: ['Approve citations', 'Revise citations'] },
      ],
      checkpoint_id: 'checkpoint-review',
      checkpoint_ns: 'agent:review',
    },
  } satisfies EventEnvelope,
]

function render(props: Partial<React.ComponentProps<typeof TracePanel>>): string {
  return renderToStaticMarkup(
    <TracePanel traceLogs={events} onSelectPrompt={() => undefined} {...props} />,
  )
}

describe('TracePanel EventEnvelope contract', () => {
  it('accepts EventEnvelope trace logs instead of raw CallbackEvent fixtures', () => {
    expectTypeOf<React.ComponentProps<typeof TracePanel>['traceLogs']>().toEqualTypeOf<EventEnvelope[]>()

    const html = render({})

    expect(html).toContain('Showing 1 of 1 events')
  })

  it('does not accept a raw CallbackEvent fixture as trace logs', () => {
    const rawCallbackEvent = {
      schema_version: '1.0',
      event_type: 'run_started',
      timestamp: '2026-06-14T00:00:00Z',
    } as CallbackEvent

    // @ts-expect-error TracePanel must consume EventEnvelope[] only.
    const invalidProps: Partial<React.ComponentProps<typeof TracePanel>> = { traceLogs: [rawCallbackEvent] }

    expect(invalidProps.traceLogs).toHaveLength(1)
  })
})

describe('TracePanel focus granularity label (F3)', () => {
  it('labels the trace as whole-run when no node is focused', () => {
    const html = render({})
    expect(html).toContain('Focus: whole run')
  })

  it('labels the trace with the focused node when link is on and a phase is active', () => {
    const html = render({ activePhase: 'phase1', linkEnabled: true })
    expect(html).toContain('Focus: phase1')
  })

  it('falls back to whole-run when link views is disabled even with an active phase', () => {
    const html = render({ activePhase: 'phase1', linkEnabled: false })
    expect(html).toContain('Focus: whole run')
    expect(html).not.toContain('Focus: phase1')
  })
})

// Two phases (nodeA, nodeB) so focus narrowing is observable via the
// "Showing N of M" count and the Focus chip (atom #17).
const twoPhaseEvents: EventEnvelope[] = [
  {
    schema_version: 'studio.event.v1',
    stream_id: 'run:run-2',
    seq: 1,
    cursor: 'run:run-2:1',
    run_id: 'run-2',
    event_type: 'phase_start',
    timestamp: '2026-06-14T00:00:00Z',
    payload: {
      schema_version: '1.0',
      event_type: 'phase_start',
      phase_name: 'nodeA',
      timestamp: '2026-06-14T00:00:00Z',
    },
  },
  {
    schema_version: 'studio.event.v1',
    stream_id: 'run:run-2',
    seq: 2,
    cursor: 'run:run-2:2',
    run_id: 'run-2',
    event_type: 'phase_end',
    timestamp: '2026-06-14T00:00:01Z',
    payload: {
      schema_version: '1.0',
      event_type: 'phase_end',
      phase_name: 'nodeA',
      timestamp: '2026-06-14T00:00:01Z',
    },
  },
  {
    schema_version: 'studio.event.v1',
    stream_id: 'run:run-2',
    seq: 3,
    cursor: 'run:run-2:3',
    run_id: 'run-2',
    event_type: 'phase_start',
    timestamp: '2026-06-14T00:00:02Z',
    payload: {
      schema_version: '1.0',
      event_type: 'phase_start',
      phase_name: 'nodeB',
      timestamp: '2026-06-14T00:00:02Z',
    },
  },
]

describe('TracePanel focus granularity (atom #17)', () => {
  it('shows the whole-run overview (all events) when no node is focused', () => {
    const html = renderToStaticMarkup(
      <TracePanel traceLogs={twoPhaseEvents} selectedNode={null} onSelectPrompt={() => undefined} />,
    )
    expect(html).toContain('Showing 3 of 3 events')
    expect(html).toContain('Focus: whole run')
  })

  it('narrows the trace to the focused node phase when a node is selected', () => {
    const html = renderToStaticMarkup(
      <TracePanel
        traceLogs={twoPhaseEvents}
        selectedNode={{ id: 'nodeA', data: { label: 'Node A' } }}
        onSelectPrompt={() => undefined}
      />,
    )
    // nodeA carries two events (phase_start + phase_end); nodeB's is excluded.
    expect(html).toContain('Showing 2 of 3 events')
    expect(html).toContain('Focus: Node A')
  })

  it('lets the focused node override the running activePhase for granularity', () => {
    const html = renderToStaticMarkup(
      <TracePanel
        traceLogs={twoPhaseEvents}
        activePhase="nodeB"
        selectedNode={{ id: 'nodeA', data: { label: 'Node A' } }}
        onSelectPrompt={() => undefined}
      />,
    )
    // selectedNode (nodeA) wins over the running phase (nodeB): narrows to nodeA.
    expect(html).toContain('Showing 2 of 3 events')
    expect(html).toContain('Focus: Node A')
  })

  it('does not narrow when link views is disabled even with a focused node', () => {
    const html = renderToStaticMarkup(
      <TracePanel
        traceLogs={twoPhaseEvents}
        selectedNode={{ id: 'nodeA', data: { label: 'Node A' } }}
        linkEnabled={false}
        onSelectPrompt={() => undefined}
      />,
    )
    expect(html).toContain('Showing 3 of 3 events')
    expect(html).toContain('Focus: whole run')
  })
})

describe('TracePanel naming (atom #28)', () => {
  it('names the panel "Event Trace" rather than the ambiguous "Trace Timeline"', () => {
    const html = render({})
    expect(html).toContain('Event Trace')
    expect(html).not.toContain('Trace Timeline')
  })

  it('uses "Event Trace" as the empty-state aria-label', () => {
    const html = renderToStaticMarkup(
      <TracePanel traceLogs={[]} onSelectPrompt={() => undefined} />,
    )
    expect(html).toContain('aria-label="Event Trace"')
    expect(html).not.toContain('Trace Timeline')
  })
})

describe('TracePanel Resume action', () => {
  it('shows a Resume button enabled when the run can be resumed', () => {
    const html = render({ canResume: true })
    expect(html).toContain('Resume')
    expect(html).toContain('aria-label="Resume run from last checkpoint"')
    // Enabled: the resume button markup should not carry the disabled attribute.
    const resumeButton = html.slice(html.indexOf('Resume run from last checkpoint') - 200, html.indexOf('Resume run from last checkpoint') + 200)
    expect(resumeButton).not.toContain('disabled=""')
  })

  it('disables Resume when there is no resumable run', () => {
    const html = render({ canResume: false })
    const idx = html.indexOf('Resume run from last checkpoint')
    // The disabled attribute follows aria-label + title on the same button.
    expect(html.slice(idx, idx + 200)).toContain('disabled')
  })

  it('shows a Resuming label while a resume is in flight', () => {
    const html = render({ canResume: true, resumeLoading: true })
    expect(html).toContain('Resuming')
  })

  it('omits Resume affordance content when there are no trace events', () => {
    const html = renderToStaticMarkup(
      <TracePanel traceLogs={[]} onSelectPrompt={() => undefined} canResume />,
    )
    // Empty state shows the waiting message, not the action bar.
    expect(html).toContain('Waiting for run events')
    expect(html).not.toContain('Resume run from last checkpoint')
  })

  it('shows a HitL answer form from the latest interrupted EventEnvelope', () => {
    const html = render({ traceLogs: hitlEvents })

    expect(html).toContain('Human input required')
    expect(html).toContain('Approve the generated draft?')
    expect(html).toContain('Approve')
    expect(html).toContain('Revise')
    expect(html).toContain('aria-label="Human response for review"')
    expect(html).toContain('tool-1')
    expect(html).toContain('checkpoint-review')
  })

  it('shows multiple pending HitL tool calls and requires selecting one before submit', () => {
    const html = render({ traceLogs: multiPendingHitlEvents })

    expect(html).toContain('Pending tool calls')
    expect(html).toContain('Approve outline?')
    expect(html).toContain('Approve citations?')
    expect(html).toContain('tool-a')
    expect(html).toContain('tool-b')
    expect(html).toContain('Select a pending tool call before submitting.')
    const submitSlice = html.slice(html.indexOf('Submit answer') - 240, html.indexOf('Submit answer') + 160)
    expect(submitSlice).toContain('disabled=""')
  })
})
