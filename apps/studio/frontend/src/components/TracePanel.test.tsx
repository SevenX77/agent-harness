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
    <TracePanel traceLogs={events} onSelectPrompt={() => undefined} {...props} />,
  )
}

describe('TracePanel EventEnvelope contract', () => {
  it('accepts EventEnvelope trace logs instead of raw CallbackEvent fixtures', () => {
    expectTypeOf<React.ComponentProps<typeof TracePanel>['traceLogs']>().toEqualTypeOf<EventEnvelope[]>()

    const html = render({})

    expect(html).toContain('1 events')
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
  // Whole-run is the resting state and carries no chrome; only a LIVE link to a
  // focused node is worth a marker, and it sits on the filter row next to the
  // node chips it narrows.
  it('says nothing about focus when no node is focused', () => {
    const html = render({})
    expect(html).not.toContain('&rarr; phase1')
  })

  it('marks the linked node when link is on and a phase is active', () => {
    const html = render({ activePhase: 'phase1', linkEnabled: true })
    expect(html).toContain('phase1')
    expect(html).toContain('Linked to phase1')
  })

  it('shows no link marker when link views is disabled even with an active phase', () => {
    const html = render({ activePhase: 'phase1', linkEnabled: false })
    expect(html).not.toContain('Linked to phase1')
  })
})

// Two phases (nodeA, nodeB) so focus narrowing is observable via the
// event count in the identity strip (atom #17).
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
    expect(html).toContain('3 events')
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
    expect(html).toContain('2 / 3')
    expect(html).toContain('Linked to nodeA')
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
    expect(html).toContain('2 / 3')
    expect(html).toContain('Linked to nodeA')
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
    expect(html).toContain('3 events')
  })
})

describe('TracePanel naming (atom #28 / D3 命名统一 2026-08-07)', () => {
  // 一套口径: 区域=Timeline(Toolbar+列表) / 本视图=Trace / 文档=Full Trace。
  // atom #28 的底线不变: 歧义的 "Trace Timeline" 永不回归。
  it('names the view "Trace" and never the ambiguous "Trace Timeline"', () => {
    const html = render({})
    expect(html).toContain('>Trace<')
    expect(html).not.toContain('Trace Timeline')
  })

  it('uses "Trace" as the empty-state aria-label', () => {
    const html = renderToStaticMarkup(
      <TracePanel traceLogs={[]} onSelectPrompt={() => undefined} />,
    )
    expect(html).toContain('aria-label="Trace"')
    expect(html).not.toContain('Trace Timeline')
  })

  // The identity strip keeps what you read while working — status, what the
  // list is showing, the controls. The run id moved into the ⋮ menu: at the
  // panel's 383px it could not coexist with them (331px of content box against
  // 361px of demand), and it is wanted exactly when you go looking for the run
  // on disk, which is what that menu is for.
  it('shows the run state in the identity strip and keeps the id one click away', () => {
    const html = render({ runId: 'run-abcdef123456', live: true })
    expect(html).toContain('Live')
    expect(html).toContain('aria-label="Run actions"')
  })

  it('offers a back-to-timeline affordance when a close handler is wired', () => {
    const html = render({ onBack: () => undefined })
    expect(html).toContain('aria-label="Back to timeline"')
  })

  it('marks a historical predict view with a Predict badge from metadata.kind', () => {
    const html = render({
      metadata: {
        run_id: 'predict-1',
        status: 'success',
        started_at: '2026-08-07T00:00:00Z',
        kind: 'predict',
        metrics: null,
        input_summary: null,
      },
      runId: 'predict-1',
    })
    expect(html).toContain('Predict')
    expect(html).toContain('Success')
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
      <TracePanel traceLogs={[]} onSelectPrompt={() => undefined} canResume onResume={() => undefined} live />,
    )
    expect(html).toContain('Waiting for run events')
    // Nothing to search or filter yet, so neither control is mounted...
    expect(html).not.toContain('Search trace events')
    expect(html).not.toContain('aria-label="Filter events"')
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
        onSelectPrompt={() => undefined}
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
        onSelectPrompt={() => undefined}
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
        onSelectPrompt={() => undefined}
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
        onSelectPrompt={() => undefined}
      />,
    )
    expect(html).not.toContain('Promote node to golden')
  })

  it('omits the per-node button when link views is off (no node focus)', () => {
    const html = renderToStaticMarkup(
      <TracePanel
        traceLogs={twoPhaseEvents}
        selectedNode={goldenlessAgentNode}
        canCompare
        linkEnabled={false}
        onPromoteNode={() => undefined}
        onSelectPrompt={() => undefined}
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
        onSelectPrompt={() => undefined}
      />,
    )
    expect(html).toContain('2 LLM fallbacks')
    expect(html).toContain('aria-label="Filter 2 LLM fallback events"')
  })

  it('uses the singular label for a single fallback', () => {
    const html = renderToStaticMarkup(
      <TracePanel
        traceLogs={[...twoPhaseEvents, fallbackEnvelope(4, 'nodeA')]}
        onSelectPrompt={() => undefined}
      />,
    )
    expect(html).toContain('1 LLM fallback')
    expect(html).not.toContain('1 LLM fallbacks')
  })

  it('omits the chip entirely for a run without fallbacks', () => {
    const html = renderToStaticMarkup(
      <TracePanel traceLogs={twoPhaseEvents} onSelectPrompt={() => undefined} />,
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
      <TracePanel traceLogs={[]} onSelectPrompt={() => undefined} compareTabs={compareTabs} activeCandidateId="fast" live />,
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
        onSelectPrompt={() => undefined}
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
        onSelectPrompt={() => undefined}
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
        onSelectPrompt={() => undefined}
        runId="run-1"
        metadata={{ ...failedMetadata, status: 'success', error: null }}
      />,
    )

    expect(html).not.toContain('llm.provider_invoke_failed')
  })
})
