import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import type { CallbackEvent } from '../../api/types'
import type { IndexedTraceEvent } from '../../hooks/useTraceFilter'
import { TraceEventList } from './TraceEventList'

function indexedEvents(count: number): IndexedTraceEvent[] {
  return Array.from({ length: count }, (_unused, index) => ({
    index,
    event: {
      schema_version: '1.0',
      timestamp: `2026-08-08T00:00:${String(index).padStart(2, '0')}Z`,
      event_type: 'phase_start',
      phase_name: `node-${index}`,
    } as CallbackEvent,
  }))
}

function markup(count: number): string {
  return renderToStaticMarkup(
    <TraceEventList
      events={indexedEvents(count)}
      selectedEventId={null}
    />,
  )
}

describe('TraceEventList', () => {
  it('renders every event, so the scroll region covers the whole trace', () => {
    // The list used to window rows into fixed 128px slots while spacing them a
    // further 20px apart, so the scroll container was always shorter than what
    // it held and the tail of a run could not be reached.
    const html = markup(100)

    expect(html.match(/role="option"/g)).toHaveLength(100)
    expect(html).toContain('data-trace-step-count="100"')
  })

  it('gives rows no fixed height, so a row is as tall as what it contains', () => {
    const html = markup(3)

    expect(html).not.toContain('min-height:128px')
    expect(html).not.toContain('height:128px')
  })
})

describe('TraceEventList step expansion (decision 2026-08-09 D4)', () => {
  function stepEvents(): IndexedTraceEvent[] {
    return [
      { index: 0, event: { schema_version: '1.0', timestamp: '2026-08-09T00:00:00Z', event_type: 'prompt_captured', phase_name: 'draft', step_id: 's1' } as CallbackEvent },
      { index: 1, event: { schema_version: '1.0', timestamp: '2026-08-09T00:00:01Z', event_type: 'llm_call', phase_name: 'draft', step_id: 's1' } as CallbackEvent },
      { index: 2, event: { schema_version: '1.0', timestamp: '2026-08-09T00:00:02Z', event_type: 'prompt_captured', phase_name: 'review', step_id: 's2' } as CallbackEvent },
    ]
  }

  it('opens a running step and folds a finished one, without being told', () => {
    // Two steps: draft answered, review still waiting. The unfinished one is
    // where the reader's attention belongs, so it is the one left open.
    const html = renderToStaticMarkup(
      <TraceEventList events={stepEvents()} selectedEventId={null} />,
    )

    expect(html).toContain('data-trace-step-count="2"')
    expect(html).toContain('data-trace-step-status="running"')
    expect(html).toContain('data-trace-step-status="done"')
    expect(html.match(/aria-expanded="true"/g)).toHaveLength(1)
    expect(html.match(/aria-expanded="false"/g)).toHaveLength(1)
  })
})

// D8 (decision 2026-08-09): "运行结束后,Trace 末尾自然长出一条终结条目
// (结论 / 耗时 / token / 报告链接)。报告是这次运行的产物,产物出现在过程末尾。"
describe('TraceEventList terminal entry', () => {
  const outcome = {
    status: 'success' as const,
    wallTimeSec: 12.5,
    totalTokens: 115117,
    reportPath: 'D:/skills/demo/.workspace/runs/run-1/report.md',
  }

  function markupWithOutcome(
    entry: (Omit<typeof outcome, 'reportPath'> & { reportPath: string | null }) | null,
  ): string {
    return renderToStaticMarkup(
      <TraceEventList events={indexedEvents(2)} selectedEventId={null} outcome={entry} />,
    )
  }

  it('states the conclusion with its duration, tokens and report link', () => {
    const html = markupWithOutcome(outcome)

    expect(html).toContain('data-trace-outcome="success"')
    expect(html).toContain('Run succeeded')
    expect(html).toContain('12.5s')
    expect(html).toContain('115,117 tokens')
    expect(html).toContain('data-trace-outcome-report')
    expect(html).toContain('Open run report')
  })

  it('puts it AFTER the last step — a product comes at the end of the process', () => {
    const html = markupWithOutcome(outcome)

    expect(html.indexOf('data-trace-outcome=')).toBeGreaterThan(html.lastIndexOf('role="option"'))
  })

  it('offers no report link for a run that left no report', () => {
    const html = markupWithOutcome({ ...outcome, reportPath: null })

    expect(html).toContain('data-trace-outcome="success"')
    expect(html).not.toContain('Open run report')
  })

  it('renders nothing extra while the run is still going', () => {
    const html = markupWithOutcome(null)

    expect(html).not.toContain('data-trace-outcome')
  })
})

describe('a resume is a seam in the run, not a step', () => {
  function listOf(events: Partial<CallbackEvent>[]): string {
    return renderToStaticMarkup(
      <TraceEventList
        events={events.map((event, index) => ({
          index,
          event: { schema_version: '1.0', timestamp: '2026-08-08T00:00:00Z', ...event } as CallbackEvent,
        }))}
        selectedEventId={null}
      />,
    )
  }

  it('renders the resume as its own seam row', () => {
    const html = listOf([
      { event_type: 'interrupted', phase_name: 'review', question: 'Approve?' },
      { event_type: 'resumed', phase_name: 'review', resumed_from_phase: 'review', human_input: 'Approve' },
      { event_type: 'phase_start', phase_name: 'publish' },
    ])

    expect(html).toContain('data-trace-resume-seam')
  })

  it('names where it picked up and what the human answered', () => {
    const html = listOf([
      { event_type: 'resumed', phase_name: 'review', resumed_from_phase: 'review', human_input: 'Approve' },
    ])

    expect(html).toContain('review')
    expect(html).toContain('Approve')
  })

  it('does not fall back to a raw event payload', () => {
    // Landing in GenericPayload is what made a resume unreadable, and an
    // unreadable seam is why one run's two time clusters read as two runs
    // bleeding into each other (ledger T12).
    const html = listOf([
      { event_type: 'resumed', phase_name: 'review', resumed_from_phase: 'review', human_input: 'Approve' },
    ])

    expect(html).not.toContain('Event payload')
  })
})
