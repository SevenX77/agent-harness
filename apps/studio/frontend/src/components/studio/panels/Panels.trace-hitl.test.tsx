import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import type { EventEnvelope } from '@/api/types'
import { WorkspaceProvider, type WorkspaceContextValue } from '../WorkspaceContext'
import { Panels } from './Panels'

const tracePanelProps = vi.hoisted(() => [] as Array<Record<string, unknown>>)

vi.mock('@/components/TracePanel', () => ({
  TracePanel: (props: Record<string, unknown>) => {
    tracePanelProps.push(props)
    return <div data-testid="trace-panel" />
  },
}))

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

const oneEvent: EventEnvelope[] = [
  {
    schema_version: 'studio.event.v1',
    stream_id: 'run:run-1',
    seq: 1,
    cursor: 'run:run-1:1',
    run_id: 'run-1',
    event_type: 'interrupted',
    timestamp: '2026-06-13T00:00:00Z',
    payload: {
      schema_version: '1.0',
      event_type: 'interrupted',
      timestamp: '2026-06-13T00:00:00Z',
      phase_name: 'review',
      run_id: 'run-1',
      question: 'Approve?',
      tool_call_id: 'tool-1',
    },
  },
]

describe('Panels timeline HitL bridge', () => {
  it('passes the HitL submit callback through to the live TracePanel', () => {
    const onSubmitHitlResponse = vi.fn()

    renderToStaticMarkup(
      <WorkspaceProvider value={workspaceContextStub}>
        <Panels
          activePanel="timeline"
          skillId="story-deconstruction"
          selectedNode={null}
          runId="run-1"
          traceView={{ source: "live" }}
          traceEvents={oneEvent}
          onSubmitHitlResponse={onSubmitHitlResponse}
        />
      </WorkspaceProvider>,
    )

    expect(tracePanelProps.at(-1)?.onSubmitHitlResponse).toBe(onSubmitHitlResponse)
  })
})
