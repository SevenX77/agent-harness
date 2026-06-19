import { describe, expect, it } from 'vitest'
import { edgeTamperResumeOptionsFromJson } from './edge-tamper'
import type { SelectedEdge } from '../WorkspaceContext'

const selectedEdge: SelectedEdge = {
  id: 'draft->review',
  source: 'draft',
  target: 'review',
  contextJson: {
    blackboard_snapshot: { topic: 'cats' },
    checkpoint_id: 'checkpoint-review',
    checkpoint_ns: 'agent:review',
  },
}

describe('edgeTamperResumeOptionsFromJson', () => {
  it('maps edited edge context JSON to downstream resume options', () => {
    expect(edgeTamperResumeOptionsFromJson(selectedEdge, '{"topic":"dogs"}')).toEqual({
      ok: true,
      options: {
        checkpointId: 'checkpoint-review',
        checkpointNs: 'agent:review',
        resumeFromNodeId: 'review',
        contextOverrides: { topic: 'dogs' },
      },
    })
  })

  it('rejects invalid JSON before the resume request can be sent', () => {
    const result = edgeTamperResumeOptionsFromJson(selectedEdge, '{"topic":')

    expect(result.ok).toBe(false)
    if (!result.ok) {
      expect(result.error).toContain('Invalid JSON')
    }
  })
})
