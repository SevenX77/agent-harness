import type { CompareCandidateRun, RunCandidate } from '@/api/types'

/**
 * n4-trace#23 (P8 model-compare): pure helpers backing the run-compare flow.
 *
 * The compare run references roles that already exist in Settings (llm_roles.yaml);
 * the user picks role names, we turn them into `RunCandidate[]` for the
 * `POST /runs/compare` request, and turn the grouped `CompareCandidateRun[]`
 * response into Trace top tabs (one tab per candidate, per-candidate failure read
 * from each run's `metadata.status`). Kept pure + string-only so the request
 * shape and tab projection are unit-testable without rendering the panel.
 */

/**
 * Build the `candidates` request payload from selected Settings role names.
 *
 * `candidate_id` defaults to the role name (each role compared at most once);
 * `target_role` is left unset so the candidate role overrides every graph_agent
 * role (the design's default — narrow it only when a phase binds a named role).
 * Blank / duplicate role names are dropped so the request never carries an empty
 * or repeated candidate the backend would reject.
 */
export function candidatesFromRoleNames(roleNames: readonly string[]): RunCandidate[] {
  const seen = new Set<string>()
  const candidates: RunCandidate[] = []
  for (const raw of roleNames) {
    const roleName = raw.trim()
    if (!roleName || seen.has(roleName)) {
      continue
    }
    seen.add(roleName)
    candidates.push({ candidate_id: roleName, role_name: roleName })
  }
  return candidates
}

export interface CompareTab {
  candidateId: string
  roleName: string
  runId: string
  /** Per-candidate failure (atom #23): read straight from the spawned run's status. */
  failed: boolean
  running: boolean
}

/**
 * Project the grouped per-candidate runs into ordered Trace top tabs. Each tab is
 * one candidate; `failed` / `running` come from that candidate run's
 * `metadata.status` so the panel can mark a failed candidate's tab. Order follows
 * the backend's response order (stable for the user across polls).
 */
export function compareTabsFromGroup(runs: readonly CompareCandidateRun[]): CompareTab[] {
  return runs.map((run) => ({
    candidateId: run.candidate_id,
    roleName: run.role_name,
    runId: run.metadata.run_id,
    failed: run.metadata.status === 'failed',
    running: run.metadata.status === 'running',
  }))
}
