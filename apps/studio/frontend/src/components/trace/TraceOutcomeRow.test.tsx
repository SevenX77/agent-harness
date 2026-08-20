// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import { WorkspaceProvider, type WorkspaceContextValue } from '../studio/WorkspaceContext'
import type { TraceOutcomeEntry } from '../../utils/trace-outcome'
import { runReportOpenRequest } from '../../utils/run-report'
import { TraceOutcomeRow } from './TraceOutcomeRow'

const mocks = vi.hoisted(() => ({ rebuildRunReport: vi.fn() }))
vi.mock('@/api/client', () => ({ rebuildRunReport: mocks.rebuildRunReport }))

// React 19's act() warns unless the environment opts in.
;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

function outcome(overrides: Partial<TraceOutcomeEntry> = {}): TraceOutcomeEntry {
  return {
    status: 'success',
    wallTimeSec: 12,
    totalTokens: 400,
    reportPath: null,
    runId: 'run-1',
    ...overrides,
  }
}

function workspaceValue(onFileOpen: WorkspaceContextValue['onFileOpen']): WorkspaceContextValue {
  return {
    currentSkillId: 'demo',
    navStack: [],
    activeFiles: {},
    activeFileDetails: {},
    splitMode: false,
    onFileOpen,
    openSplitEditor: () => {},
    closeFile: () => {},
    updateFileContent: () => {},
    markFileSaved: () => {},
    setFileInFlight: () => {},
    onSaveConflict: () => {},
    reloadOpenFile: async () => {},
    pushNavSkill: () => {},
    popNavTo: () => {},
  }
}

describe('TraceOutcomeRow report entry', () => {
  it('opens the report through workspace onFileOpen, not the operating system', async () => {
    mocks.rebuildRunReport.mockResolvedValue({ report_path: '.workspace/runs/run-1/report.md' })
    const onFileOpen = vi.fn()
    const container = document.createElement('div')
    document.body.appendChild(container)
    const root = createRoot(container)
    act(() => {
      root.render(
        <WorkspaceProvider value={workspaceValue(onFileOpen)}>
          <TraceOutcomeRow outcome={outcome({ reportPath: '.workspace/runs/run-1/report.md' })} />
        </WorkspaceProvider>,
      )
    })

    const button = container.querySelector('[data-trace-outcome-report]') as HTMLButtonElement
    expect(button).not.toBeNull()
    await act(async () => {
      button.click()
    })
    // The report is re-rendered first, so what opens is today's rendering of
    // this run rather than the one written the day it finished.
    expect(mocks.rebuildRunReport).toHaveBeenCalledWith('demo', 'run-1')
    expect(onFileOpen).toHaveBeenCalledWith(runReportOpenRequest('.workspace/runs/run-1/report.md'))

    act(() => {
      root.unmount()
    })
    container.remove()
  })

  it('offers no report entry when the run left no report', () => {
    const html = renderToStaticMarkup(
      <WorkspaceProvider value={workspaceValue(vi.fn())}>
        <TraceOutcomeRow outcome={outcome({ reportPath: null })} />
      </WorkspaceProvider>,
    )
    expect(html).not.toContain('Open run report')
  })
})
