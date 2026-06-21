import { describe, expect, it } from 'vitest'
import type { EventEnvelope, ResumeValidityResponse } from '@/api/types'
import type { SkillNodeStatus } from '@/components/nodes'
import {
  dirtyDownstreamFromValidity,
  nodeResumeCheckpointFromEvents,
  nodeResumeOptionsFromValidity,
  resumeAnchorNodeId,
  shouldDeriveDirtyDownstream,
} from './node-resume'

function envelope(seq: number, phaseName: string, checkpointId: string, runId = 'run-1'): EventEnvelope {
  return {
    schema_version: 'studio.event.v1',
    stream_id: `run:${runId}`,
    seq,
    cursor: `run:${runId}:${seq}`,
    run_id: runId,
    event_type: 'validation_fail',
    timestamp: '2026-06-18T00:00:00Z',
    payload: {
      schema_version: '1.0',
      event_type: 'validation_fail',
      timestamp: '2026-06-18T00:00:00Z',
      run_id: runId,
      phase_name: phaseName,
      checkpoint_id: checkpointId,
      checkpoint_ns: `agent:${phaseName}`,
    },
  }
}

describe('nodeResumeCheckpointFromEvents', () => {
  it('discovers the latest checkpoint identity for a failed node without enumerating phase names', () => {
    const result = nodeResumeCheckpointFromEvents([
      envelope(1, 'draft', 'checkpoint-draft'),
      envelope(2, 'review', 'checkpoint-review-old'),
      envelope(3, 'review', 'checkpoint-review-new'),
    ], 'review', 'run-1')

    expect(result).toEqual({
      checkpointId: 'checkpoint-review-new',
      checkpointNs: 'agent:review',
    })
  })

  it('ignores checkpoint events from other active runs', () => {
    const result = nodeResumeCheckpointFromEvents([
      envelope(1, 'review', 'checkpoint-old-run', 'run-old'),
      envelope(2, 'review', 'checkpoint-active-run', 'run-2'),
    ], 'review', 'run-2')

    expect(result?.checkpointId).toBe('checkpoint-active-run')
  })
})

function validity(overrides: Partial<ResumeValidityResponse> = {}): ResumeValidityResponse {
  return {
    run_id: 'run-1',
    resume_allowed: true,
    reason: 'ok',
    checkpoint_id: 'checkpoint-review',
    checkpoint_ns: 'agent:review',
    resume_from_node_id: 'review',
    resume_to_node_id: null,
    dirty_fields: [],
    dirty_node_ids: [],
    affected_downstream: [],
    snapshot_content_hash: null,
    current_content_hash: null,
    snapshot_execution_fingerprint: null,
    current_execution_fingerprint: null,
    ...overrides,
  }
}

describe('resumeAnchorNodeId (N5 atom #3 — auto dirty-downstream anchor)', () => {
  it('anchors on the failed node so the affected-downstream slice can be derived without a manual selection', () => {
    const statusByNodeId: Record<string, SkillNodeStatus> = {
      draft: 'success',
      review: 'error',
      publish: 'idle',
    }
    expect(resumeAnchorNodeId(statusByNodeId)).toBe('review')
  })

  it('returns null when no node is in a failed state (nothing to anchor the auto-derive on)', () => {
    expect(resumeAnchorNodeId({ draft: 'success', review: 'idle' })).toBeNull()
    expect(resumeAnchorNodeId({})).toBeNull()
  })
})

describe('shouldDeriveDirtyDownstream (N5 atom #3 — auto edit-watcher gate)', () => {
  it('fires when a run + an anchor node exist, independent of which node is selected', () => {
    expect(
      shouldDeriveDirtyDownstream({ skillId: 'demo', runId: 'run-1', anchorNodeId: 'review' }),
    ).toBe(true)
  })

  it('does not fire when there is no run to derive validity against', () => {
    expect(
      shouldDeriveDirtyDownstream({ skillId: 'demo', runId: null, anchorNodeId: 'review' }),
    ).toBe(false)
  })

  it('does not fire when no node can anchor the slice (no failed node)', () => {
    expect(
      shouldDeriveDirtyDownstream({ skillId: 'demo', runId: 'run-1', anchorNodeId: null }),
    ).toBe(false)
  })

  it('does not fire without an active skill', () => {
    expect(
      shouldDeriveDirtyDownstream({ skillId: null, runId: 'run-1', anchorNodeId: 'review' }),
    ).toBe(false)
  })
})

describe('dirtyDownstreamFromValidity (N5 atom #3 — gray affected, keep unrelated runnable)', () => {
  it('grays exactly the affected-downstream set after an upstream edit', () => {
    // Upstream edit at `draft` reaches review+publish; `sidebranch` is unrelated.
    const dirty = dirtyDownstreamFromValidity(
      validity({ resume_allowed: false, reason: 'dirty_upstream', affected_downstream: ['draft', 'review', 'publish'] }),
    )
    expect(dirty.has('draft')).toBe(true)
    expect(dirty.has('review')).toBe(true)
    expect(dirty.has('publish')).toBe(true)
    // Unrelated side-branch stays non-grayed.
    expect(dirty.has('sidebranch')).toBe(false)
  })

  it('grays nothing when resume is clean (no affected downstream)', () => {
    expect(dirtyDownstreamFromValidity(validity({ resume_allowed: true, affected_downstream: [] })).size).toBe(0)
  })

  it('grays nothing for a null validity (no resume in progress)', () => {
    expect(dirtyDownstreamFromValidity(null).size).toBe(0)
  })
})

describe('nodeResumeOptionsFromValidity', () => {
  it('anchors the node-level resume request at the validity node id (resume_from_node_id)', () => {
    expect(nodeResumeOptionsFromValidity(validity(), 'review')).toEqual({
      checkpointId: 'checkpoint-review',
      checkpointNs: 'agent:review',
      resumeFromNodeId: 'review',
      resumeToNodeId: undefined,
    })
  })

  it('falls back to the selected node id when the engine omits resume_from_node_id', () => {
    const options = nodeResumeOptionsFromValidity(
      validity({ resume_from_node_id: null, checkpoint_id: null, checkpoint_ns: null }),
      'expand',
    )
    expect(options.resumeFromNodeId).toBe('expand')
    expect(options.checkpointId).toBeUndefined()
    expect(options.checkpointNs).toBeUndefined()
  })

  it('carries resume_to_node_id when the engine bounds the resume range', () => {
    const options = nodeResumeOptionsFromValidity(validity({ resume_to_node_id: 'publish' }), 'review')
    expect(options.resumeToNodeId).toBe('publish')
  })
})
