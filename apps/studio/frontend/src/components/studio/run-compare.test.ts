import { describe, expect, it } from 'vitest'
import type { CompareCandidateRun, RunMetadata } from '@/api/types'
import { compareTabsFromGroup } from './run-compare'

function metadata(runId: string, status: RunMetadata['status']): RunMetadata {
  return {
    run_id: runId,
    status,
    started_at: '2026-06-20T00:00:00Z',
    metrics: null,
    input_summary: null,
  }
}

function candidateRun(
  candidateId: string,
  label: string,
  status: RunMetadata['status'],
  runId: string,
): CompareCandidateRun {
  return { candidate_id: candidateId, label, metadata: metadata(runId, status) }
}

describe('compareTabsFromGroup (per-candidate Trace tabs)', () => {
  it('projects each candidate side-run into a tab with its label, run id and status flags', () => {
    const tabs = compareTabsFromGroup([
      candidateRun('fast', 'deepseek-v4', 'success', 'run-f'),
      candidateRun('slow', 'claude-opus', 'failed', 'run-s'),
      candidateRun('mid', 'gpt-x', 'running', 'run-m'),
    ])
    expect(tabs).toEqual([
      { candidateId: 'fast', label: 'deepseek-v4', runId: 'run-f', failed: false, running: false },
      { candidateId: 'slow', label: 'claude-opus', runId: 'run-s', failed: true, running: false },
      { candidateId: 'mid', label: 'gpt-x', runId: 'run-m', failed: false, running: true },
    ])
  })

  it('reads per-candidate failure straight from metadata.status', () => {
    const [tab] = compareTabsFromGroup([candidateRun('slow', 'claude-opus', 'failed', 'run-s')])
    expect(tab.failed).toBe(true)
  })
})
