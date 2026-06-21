import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import type { EventEnvelope } from '@/api/types'
import { WorkspaceProvider, type WorkspaceContextValue } from '../WorkspaceContext'
import { Panels } from './Panels'

// TraceDocumentPanel mounts the heavy Monaco editor at module scope; stub it so this
// stays a pure SSR render-contract test. The panel's own chrome (heading + event
// count) renders without the editor, which is all this contract asserts.
vi.mock('@monaco-editor/react', () => ({ default: () => null }))

// HistoryPanel pulls run history over SWR/API; stub so non-trace branches render
// deterministically without a network layer.
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

const twoEvents: EventEnvelope[] = [
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
  {
    schema_version: 'studio.event.v1',
    stream_id: 'run:run-1',
    seq: 2,
    cursor: 'run:run-1:2',
    run_id: 'run-1',
    event_type: 'phase_complete',
    timestamp: '2026-06-13T00:00:01Z',
    payload: {
      schema_version: '1.0',
      event_type: 'phase_complete',
      timestamp: '2026-06-13T00:00:01Z',
      phase_name: 'draft',
      run_id: 'run-1',
    },
  },
]

function renderTraceDoc(
  props: { traceEvents: EventEnvelope[]; selectedNode?: { id: string; data: { label: string } } | null },
): string {
  return renderToStaticMarkup(
    <WorkspaceProvider value={workspaceContextStub}>
      <Panels
        activePanel="trace-doc"
        skillId="story-deconstruction"
        selectedNode={(props.selectedNode ?? null) as never}
        runId="run-1"
        traceEvents={props.traceEvents}
      />
    </WorkspaceProvider>,
  )
}

describe('Panels trace-doc region — full-trace document mount (n4-trace #18)', () => {
  it('renders the read-only TraceDocumentPanel when the trace-doc panel kind is selected', () => {
    const html = renderTraceDoc({ traceEvents: twoEvents })

    // TraceDocumentPanel-only markers — proves the panel is reachable, not dead code.
    expect(html).toContain('aria-label="Full trace document"')
    expect(html).toContain('Full Trace')
    // Surfaces the run-stream event count the live Event Trace panel was fed.
    expect(html).toContain('2 events')
  })

  it('is the full-trace document, not the live Event Trace (TracePanel) list', () => {
    const html = renderTraceDoc({ traceEvents: twoEvents })

    // The live trace stream renders TracePanel's "Showing N of N events" search shell;
    // the trace-doc kind must render the document surface instead.
    expect(html).not.toContain('Showing 2 of 2 events')
  })

  it('renders the document surface even before any events stream in (empty run)', () => {
    const html = renderTraceDoc({ traceEvents: [] })

    expect(html).toContain('aria-label="Full trace document"')
    expect(html).toContain('0 events')
  })
})
