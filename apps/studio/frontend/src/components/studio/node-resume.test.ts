import { describe, expect, it } from 'vitest'
import type { EventEnvelope } from '@/api/types'
import { nodeResumeCheckpointFromEvents } from './node-resume'

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
