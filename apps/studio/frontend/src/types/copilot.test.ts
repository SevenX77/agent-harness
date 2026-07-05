import { describe, expect, it } from 'vitest'
import { normalizeCopilotEvent } from './copilot'

describe('normalizeCopilotEvent', () => {
  // F1: the backend now streams a thinking_delta event; it must normalize to a
  // first-class thinking event (collapsible Thought), never fall to "unknown".
  it('maps a thinking_delta payload to a thinking event with its content', () => {
    const event = normalizeCopilotEvent(
      { type: 'thinking_delta', content: 'let me reason...' },
      'evt-1',
    )

    expect(event.type).toBe('thinking_delta')
    expect(event).toMatchObject({ id: 'evt-1', status: 'running', content: 'let me reason...' })
  })

  it('maps a context_resolved payload (F4 context echo) with summary + detail', () => {
    const event = normalizeCopilotEvent(
      { type: 'context_resolved', summary: 'Injected this turn: view=Edit', detail: '{...}' },
      'evt-ctx',
    )

    expect(event.type).toBe('context_resolved')
    expect(event).toMatchObject({ status: 'success', summary: 'Injected this turn: view=Edit', detail: '{...}' })
  })

  it('falls back to unknown for context_resolved missing detail', () => {
    const event = normalizeCopilotEvent({ type: 'context_resolved', summary: 'x' }, 'evt-bad')
    expect(event.type).toBe('unknown')
  })

  it('maps a text_delta payload to a text event', () => {
    const event = normalizeCopilotEvent({ type: 'text_delta', content: 'answer' }, 'evt-2')

    expect(event.type).toBe('text_delta')
    expect(event).toMatchObject({ status: 'running', content: 'answer' })
  })

  it('falls back to unknown for a thinking_delta missing string content', () => {
    const event = normalizeCopilotEvent({ type: 'thinking_delta', content: 42 }, 'evt-3')

    expect(event.type).toBe('unknown')
  })

  // F5: safe-write events must normalize so the diff bubble + Bash card render.
  it('maps a patch_proposed payload to a patch event with before/after', () => {
    const event = normalizeCopilotEvent(
      {
        type: 'patch_proposed',
        tool_use_id: 'tu-9',
        tool_name: 'Edit',
        path: 'GRAPH.md',
        before_existed: true,
        before_content: 'a\nold',
        after_content: 'a\nnew',
        before_hash: 'sha-before',
        after_hash: 'sha-after',
        diff: '@@ -1,2 +1,2 @@\n a\n-old\n+new',
        checkpoint_id: 'checkpoint-7',
      },
      'evt-patch',
    )

    expect(event.type).toBe('patch_proposed')
    expect(event).toMatchObject({
      toolUseId: 'tu-9',
      toolName: 'Edit',
      path: 'GRAPH.md',
      beforeExisted: true,
      beforeContent: 'a\nold',
      afterContent: 'a\nnew',
      beforeHash: 'sha-before',
      afterHash: 'sha-after',
      diff: '@@ -1,2 +1,2 @@\n a\n-old\n+new',
      checkpointId: 'checkpoint-7',
      review: 'pending',
    })
  })

  it('keeps old patch_proposed payloads compatible with conservative metadata fallbacks', () => {
    const event = normalizeCopilotEvent(
      {
        type: 'patch_proposed',
        tool_name: 'Write',
        path: 'GRAPH.md',
      },
      'evt-old-patch',
    )

    expect(event.type).toBe('patch_proposed')
    expect(event).toMatchObject({
      beforeHash: null,
      afterHash: '',
      diff: '',
      checkpointId: '',
    })
  })

  it('maps a tool_approval_required payload to a held tool event', () => {
    const event = normalizeCopilotEvent(
      {
        type: 'tool_approval_required',
        tool_use_id: 'tu-10',
        tool_name: 'Bash',
        detail: 'rm -rf x',
      },
      'evt-held',
    )

    expect(event.type).toBe('tool_approval_required')
    expect(event).toMatchObject({ toolName: 'Bash', detail: 'rm -rf x', status: 'pending' })
  })

  it('falls back to unknown for patch_proposed with a non-Write/Edit tool', () => {
    const event = normalizeCopilotEvent(
      { type: 'patch_proposed', tool_name: 'Bash', path: 'x' },
      'evt-bad-patch',
    )
    expect(event.type).toBe('unknown')
  })
})
