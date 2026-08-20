import { toast } from 'sonner'
import { rebuildRunReport } from '@/api/client'
import { errorMessage } from '@/utils/errors'
import type { FileOpenRequest } from '@/components/studio/file-types'

/**
 * The report as a workspace document — the editor opens it, not the OS.
 *
 * `report_path` arrives workspace-relative for exactly this reason, and the
 * editor loads the content itself when a request carries none. Read-only:
 * the report is a projection of the run (decision 2026-08-09 D8), so an
 * editable copy would be a second truth about a finished run.
 */
export function runReportOpenRequest(reportPath: string): FileOpenRequest {
  return { path: reportPath, title: 'Run report', language: 'markdown', saveEnabled: false }
}

/**
 * Open a run's report, re-rendered first so it reads as today's renderer writes.
 *
 * `report.md` is written once, when the run is sealed, and the design calls it a
 * projection that can be regenerated at any time (RUN_EXECUTION-5). Nothing used
 * to regenerate one, so every report stayed frozen on the rendering logic of the
 * day its run finished. Asking to read it is both the moment the freshness
 * matters and the moment the work is cheap: one run, one write, one reader.
 *
 * A rebuild that fails still opens the report that is there. The reader asked to
 * read a run, and a rendering from last month answers that question; refusing to
 * show anything does not. The failure is still said out loud rather than
 * swallowed, because a renderer that cannot run is a fault, not a preference.
 */
export async function openRunReport(params: {
  skillId: string | null | undefined
  runId: string | null | undefined
  reportPath: string
  onFileOpen: (file: FileOpenRequest) => void
}): Promise<void> {
  const { skillId, runId, reportPath, onFileOpen } = params
  if (!skillId || !runId) {
    onFileOpen(runReportOpenRequest(reportPath))
    return
  }
  try {
    const refreshed = await rebuildRunReport(skillId, runId)
    onFileOpen(runReportOpenRequest(refreshed.report_path ?? reportPath))
  } catch (error) {
    toast.error(`Could not re-render the run report: ${errorMessage(error)}`)
    onFileOpen(runReportOpenRequest(reportPath))
  }
}
