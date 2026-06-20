import { describe, expect, it } from 'vitest'
import { nextLocalHistoryRefreshKey } from './useRunHistory'

// N6 #2 (history-auto-refresh): when a run reaches run_ended the backend has
// autocommitted a new "Auto run" snapshot, so the Local History list must be
// revalidated exactly once on the not-ended → ended edge. nextLocalHistoryRefreshKey
// is the pure de-dupe rule behind the Workspace effect; these tests pin that
// contract (effects themselves are SSR-untestable, so the decision is extracted).
describe('nextLocalHistoryRefreshKey', () => {
  it('returns a refresh key when a run reaches run_ended for the first time', () => {
    expect(
      nextLocalHistoryRefreshKey({
        skillId: 'writer-smoke',
        completedRunId: 'run-1',
        lastRefreshedKey: null,
      }),
    ).toBe('writer-smoke::run-1')
  })

  it('does not refresh again for the same skill/run pair (fires once per run_ended edge)', () => {
    expect(
      nextLocalHistoryRefreshKey({
        skillId: 'writer-smoke',
        completedRunId: 'run-1',
        lastRefreshedKey: 'writer-smoke::run-1',
      }),
    ).toBeNull()
  })

  it('refreshes again when a newer run completes after a prior one', () => {
    expect(
      nextLocalHistoryRefreshKey({
        skillId: 'writer-smoke',
        completedRunId: 'run-2',
        lastRefreshedKey: 'writer-smoke::run-1',
      }),
    ).toBe('writer-smoke::run-2')
  })

  it('refreshes when the same run id completes under a different skill', () => {
    expect(
      nextLocalHistoryRefreshKey({
        skillId: 'other-skill',
        completedRunId: 'run-1',
        lastRefreshedKey: 'writer-smoke::run-1',
      }),
    ).toBe('other-skill::run-1')
  })

  it('does not refresh while the run has not ended yet (no completed run id)', () => {
    expect(
      nextLocalHistoryRefreshKey({
        skillId: 'writer-smoke',
        completedRunId: null,
        lastRefreshedKey: null,
      }),
    ).toBeNull()
  })

  it('does not refresh when no skill is active', () => {
    expect(
      nextLocalHistoryRefreshKey({
        skillId: null,
        completedRunId: 'run-1',
        lastRefreshedKey: null,
      }),
    ).toBeNull()
  })
})
