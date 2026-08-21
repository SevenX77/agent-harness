import { beforeEach, describe, expect, it } from 'vitest'

import { copilotStore } from '../store/copilotStore'
import type {
  CopilotEvent,
  CopilotMessage,
  CopilotTextDeltaEvent,
  CopilotThinkingDeltaEvent,
} from '../types/copilot'
import {
  assistantMessageAfterEvent,
  buildCopilotSendPayload,
  flushDeltaQueue,
  visibleCopilotSocketError,
} from './useCopilot'

function assistantMessage(overrides: Partial<CopilotMessage> = {}): CopilotMessage {
  return {
    id: 'assistant-1',
    role: 'assistant',
    content: '',
    events: [],
    status: 'running',
    createdAt: 1,
    ...overrides,
  }
}

function textDelta(id: string, content: string): CopilotTextDeltaEvent {
  return { id, type: 'text_delta', status: 'running', receivedAt: 1, raw: null, content }
}

function thinkingDelta(id: string, content: string): CopilotThinkingDeltaEvent {
  return { id, type: 'thinking_delta', status: 'running', receivedAt: 1, raw: null, content }
}

function eventOf(type: 'done' | 'error' | 'context_resolved' | 'tool_use_start'): CopilotEvent {
  const base = { id: `e-${type}`, receivedAt: 1, raw: null }
  switch (type) {
    case 'done':
      return { ...base, type, status: 'success' }
    case 'error':
      return { ...base, type, status: 'error', message: 'boom' }
    case 'context_resolved':
      return { ...base, type, status: 'success', summary: 'ctx', detail: 'detail' }
    case 'tool_use_start':
      return { ...base, type, status: 'running', tool_name: 'Read', tool_input: {} }
  }
}

describe('assistantMessageAfterEvent', () => {
  // F8-4: message status is a lifecycle (running → success|error) driven ONLY by
  // terminal events. R5 root cause: context_resolved's event-level 'success'
  // used to overwrite the message status and kill the thinking indicator.
  it('keeps the message running across intermediate events', () => {
    const message = assistantMessage()

    const afterContext = assistantMessageAfterEvent(message, eventOf('context_resolved'))
    expect(afterContext.status).toBe('running')
    expect(afterContext.events).toHaveLength(1)

    const afterTool = assistantMessageAfterEvent(afterContext, eventOf('tool_use_start'))
    expect(afterTool.status).toBe('running')
    expect(afterTool.events).toHaveLength(2)
  })

  it('settles the message only on terminal events', () => {
    expect(assistantMessageAfterEvent(assistantMessage(), eventOf('done')).status).toBe('success')
    expect(assistantMessageAfterEvent(assistantMessage(), eventOf('error')).status).toBe('error')
  })
})

describe('flushDeltaQueue', () => {
  let messageId: string

  beforeEach(async () => {
    copilotStore.reset('skill-1')
    const sessionId = copilotStore.newSession()
    const message = assistantMessage()
    messageId = message.id
    await copilotStore.appendMessage(message, sessionId)
  })

  it('coalesces same-type runs and accumulates text into message content', () => {
    flushDeltaQueue([
      { messageId, event: thinkingDelta('t1', 'let me ') },
      { messageId, event: thinkingDelta('t2', 'reason') },
      { messageId, event: textDelta('x1', 'Hel') },
      { messageId, event: textDelta('x2', 'lo') },
    ])

    const message = copilotStore.getSnapshot().messages[0]
    expect(message.content).toBe('Hello')
    expect(message.status).toBe('running')
    expect(message.events.map((e) => e.type)).toEqual(['thinking_delta', 'text_delta'])
    expect((message.events[0] as CopilotThinkingDeltaEvent).content).toBe('let me reason')
    expect((message.events[1] as CopilotTextDeltaEvent).content).toBe('Hello')
  })

  it('merges across flush windows into the trailing event so events stay bounded', () => {
    flushDeltaQueue([{ messageId, event: textDelta('x1', 'Hel') }])
    flushDeltaQueue([{ messageId, event: textDelta('x2', 'lo') }])

    const message = copilotStore.getSnapshot().messages[0]
    expect(message.content).toBe('Hello')
    expect(message.events).toHaveLength(1)
    expect((message.events[0] as CopilotTextDeltaEvent).content).toBe('Hello')
  })

  it('is a no-op on an empty queue', () => {
    flushDeltaQueue([])
    expect(copilotStore.getSnapshot().messages[0].events).toHaveLength(0)
  })
})

