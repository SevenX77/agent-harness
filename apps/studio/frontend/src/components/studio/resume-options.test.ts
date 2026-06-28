import { describe, expect, it } from 'vitest'
import { hitlResumeOptionsFromRequest } from './resume-options'

describe('hitlResumeOptionsFromRequest', () => {
  it('maps a TracePanel HitL request into the structured resume API payload options', () => {
    expect(hitlResumeOptionsFromRequest({
      content: 'approved',
      phaseName: 'review',
      toolCallId: 'tool-1',
      checkpointId: 'checkpoint-review',
      checkpointNs: 'agent:review',
    })).toEqual({
      checkpointId: 'checkpoint-review',
      checkpointNs: 'agent:review',
      resumeFromNodeId: 'review',
      humanResponse: {
        content: 'approved',
        toolCallId: 'tool-1',
      },
    })
  })
})
