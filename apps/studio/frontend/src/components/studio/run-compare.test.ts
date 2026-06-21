import { describe, expect, it } from 'vitest'
import type { CompareCandidateRun, RunMetadata } from '@/api/types'
import { candidatesFromRoleNames, compareTabsFromGroup } from './run-compare'

function metadata(runId: string, status: RunMetadata['status']): RunMetadata {
  return {
    run_id: runId,
    status,
    started_at: '2026-06-20T00:00:00Z',
    metrics: null,
    input_summary: null,
  }
}

function candidateRun(candidateId: string, roleName: string, status: RunMetadata['status'], runId: string): CompareCandidateRun {
  return { candidate_id: candidateId, role_name: roleName, metadata: metadata(runId, status) }
}

describe('candidatesFromRoleNames (n4-trace#23 request shape)', () => {
  it('maps each role name to a candidate keyed by the role name', () => {
    expect(candidatesFromRoleNames(['writer', 'editor'])).toEqual([
      { candidate_id: 'writer', role_name: 'writer' },
      { candidate_id: 'editor', role_name: 'editor' },
    ])
  })

  it('drops blank and duplicate role names so the request never carries an empty/repeated candidate', () => {
    expect(candidatesFromRoleNames([' writer ', 'writer', '', '   ', 'editor'])).toEqual([
      { candidate_id: 'writer', role_name: 'writer' },
      { candidate_id: 'editor', role_name: 'editor' },
    ])
  })

  it('returns an empty list for no usable names', () => {
    expect(candidatesFromRoleNames(['', '  '])).toEqual([])
  })
})

describe('compareTabsFromGroup (per-candidate Trace tabs)', () => {
  it('projects each candidate run into a tab with its run id and status flags', () => {
    const tabs = compareTabsFromGroup([
      candidateRun('writer', 'writer', 'success', 'run-w'),
      candidateRun('editor', 'editor', 'failed', 'run-e'),
      candidateRun('critic', 'critic', 'running', 'run-c'),
    ])
    expect(tabs).toEqual([
      { candidateId: 'writer', roleName: 'writer', runId: 'run-w', failed: false, running: false },
      { candidateId: 'editor', roleName: 'editor', runId: 'run-e', failed: true, running: false },
      { candidateId: 'critic', roleName: 'critic', runId: 'run-c', failed: false, running: true },
    ])
  })

  it('reads per-candidate failure straight from metadata.status', () => {
    const [tab] = compareTabsFromGroup([candidateRun('editor', 'editor', 'failed', 'run-e')])
    expect(tab.failed).toBe(true)
  })
})