describe('buildCopilotSendPayload', () => {
  // 会话身份契约(COPILOT_ASSIST-5):每条报文必带发起标签的 session_id,
  // 后端以它隔离 SDK 对话——缺了它就是"消息注入别人对话"的缺陷本体。
  it('always carries the owning session id alongside the user message', () => {
    expect(buildCopilotSendPayload('hello', 'session-1')).toEqual({
      user_message: 'hello',
      session_id: 'session-1',
    })
  })

  it('attaches the selected role so the composer picker reaches the ws payload', () => {
    expect(buildCopilotSendPayload('hello', 'session-1', { role: 'copilot_judge' })).toEqual({
      user_message: 'hello',
      session_id: 'session-1',
      role: 'copilot_judge',
    })
  })

  it('keeps model_override behavior intact alongside role', () => {
    expect(buildCopilotSendPayload('hello', 'session-1', { modelOverride: 'anthropic:claude', role: 'copilot_chat' })).toEqual({
      user_message: 'hello',
      session_id: 'session-1',
      model_override: 'anthropic:claude',
      role: 'copilot_chat',
    })
  })

  it('attaches imported workspace root so the backend runs Copilot in that cwd', () => {
    expect(buildCopilotSendPayload('hello', 'session-1', { role: 'copilot_chat', workspaceRoot: '/abs/imported-skill' })).toEqual({
      user_message: 'hello',
      session_id: 'session-1',
      role: 'copilot_chat',
      workspace_root: '/abs/imported-skill',
    })
  })

  it('attaches structured judge context separately from the user message', () => {
    expect(buildCopilotSendPayload('judge it', 'session-1', { role: 'copilot_judge', judgeContext: {
      compare_result_ref: 'skill-1/golden/golden-1/compare/run-1/compare_result.json',
      judge_context_ref: 'skill-1/runs/run-1/copilot_judge/golden-1/judge_context.json',
      baseline_ref: 'skill-1/golden/golden-1/baseline.json',
      diff_summary: {
        baseline_id: 'golden-1',
        run_results_ref: 'skill-1/runs/run-1/result.json',
        total_score: 80,
        node_group_count: 1,
        failed_node_count: 1,
      },
    } })).toEqual({
      user_message: 'judge it',
      session_id: 'session-1',
      role: 'copilot_judge',
      judge_context: {
        compare_result_ref: 'skill-1/golden/golden-1/compare/run-1/compare_result.json',
        judge_context_ref: 'skill-1/runs/run-1/copilot_judge/golden-1/judge_context.json',
        baseline_ref: 'skill-1/golden/golden-1/baseline.json',
        diff_summary: {
          baseline_id: 'golden-1',
          run_results_ref: 'skill-1/runs/run-1/result.json',
          total_score: 80,
          node_group_count: 1,
          failed_node_count: 1,
        },
      },
    })
  })

  // F4 ②: what the user picked in the composer, and only that. The payload is
  // the whole channel — anything not in it (current selection, open file) is
  // context the backend must never see, which is F4 ③.
  it('carries the mentions the user picked, by ref and not by label', () => {
    expect(buildCopilotSendPayload('explain this', 'session-1', {
      mentions: [{ kind: 'phase', ref: 'event-timeline/review', label: 'review' }],
    })).toEqual({
      user_message: 'explain this',
      session_id: 'session-1',
      mentions: [{ kind: 'phase', ref: 'event-timeline/review', label: 'review' }],
    })
  })

  it('carries an attached image by value', () => {
    expect(buildCopilotSendPayload('look', 'session-1', {
      attachments: [{ kind: 'image', media_type: 'image/png', data: 'aGVsbG8=', name: 'shot.png' }],
    })).toEqual({
      user_message: 'look',
      session_id: 'session-1',
      attachments: [{ kind: 'image', media_type: 'image/png', data: 'aGVsbG8=', name: 'shot.png' }],
    })
  })

  it('omits mention and attachment keys when the composer had none', () => {
    expect(buildCopilotSendPayload('hello', 'session-1', { mentions: [], attachments: [] })).toEqual({
      user_message: 'hello',
      session_id: 'session-1',
    })
  })

  it('omits empty role and override values', () => {
    expect(buildCopilotSendPayload('hello', 'session-1', { modelOverride: '', role: '', workspaceRoot: '   ' })).toEqual({
      user_message: 'hello',
      session_id: 'session-1',
    })
  })
})

describe('visibleCopilotSocketError', () => {
  it('does not surface transient websocket reconnects as a red panel error', () => {
    expect(visibleCopilotSocketError('reconnecting', 'Copilot WebSocket failed')).toBeNull()
    expect(visibleCopilotSocketError('open', 'Copilot WebSocket failed')).toBeNull()
  })

  it('surfaces only stable socket error text', () => {
    expect(visibleCopilotSocketError('error', 'Copilot WebSocket failed')).toBe('Copilot WebSocket failed')
    expect(visibleCopilotSocketError('error', null)).toBeNull()
  })
})
