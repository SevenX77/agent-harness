import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import type { CallbackEvent } from '@/api/types'
import { WorkspaceProvider, type WorkspaceContextValue } from '../WorkspaceContext'
import { Panels } from './Panels'

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

function renderTimelinePanel(props: { runId: string | null; traceEvents: CallbackEvent[] }): string {
  return renderToStaticMarkup(
    <WorkspaceProvider value={workspaceContextStub}>
      <Panels
        activePanel="timeline"
        skillId="story-deconstruction"
        selectedNode={null}
        runId={props.runId}
        traceEvents={props.traceEvents}
      />
    </WorkspaceProvider>,
  )
}

const oneEvent: CallbackEvent[] = [
  {
    schema_version: '1.0',
    event_type: 'phase_start',
    timestamp: '2026-06-13T00:00:00Z',
    phase_name: 'draft',
    run_id: 'run-1',
  },
]

describe('Panels timeline region — live trace mount (F1)', () => {
  it('mounts the live TracePanel fed by run-stream events when a run is active', () => {
    const html = renderTimelinePanel({ runId: 'run-1', traceEvents: oneEvent })

    // TracePanel-only markers (search/filter shell + event count summary).
    expect(html).toContain('Showing 1 of 1 events')
    // Must NOT fall back to the run-history list while a run is streaming.
    expect(html).not.toContain('No runs recorded yet')
  })

  it('shows the run-history TimelinePanel when no run is active (F2)', () => {
    const html = renderTimelinePanel({ runId: null, traceEvents: [] })

    expect(html).toContain('No runs recorded yet')
    expect(html).not.toContain('Showing 0 of 0 events')
  })
})
