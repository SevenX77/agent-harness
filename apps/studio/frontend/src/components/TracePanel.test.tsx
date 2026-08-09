import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, expectTypeOf, it } from 'vitest'

import type { CallbackEvent, EventEnvelope } from '../api/types'
import { TracePanel, isGoldenlessAgentNode, traceRunActions } from './TracePanel'

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
    <TracePanel traceLogs={events} {...props} />,
  )
}

describe('TracePanel EventEnvelope contract', () => {
  it('accepts EventEnvelope trace logs instead of raw CallbackEvent fixtures', () => {
    expectTypeOf<React.ComponentProps<typeof TracePanel>['traceLogs']>().toEqualTypeOf<EventEnvelope[]>()

    const html = render({})

    expect(html).toContain('data-trace-step-count="1"')
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

// Two phases (nodeA, nodeB) so focus can be observed to LOCATE without removing
// anything (decision 2026-08-09 D2).
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

describe('TracePanel search and filter (decision 2026-08-09 D10/D11)', () => {
  it('keeps filtering with the search box instead of on the identity strip', () => {
    const html = render({ runId: 'run-1' })

    // The strip answers WHICH run and HOW it stands; a filter control there was
    // a third question competing for the same row (D3).
    expect(html).toContain('aria-label="Filter by event kind"')
    expect(html).not.toContain('aria-label="Filter events"')
  })

  it('wraps the box and its tags in one focus scope', () => {
    // Without a shared scope, clicking a tag blurs the input and the tags
    // vanish under the pointer.
    const html = render({})
    expect(html).toContain('group/trace-search')
  })

  it('says how many filters are on, so a closed row is never a silent one', () => {
    const html = render({})
    expect(html).not.toContain('filters are narrowing this trace')
  })

  it('lets the search icon take its size from the addon that holds it', () => {
    // Overriding it is the modification D10 removes: the group is 28px tall and
    // a hand-set 16px icon does not fit the padding the addon already applies.
    const html = render({})
    expect(html).toContain('lucide-search')
    expect(html).not.toMatch(/lucide-search[^"]*h-4 w-4/)
  })
})

describe('TracePanel focus behaviour (decision 2026-08-09 D2)', () => {
  // Focusing a node used to FILTER the trace down to that node. With the
  // narrowing hint and its toggle both gone from the strip, keeping the filter
  // would leave an invisible, unclosable one — and the trace is now the only
  // surface that has to read end to end. Focus therefore locates, never hides.
  it('keeps every event when a node is focused', () => {
    const html = renderToStaticMarkup(
      <TracePanel
        traceLogs={twoPhaseEvents}
        selectedNode={{ id: 'nodeA', data: { label: 'Node A' } }}
      />,
    )
    expect(html).toContain('data-trace-step-count="3"')
    expect(html).not.toContain('2 / 3')
    expect(html).not.toContain('Linked to nodeA')
  })

  it('keeps every event while a phase is running', () => {
    const html = renderToStaticMarkup(
      <TracePanel traceLogs={twoPhaseEvents} activePhase="nodeB" />,
    )
    expect(html).toContain('data-trace-step-count="3"')
  })

  it('marks the focused node group so the list can scroll to it', () => {
    const html = renderToStaticMarkup(
      <TracePanel
        traceLogs={twoPhaseEvents}
        selectedNode={{ id: 'nodeA', data: { label: 'Node A' } }}
      />,
    )
    expect(html).toContain('data-trace-group-header="nodeA"')
    expect(html).toContain('data-trace-focus-group="true"')
  })

  it('offers no link toggle — canvas focus no longer filters anything', () => {
    const html = renderToStaticMarkup(
      <TracePanel
        traceLogs={twoPhaseEvents}
        selectedNode={{ id: 'nodeA', data: { label: 'Node A' } }}
      />,
    )
    expect(html).not.toContain('Link trace to the focused node')
  })
})

describe('TracePanel naming (decision 2026-08-09 D1)', () => {
  // 一套口径: 区域=Trace(Toolbar 第4格) / 区域默认视图=运行列表 / 该次运行的踪迹视图=Trace。
  // atom #28 的底线不变: 歧义的 "Trace Timeline" 永不回归。
  it('names the view "Trace" and never the ambiguous "Trace Timeline"', () => {
    const html = render({})
    expect(html).toContain('aria-label="Trace"')
    expect(html).not.toContain('Trace Timeline')
  })

  it('uses "Trace" as the empty-state aria-label', () => {
    const html = renderToStaticMarkup(
      <TracePanel traceLogs={[]} />,
    )
    expect(html).toContain('aria-label="Trace"')
    expect(html).not.toContain('Trace Timeline')
  })

  // The strip answers two questions and no more: WHICH run this is, and HOW it
  // stands (decision 2026-08-09 D3). Everything that used to compete for the
  // 331px content box — the view's own name, the narrowing hint, the link
  // toggle — said something the user could already see or no longer needs.
  it('puts the full run id on the strip, untruncated', () => {
    const html = render({ runId: '2026-08-09T13-40-42_80960a2c', live: true })

    expect(html).toContain('2026-08-09T13-40-42_80960a2c')
    // Truncation is CSS, so the full id stays in the DOM and in the title.
    expect(html).toContain('title="2026-08-09T13-40-42_80960a2c"')
  })

  it('says the outcome with an icon and puts the words in a tooltip', () => {
    const html = render({
      metadata: {
        run_id: 'r1',
        status: 'success',
        started_at: '2026-08-09T00:00:00Z',
        metrics: null,
        input_summary: null,
      },
    })

    expect(html).toContain('aria-label="Run succeeded"')
    // The word itself is not spent on strip width.
    expect(html).not.toMatch(/>Success</)
  })

  it('marks a predict run with the same flask used everywhere else', () => {
    const html = render({
      runId: 'predict-2026-08-09T13-40-42_80960a2c',
      metadata: {
        run_id: 'p1',
        kind: 'predict',
        status: 'success',
        started_at: '2026-08-09T00:00:00Z',
        metrics: null,
        input_summary: null,
      },
    })

    expect(html).toContain('aria-label="Predict attempt"')
    expect(html).not.toMatch(/>Predict</)
  })

  it('offers a back-to-timeline affordance when a close handler is wired', () => {
    const html = render({ onBack: () => undefined })
    expect(html).toContain('aria-label="Back to timeline"')
  })
})

describe('TracePanel run actions (⋮ menu)', () => {
  // Run-level actions live in one overflow menu on the identity strip, so the
  // search row keeps its full width (decision 2026-08-08 D4). Radix renders the
  // menu's items only once it is open, which static rendering cannot do — so the
  // items are decided by a pure function and asserted here, while the markup
  // tests below assert the trigger itself.
  const resumeOnly = {
    canResume: true,
    resumeLoading: false,
    onResume: () => undefined,
    canCompare: false,
    compareLoading: false,
    reportPath: null,
  }

  it('offers Resume, enabled, when the run can be resumed', () => {
    const [action] = traceRunActions(resumeOnly)
    expect(action.key).toBe('resume')
    expect(action.label).toBe('Resume from last checkpoint')
    expect(action.disabled).toBe(false)
  })

  it('disables Resume when there is no resumable run', () => {
    const [action] = traceRunActions({ ...resumeOnly, canResume: false })
    expect(action.disabled).toBe(true)
  })

  it('says Resuming, and refuses a second click, while a resume is in flight', () => {
    const [action] = traceRunActions({ ...resumeOnly, resumeLoading: true })
    expect(action.label).toBe('Resuming')
    expect(action.disabled).toBe(true)
  })

  it('offers no actions at all for a read-only historical view', () => {
    expect(traceRunActions({
      canResume: false,
      resumeLoading: false,
      canCompare: false,
      compareLoading: false,
      reportPath: null,
    })).toEqual([])
  })

  it('offers the run report exactly when the run left one on disk', () => {
    const withReport = traceRunActions({
      canResume: false,
      resumeLoading: false,
      canCompare: false,
      compareLoading: false,
      reportPath: 'D:/runs/run-1/report.md',
    })
    expect(withReport.map((action) => action.key)).toEqual(['report'])
    expect(withReport[0].label).toBe('Open run report')
  })

  it('renders the overflow trigger when at least one action is wired', () => {
    const html = render({ canResume: true, onResume: () => undefined })
    expect(html).toContain('aria-label="Run actions"')
  })

  it('renders no overflow trigger when nothing is wired', () => {
    const html = render({})
    expect(html).not.toContain('aria-label="Run actions"')
  })

  it('drops the search and filter shell when there are no events, keeping the run identity', () => {
    const html = renderToStaticMarkup(
      <TracePanel traceLogs={[]} canResume onResume={() => undefined} live />,
    )
    expect(html).toContain('Waiting for run events')
    // Nothing to search or filter yet, so neither control is mounted...
    expect(html).not.toContain('Search trace events')
    expect(html).not.toContain('aria-label="Filter by event kind"')
    // ...but the run is still the run: its identity strip and actions stay put.
    expect(html).toContain('aria-label="Run actions"')
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

describe('isGoldenlessAgentNode (atom #32 entry① eligibility)', () => {
  it('is true for an agent node without golden', () => {
    expect(isGoldenlessAgentNode({ data: { mode: 'agent' } })).toBe(true)
    expect(isGoldenlessAgentNode({ data: { mode: 'llm', goldenState: 'logic-ok' } })).toBe(true)
    expect(isGoldenlessAgentNode({ data: { mode: 'skill' } })).toBe(true)
  })

  it('is false once the agent node already has golden', () => {
    expect(isGoldenlessAgentNode({ data: { mode: 'agent', goldenState: 'has-golden' } })).toBe(false)
  })

  it('is false for non-agent nodes (logic/subgraph never get golden)', () => {
    expect(isGoldenlessAgentNode({ data: { mode: 'logic' } })).toBe(false)
    expect(isGoldenlessAgentNode({ data: { mode: 'subgraph' } })).toBe(false)
  })

  it('is false when there is no focused node', () => {
    expect(isGoldenlessAgentNode(null)).toBe(false)
    expect(isGoldenlessAgentNode(undefined)).toBe(false)
  })
})

describe('TracePanel per-node golden promote (atom #32 entry①)', () => {
  const goldenlessAgentNode = { id: 'nodeA', data: { label: 'Node A', mode: 'agent' as const } }

  it('renders a per-node promote button beside the focused golden-less agent node', () => {
    const html = renderToStaticMarkup(
      <TracePanel
        traceLogs={twoPhaseEvents}
        selectedNode={goldenlessAgentNode}
        canCompare
        onPromoteNode={() => undefined}
      />,
    )
    expect(html).toContain('Promote node to golden')
    // The aria-label is node-anchored; the focused node label appears in it
    // (double quotes around the label are HTML-escaped by the static renderer).
    expect(html).toContain('aria-label="Promote node ')
    expect(html).toContain('Node A')
    expect(html).toContain(' to golden"')
  })

  it('omits the per-node button when the focused agent node already has golden', () => {
    const html = renderToStaticMarkup(
      <TracePanel
        traceLogs={twoPhaseEvents}
        selectedNode={{ id: 'nodeA', data: { label: 'Node A', mode: 'agent', goldenState: 'has-golden' } }}
        canCompare
        onPromoteNode={() => undefined}
      />,
    )
    expect(html).not.toContain('Promote node to golden')
  })

  it('omits the per-node button with no run to promote from (canCompare false)', () => {
    const html = renderToStaticMarkup(
      <TracePanel
        traceLogs={twoPhaseEvents}
        selectedNode={goldenlessAgentNode}
        canCompare={false}
        onPromoteNode={() => undefined}
      />,
    )
    expect(html).not.toContain('Promote node to golden')
  })

  it('omits the per-node button when no per-node promote handler is wired', () => {
    const html = renderToStaticMarkup(
      <TracePanel
        traceLogs={twoPhaseEvents}
        selectedNode={goldenlessAgentNode}
        canCompare
      />,
    )
    expect(html).not.toContain('Promote node to golden')
  })
})

// trace-observability F7: a run that silently fell back to another provider must
// announce it at the run level, not only as one row lost in the stream.
const fallbackEnvelope = (seq: number, phase: string): EventEnvelope => ({
  schema_version: 'studio.event.v1',
  stream_id: 'run:run-3',
  seq,
  cursor: `run:run-3:${seq}`,
  run_id: 'run-3',
  event_type: 'llm_fallback',
  timestamp: '2026-07-16T00:00:00Z',
  payload: {
    schema_version: '1.0',
    event_type: 'llm_fallback',
    phase_name: phase,
    timestamp: '2026-07-16T00:00:00Z',
    from_provider: 'openai:gpt-4o',
    to_provider: 'zhipu:glm-4.7',
    reason: 'RateLimitError: 429 too many requests',
  },
})

describe('TracePanel LLM fallback summary chip (trace-observability F7)', () => {
  it('surfaces a run-level fallback count chip when fallbacks happened', () => {
    const html = renderToStaticMarkup(
      <TracePanel
        traceLogs={[...twoPhaseEvents, fallbackEnvelope(4, 'nodeA'), fallbackEnvelope(5, 'nodeB')]}
      />,
    )
    expect(html).toContain('2 LLM fallbacks')
    expect(html).toContain('aria-label="Filter 2 LLM fallback events"')
  })

  it('uses the singular label for a single fallback', () => {
    const html = renderToStaticMarkup(
      <TracePanel
        traceLogs={[...twoPhaseEvents, fallbackEnvelope(4, 'nodeA')]}
      />,
    )
    expect(html).toContain('1 LLM fallback')
    expect(html).not.toContain('1 LLM fallbacks')
  })

  it('omits the chip entirely for a run without fallbacks', () => {
    const html = renderToStaticMarkup(
      <TracePanel traceLogs={twoPhaseEvents} />,
    )
    expect(html).not.toContain('LLM fallback')
  })
})

describe('TracePanel model-compare tabs (PR2 node-compare)', () => {
  const compareTabs = [
    { candidateId: 'fast', label: 'deepseek-v4', runId: 'run-f', failed: false, running: false },
    { candidateId: 'slow', label: 'claude-opus', runId: 'run-s', failed: true, running: false },
  ]

  it('renders one tab per candidate, marking the failed candidate', () => {
    const html = render({ compareTabs, activeCandidateId: 'fast' })
    expect(html).toContain('aria-label="Model compare candidates"')
    expect(html).toContain('aria-label="Candidate deepseek-v4"')
    // The failed candidate's tab carries the failure in its accessible name.
    expect(html).toContain('aria-label="Candidate claude-opus (failed)"')
    expect(html).toContain('>deepseek-v4<')
    expect(html).toContain('>claude-opus<')
  })

  it('marks the active candidate tab as selected', () => {
    const html = render({ compareTabs, activeCandidateId: 'slow' })
    const slowIdx = html.indexOf('aria-label="Candidate claude-opus (failed)"')
    // aria-selected="true" lives on the active tab's button (same element as the label).
    expect(html.slice(slowIdx - 120, slowIdx)).toContain('aria-selected="true"')
    const fastIdx = html.indexOf('aria-label="Candidate deepseek-v4"')
    expect(html.slice(fastIdx - 120, fastIdx)).toContain('aria-selected="false"')
  })

  it('renders the tab strip even while a candidate run has no events yet', () => {
    const html = renderToStaticMarkup(
      <TracePanel traceLogs={[]} compareTabs={compareTabs} activeCandidateId="fast" live />,
    )
    // Empty-state still shows the candidate tabs so the user can switch.
    expect(html).toContain('aria-label="Model compare candidates"')
    expect(html).toContain('aria-label="Candidate deepseek-v4"')
    expect(html).toContain('Waiting for run events')
  })

  it('omits the tab strip when no compare run is active', () => {
    const html = render({})
    expect(html).not.toContain('aria-label="Model compare candidates"')
  })
})

describe('failed run reason', () => {
  const failedMetadata = {
    run_id: 'run-1',
    status: 'failed' as const,
    started_at: '2026-08-08T09:47:48Z',
    metrics: null,
    input_summary: null,
    error: {
      code: 'llm.provider_invoke_failed',
      message: "resource.no_available_route - {'role': 'analyst'}",
      details: {},
    },
  }

  it('shows why the run failed', () => {
    const html = renderToStaticMarkup(
      <TracePanel
        traceLogs={events}
        activePhase={null}
        selectedNode={null}
        runId="run-1"
        metadata={failedMetadata}
      />,
    )

    expect(html).toContain('llm.provider_invoke_failed')
    expect(html).toContain('no_available_route')
  })

  it('shows the reason even when the run died before emitting any event', () => {
    const html = renderToStaticMarkup(
      <TracePanel
        traceLogs={[]}
        activePhase={null}
        selectedNode={null}
        runId="run-1"
        metadata={failedMetadata}
      />,
    )

    expect(html).toContain('llm.provider_invoke_failed')
  })

  it('shows nothing extra for a successful run', () => {
    const html = renderToStaticMarkup(
      <TracePanel
        traceLogs={events}
        activePhase={null}
        selectedNode={null}
        runId="run-1"
        metadata={{ ...failedMetadata, status: 'success', error: null }}
      />,
    )

    expect(html).not.toContain('llm.provider_invoke_failed')
  })
})
