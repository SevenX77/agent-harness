// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import { WorkspaceProvider, type WorkspaceContextValue } from '../studio/WorkspaceContext'
import type { TraceOutcomeEntry } from '../../utils/trace-outcome'
import { TraceOutcomeRow, runReportOpenRequest } from './TraceOutcomeRow'

// React 19's act() warns unless the environment opts in.
;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

function outcome(overrides: Partial<TraceOutcomeEntry> = {}): TraceOutcomeEntry {
  return { status: 'success', wallTimeSec: 12, totalTokens: 400, reportPath: null, ...overrides }
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

describe('runReportOpenRequest (PM 08-19 Q6: the report opens in the app)', () => {
  it('names the report as a read-only workspace document', () => {
    expect(runReportOpenRequest('.workspace/runs/run-1/report.md')).toEqual({
      path: '.workspace/runs/run-1/report.md',
      title: 'Run report',
      language: 'markdown',
      saveEnabled: false,
    })
  })

  it('carries no content, so the editor loads the file itself', () => {
    // The report is on disk, not in the event stream. Leaving `content` unset
    // is what makes the editor read it — inventing a content field here would
    // mean the trace panel shipping its own file reader.
    expect(runReportOpenRequest('.workspace/runs/run-1/report.md')).not.toHaveProperty('content')
  })
})

describe('TraceOutcomeRow report entry', () => {
  it('opens the report through workspace onFileOpen, not the operating system', () => {
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
    act(() => {
      button.click()
    })
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
