import type { CompareCandidateRun } from '@/api/types'

/**
 * PR2 node-level Compare LLMs: pure helper backing the Trace compare tabs.
 *
 * Compare runs are node-scoped isolated single-node side-runs (one per model
 * candidate), spawned off a base run. The grouped `CompareCandidateRun[]` from
 * the backend projects into Trace top tabs — one tab per candidate, its label =
 * the candidate model group, per-candidate failure read from each run's
 * `metadata.status`. Kept pure so the tab projection is unit-testable without
 * rendering the panel.
 */

export interface CompareTab {
  candidateId: string
  /** Tab label = the candidate model group. */
  label: string
  runId: string
  /** Per-candidate failure: read straight from the spawned side-run's status. */
  failed: boolean
  running: boolean
}

/**
 * Project the grouped per-candidate side-runs into ordered Trace top tabs. Each
 * tab is one candidate; `failed` / `running` come from that side-run's
 * `metadata.status`. Order follows the backend's response order (stable across
 * polls).
 */
export function compareTabsFromGroup(runs: readonly CompareCandidateRun[]): CompareTab[] {
  return runs.map((run) => ({
    candidateId: run.candidate_id,
    label: run.label,
    runId: run.metadata.run_id,
    failed: run.metadata.status === 'failed',
    running: run.metadata.status === 'running',
  }))
}
