import { describe, expect, it } from 'vitest'
import type { EventEnvelope } from '@/api/types'
import { buildHitlResumeRequest, latestHitlPrompt } from './hitl-prompt'

function envelope(payload: Record<string, unknown>, seq = 1): EventEnvelope {
  return {
    schema_version: 'studio.event.v1',
    stream_id: 'run:run-1',
    seq,
    cursor: `run:run-1:${seq}`,
    run_id: 'run-1',
    event_type: String(payload.event_type ?? ''),
    timestamp: '2026-06-19T00:00:00Z',
    payload: {
      schema_version: '1.0',
      timestamp: '2026-06-19T00:00:00Z',
      ...payload,
    } as EventEnvelope['payload'],
  }
}

// Field shape verified against the REAL engine InterruptedEvent
// (packages/graph-agent/src/graph_agent/callbacks/events.py:408): it carries
// phase_name, checkpoint_id, checkpoint_ns, question, options — and crucially
// does NOT carry tool_call_id or pending_tool_calls.
const liveInterrupted = envelope({
  event_type: 'interrupted',
  phase_name: 'review',
  question: 'Approve the generated draft?',
  options: ['Approve', 'Revise'],
  checkpoint_id: 'checkpoint-review',
  checkpoint_ns: 'agent:review',
})

describe('latestHitlPrompt', () => {
  it('extracts the prompt from a live engine interrupted event (no tool_call_id)', () => {
    const prompt = latestHitlPrompt([liveInterrupted])
    expect(prompt).not.toBeNull()
    expect(prompt?.phaseName).toBe('review')
    expect(prompt?.question).toBe('Approve the generated draft?')
    expect(prompt?.options).toEqual(['Approve', 'Revise'])
    expect(prompt?.checkpointId).toBe('checkpoint-review')
    expect(prompt?.checkpointNs).toBe('agent:review')
    // Real InterruptedEvent has no tool_call_id / pending_tool_calls — must degrade.
    expect(prompt?.toolCallId).toBeNull()
    expect(prompt?.pendingToolCalls).toEqual([])
  })

  it('returns null when there is no interrupt event in the stream', () => {
    const running = envelope({ event_type: 'phase_start', phase_name: 'review' })
    expect(latestHitlPrompt([running])).toBeNull()
  })

  it('returns null for an empty event stream', () => {
    expect(latestHitlPrompt([])).toBeNull()
  })

  it('reads multiple pending tool calls when the payload provides them', () => {
    const multi = envelope({
      event_type: 'interrupted',
      phase_name: 'review',
      question: 'Choose the pending human input to answer.',
      pending_tool_calls: [
        { id: 'tool-a', question: 'Approve outline?', options: ['Approve outline'] },
        { id: 'tool-b', question: 'Approve citations?', options: ['Approve citations'] },
      ],
      checkpoint_id: 'checkpoint-review',
    })
    const prompt = latestHitlPrompt([multi])
    expect(prompt?.pendingToolCalls.map((toolCall) => toolCall.toolCallId)).toEqual(['tool-a', 'tool-b'])
  })
})

describe('buildHitlResumeRequest', () => {
  it('packs the full TraceHitlResumeRequest (all five fields) from a live prompt', () => {
    const prompt = latestHitlPrompt([liveInterrupted])
    const request = buildHitlResumeRequest({ prompt, draft: '  Approve  ', selectedToolCallId: null })
    expect(request).toEqual({
      content: 'Approve',
      phaseName: 'review',
      // Live engine event has no tool call id → null (field still present in shape).
      toolCallId: null,
      checkpointId: 'checkpoint-review',
      checkpointNs: 'agent:review',
    })
  })

  it('returns null when the draft is empty (nothing to submit)', () => {
    const prompt = latestHitlPrompt([liveInterrupted])
    expect(buildHitlResumeRequest({ prompt, draft: '   ', selectedToolCallId: null })).toBeNull()
  })

  it('returns null when there is no prompt', () => {
    expect(buildHitlResumeRequest({ prompt: null, draft: 'anything', selectedToolCallId: null })).toBeNull()
  })

  it('blocks submission until a pending tool call is selected, then targets it', () => {
    const multi = envelope({
      event_type: 'interrupted',
      phase_name: 'review',
      pending_tool_calls: [
        { id: 'tool-a', question: 'Approve outline?', options: [] },
        { id: 'tool-b', question: 'Approve citations?', options: [] },
      ],
      checkpoint_id: 'checkpoint-review',
    })
    const prompt = latestHitlPrompt([multi])
    // No selection among multiple pending calls → cannot submit.
    expect(buildHitlResumeRequest({ prompt, draft: 'yes', selectedToolCallId: null })).toBeNull()
    // Selecting one routes the answer to that tool_call_id.
    const request = buildHitlResumeRequest({ prompt, draft: 'yes', selectedToolCallId: 'tool-b' })
    expect(request?.toolCallId).toBe('tool-b')
  })
})
