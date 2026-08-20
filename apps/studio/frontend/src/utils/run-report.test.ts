import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  rebuildRunReport: vi.fn(),
  toastError: vi.fn(),
}))

vi.mock('@/api/client', () => ({ rebuildRunReport: mocks.rebuildRunReport }))
vi.mock('sonner', () => ({ toast: { error: mocks.toastError } }))

const { openRunReport, runReportOpenRequest } = await import('./run-report')

const REPORT = '.workspace/runs/run-1/report.md'

beforeEach(() => {
  mocks.rebuildRunReport.mockReset()
  mocks.toastError.mockReset()
})

describe('runReportOpenRequest (PM 08-19 Q6: the report opens in the app)', () => {
  it('names the report as a read-only workspace document', () => {
    expect(runReportOpenRequest(REPORT)).toEqual({
      path: REPORT,
      title: 'Run report',
      language: 'markdown',
      saveEnabled: false,
    })
  })

  it('carries no content, so the editor loads the file itself', () => {
    // The report is on disk, not in the event stream. Leaving `content` unset
    // is what makes the editor read it — inventing a content field here would
    // mean the trace panel shipping its own file reader.
    expect(runReportOpenRequest(REPORT)).not.toHaveProperty('content')
  })
})

describe('openRunReport', () => {
  it('re-renders the report before opening it', async () => {
    // Without this, a run that finished before today's renderer existed opens
    // as whatever was rendered that day — the projection can be regenerated
    // (RUN_EXECUTION-5) but nothing ever regenerated it.
    mocks.rebuildRunReport.mockResolvedValue({ report_path: REPORT })
    const onFileOpen = vi.fn()

    await openRunReport({ skillId: 'demo', runId: 'run-1', reportPath: REPORT, onFileOpen })

    expect(mocks.rebuildRunReport).toHaveBeenCalledWith('demo', 'run-1')
    expect(onFileOpen).toHaveBeenCalledWith(runReportOpenRequest(REPORT))
  })

  it('opens the path the server answers with, not the one it was handed', async () => {
    mocks.rebuildRunReport.mockResolvedValue({ report_path: '.workspace/runs/moved/report.md' })
    const onFileOpen = vi.fn()

    await openRunReport({ skillId: 'demo', runId: 'run-1', reportPath: REPORT, onFileOpen })

    expect(onFileOpen).toHaveBeenCalledWith(
      runReportOpenRequest('.workspace/runs/moved/report.md'),
    )
  })

  it('still opens the report that is there when re-rendering fails, and says so', async () => {
    // The reader asked to read a run; last month's rendering answers that.
    // Showing nothing does not — but a renderer that cannot run is a fault, so
    // it is said out loud rather than swallowed.
    mocks.rebuildRunReport.mockRejectedValue(new Error('sidecar is down'))
    const onFileOpen = vi.fn()

    await openRunReport({ skillId: 'demo', runId: 'run-1', reportPath: REPORT, onFileOpen })

    expect(onFileOpen).toHaveBeenCalledWith(runReportOpenRequest(REPORT))
    expect(mocks.toastError).toHaveBeenCalledOnce()
  })

  it('opens directly when there is no run to re-render', async () => {
    const onFileOpen = vi.fn()

    await openRunReport({ skillId: 'demo', runId: null, reportPath: REPORT, onFileOpen })

    expect(mocks.rebuildRunReport).not.toHaveBeenCalled()
    expect(onFileOpen).toHaveBeenCalledWith(runReportOpenRequest(REPORT))
  })
})
