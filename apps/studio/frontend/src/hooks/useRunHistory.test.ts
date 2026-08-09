import { describe, expect, it } from 'vitest'
import type { RunMetadata, TokensMetrics } from '@/api/types'
import { archiveFeedbackForGitStatus, nextLocalHistoryRefreshKey, runOutcomeFeedback } from './useRunHistory'

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

// D7 (decision 2026-08-09): reaching a terminal state must SAY so. The archive
// toast above reports a git snapshot, not the run's conclusion — two different
// facts, so this is a second, independent projection rather than a rewording of
// the first. Pure so the wording is testable under SSR.
describe('runOutcomeFeedback', () => {
  const metrics = (partial: Partial<TokensMetrics> = {}): TokensMetrics => ({
    input_tokens: 120,
    output_tokens: 80,
    total_tokens: 200,
    cost_estimate: null,
    wall_time_sec: 12.5,
    ...partial,
  })

  const metadata = (partial: Partial<RunMetadata>): RunMetadata => ({
    run_id: 'run-20260809-101500-abcd',
    status: 'success',
    started_at: '2026-08-09T10:15:00Z',
    metrics: metrics(),
    input_summary: null,
    ...partial,
  })

  it('celebrates a successful run with its duration and token total', () => {
    const feedback = runOutcomeFeedback(metadata({ status: 'success' }))
    expect(feedback?.variant).toBe('success')
    expect(feedback?.message).toMatch(/succeeded/i)
    expect(feedback?.message).toContain('12.5s')
    expect(feedback?.message).toContain('200 tokens')
  })

  it('reports a failed run as an error, still with duration and tokens', () => {
    const feedback = runOutcomeFeedback(metadata({ status: 'failed' }))
    expect(feedback?.variant).toBe('error')
    expect(feedback?.message).toMatch(/failed/i)
    expect(feedback?.message).toContain('12.5s')
    expect(feedback?.message).toContain('200 tokens')
  })

  it('reports a cancelled run as an interruption, not a failure', () => {
    const feedback = runOutcomeFeedback(metadata({ status: 'cancelled' }))
    expect(feedback?.variant).toBe('warning')
    expect(feedback?.message).toMatch(/interrupted/i)
    expect(feedback?.message).not.toMatch(/failed/i)
  })

  it('omits the metrics clause instead of inventing zeros when metrics are absent', () => {
    const feedback = runOutcomeFeedback(metadata({ status: 'success', metrics: null }))
    expect(feedback?.variant).toBe('success')
    expect(feedback?.message).toMatch(/succeeded/i)
    expect(feedback?.message).not.toMatch(/token/i)
    expect(feedback?.message).not.toMatch(/n\/a/i)
  })

  it('keeps the tokens clause when only the wall time is missing', () => {
    const feedback = runOutcomeFeedback(
      metadata({ status: 'success', metrics: metrics({ wall_time_sec: null }) }),
    )
    expect(feedback?.message).toContain('200 tokens')
    expect(feedback?.message).not.toMatch(/n\/a/i)
  })

  it('renders a sub-second run in milliseconds', () => {
    const feedback = runOutcomeFeedback(
      metadata({ status: 'success', metrics: metrics({ wall_time_sec: 0.42 }) }),
    )
    expect(feedback?.message).toContain('420ms')
  })

  it('names the rehearsal instead of the run when the run is a predict', () => {
    const feedback = runOutcomeFeedback(metadata({ status: 'success', kind: 'predict' }))
    expect(feedback?.message).toMatch(/predict/i)
    expect(feedback?.message).not.toMatch(/^Run /)
  })

  it('stays silent for a run that has not concluded (running / paused)', () => {
    expect(runOutcomeFeedback(metadata({ status: 'running' }))).toBeNull()
    expect(runOutcomeFeedback(metadata({ status: 'paused' }))).toBeNull()
  })
})
