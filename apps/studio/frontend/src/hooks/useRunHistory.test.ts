import { describe, expect, it } from 'vitest'
import { archiveFeedbackForGitStatus, nextLocalHistoryRefreshKey } from './useRunHistory'

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

// N6 #1 (autocommit-feedback): after a successful run the backend records the
// autocommit outcome on the run metadata's git_status, and Workspace re-fetches
// the run detail to surface a one-shot toast. archiveFeedbackForGitStatus is the
// pure projection behind that effect; these tests pin every contract branch so a
// new/renamed status can never silently fall into the wrong message.
describe('archiveFeedbackForGitStatus', () => {
  it('reports a successful, revertable archive when committed', () => {
    const feedback = archiveFeedbackForGitStatus('committed')
    expect(feedback?.variant).toBe('success')
    expect(feedback?.message).toMatch(/Local History/i)
  })

  it('reports a benign no-repo archive (no revertable snapshot) when no_git', () => {
    const feedback = archiveFeedbackForGitStatus('no_git')
    expect(feedback?.variant).toBe('success')
    expect(feedback?.message).toMatch(/no git repo/i)
    // must NOT claim a revertable snapshot exists
    expect(feedback?.message).not.toMatch(/revert from Local History/i)
  })

  it('warns without claiming archive success when the git index was locked', () => {
    const feedback = archiveFeedbackForGitStatus('locked')
    expect(feedback?.variant).toBe('warning')
    expect(feedback?.message).toMatch(/not archived/i)
  })

  it('warns without claiming archive success when auto-commit failed', () => {
    const feedback = archiveFeedbackForGitStatus('failed')
    expect(feedback?.variant).toBe('warning')
    expect(feedback?.message).toMatch(/not archived/i)
  })

  it('stays silent (returns null) when git_status is null or absent', () => {
    expect(archiveFeedbackForGitStatus(null)).toBeNull()
    expect(archiveFeedbackForGitStatus(undefined)).toBeNull()
  })
})
