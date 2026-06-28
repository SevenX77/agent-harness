import { describe, expect, it } from 'vitest'
import { edgeTamperResumeOptionsFromJson, validateTamperJson } from './edge-tamper'
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

describe('validateTamperJson', () => {
  it('accepts a well-formed JSON object so the writable editor reads valid', () => {
    expect(validateTamperJson('{"topic":"dogs"}')).toEqual({ ok: true })
  })

  it('rejects malformed JSON with the same syntax error the resume path uses', () => {
    expect(validateTamperJson('{"topic":')).toEqual({
      ok: false,
      error: 'Invalid JSON: fix the edited context before resuming downstream.',
    })
  })

  it('rejects valid JSON that is not a plain object (arrays / primitives)', () => {
    expect(validateTamperJson('[1,2,3]')).toEqual({
      ok: false,
      error: 'Invalid JSON: edge context overrides must be a JSON object.',
    })
    expect(validateTamperJson('"just a string"').ok).toBe(false)
  })

  it('shares the accept/reject contract with the resume payload builder', () => {
    const valid = '{"topic":"dogs"}'
    const invalid = '{"topic":'
    expect(validateTamperJson(valid).ok).toBe(edgeTamperResumeOptionsFromJson(selectedEdge, valid).ok)
    expect(validateTamperJson(invalid).ok).toBe(edgeTamperResumeOptionsFromJson(selectedEdge, invalid).ok)
  })
})
