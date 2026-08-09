import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import type { EventEnvelope } from '@/api/types'
import { WorkspaceProvider, type WorkspaceContextValue } from '../WorkspaceContext'
import { Panels } from './Panels'
import type { TraceView } from './trace-view'

// History panel pulls run history over SWR/API; stub it so the no-run branch
// renders deterministically without a network layer.
vi.mock('@/hooks/useRunHistory', () => ({
  useRunHistory: () => ({ runs: [], isLoading: false, error: null, refresh: () => undefined }),
}))

const workspaceContextStub: WorkspaceContextValue = {
  currentSkillId: 'story-deconstruction',
  navStack: [],
  activeFiles: {},
  activeFileDetails: {},
  splitMode: false,
  onFileOpen: () => undefined,
  openSplitEditor: () => undefined,
  closeFile: () => undefined,
  updateFileContent: () => undefined,
  markFileSaved: () => undefined,
  setFileInFlight: () => undefined,
  onSaveConflict: () => undefined,
  reloadOpenFile: async () => undefined,
  pushNavSkill: () => undefined,
  popNavTo: () => undefined,
}

function renderTimelinePanel(
  props: { runId: string | null; traceEvents: EventEnvelope[]; traceView?: TraceView | null },
  context: WorkspaceContextValue = workspaceContextStub,
): string {
  return renderToStaticMarkup(
    <WorkspaceProvider value={context}>
      <Panels
        activePanel="trace"
        skillId="story-deconstruction"
        selectedNode={null}
        runId={props.runId}
        traceView={props.traceView ?? null}
        onCloseTraceView={() => undefined}
        traceEvents={props.traceEvents}
        onResumeEdgeDownstream={() => undefined}
      />
    </WorkspaceProvider>,
  )
}

const oneEvent: EventEnvelope[] = [
  {
    schema_version: 'studio.event.v1',
    stream_id: 'run:run-1',
    seq: 1,
    cursor: 'run:run-1:1',
    run_id: 'run-1',
    event_type: 'phase_start',
    timestamp: '2026-06-13T00:00:00Z',
    payload: {
      schema_version: '1.0',
      event_type: 'phase_start',
      timestamp: '2026-06-13T00:00:00Z',
      phase_name: 'draft',
      run_id: 'run-1',
    },
  },
]

describe('Panels timeline region — viewed-run mount (F1/F2, decision 2026-08-07)', () => {
  it('mounts the live TracePanel fed by run-stream events while viewing the live run', () => {
    const html = renderTimelinePanel({ runId: 'run-1', traceEvents: oneEvent, traceView: { source: 'live' } })

    // TracePanel-only marker: the event list publishes what it rendered.
    expect(html).toContain('data-trace-step-count="1"')
    // Must NOT fall back to the run-history list while a run is streaming.
    expect(html).not.toContain('No runs recorded yet')
  })

  it('shows the run-history TimelinePanel when nothing is being viewed (F2)', () => {
    const html = renderTimelinePanel({ runId: null, traceEvents: [] })

    expect(html).toContain('No runs recorded yet')
    expect(html).not.toContain('data-trace-step-count=')
  })

  it('fix A regression lock: a lingering runId with no viewed run still shows the list', () => {
    // Before the viewed-run model, `runId` alone pinned this region to the last
    // run's stream forever — the history list became unreachable after the
    // first run. A closed trace view (traceView null) must show the list even
    // while runId is still set.
    const html = renderTimelinePanel({ runId: 'run-1', traceEvents: oneEvent, traceView: null })

    expect(html).toContain('No runs recorded yet')
    expect(html).not.toContain('data-trace-step-count=')
  })

  it('mounts a read-only TracePanel for a fetched historical run', () => {
    const html = renderTimelinePanel({
      runId: null,
      traceEvents: oneEvent,
      traceView: {
        source: 'history',
        runId: 'hist-1',
        metadata: {
          run_id: 'hist-1',
          status: 'success',
          started_at: '2026-08-07T00:00:00Z',
          kind: 'run',
          metrics: null,
          input_summary: null,
        },
      },
    })

    expect(html).toContain('data-trace-step-count="1"')
    expect(html).toContain('aria-label="Back to run list"')
    // Read-only replay: no run actions are wired for a historical view.
    expect(html).not.toContain('Resume run from last checkpoint')
  })

  it('gives an active selected edge precedence over the live trace stream', () => {
    const html = renderTimelinePanel(
      { runId: 'run-1', traceEvents: oneEvent, traceView: { source: 'live' } },
      {
        ...workspaceContextStub,
        selectedEdge: {
          id: 'draft->review',
          source: 'draft',
          target: 'review',
          contextJson: {
            blackboard_snapshot: { topic: 'cats' },
            changed_keys: ['topic'],
            checkpoint_id: 'checkpoint-review',
            checkpoint_ns: 'agent:review',
          },
        },
        setSelectedEdge: () => undefined,
      },
    )

    expect(html).toContain('Blackboard transition')
    expect(html).toContain('draft')
    expect(html).toContain('review')
    expect(html).not.toContain('data-trace-step-count=')
  })
})
