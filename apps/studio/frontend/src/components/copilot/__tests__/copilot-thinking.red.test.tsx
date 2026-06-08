/**
 * WS-5 RED: Copilot event rendering does not drop structure (copilot-assist F1).
 *
 * Contract: Text / Thinking / ToolUse / ToolResult / done / error all render by
 * SDK block type. Thinking is foldable but NEVER summarised away or downgraded
 * to an "Unknown Copilot event" blob.
 *
 * RED today: the frontend has no `thinking_delta` event — `normalizeCopilotEvent`
 * maps it to `unknown` and `ChatMessageItem` renders it as raw "Unknown" JSON.
 */
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { ChatMessageItem } from '../copilot-panel'
import { normalizeCopilotEvent } from '../../../types/copilot'
import type { CopilotMessage } from '../../../types/copilot'

describe('Copilot thinking event rendering', () => {
  it('normalizes a thinking_delta event instead of falling back to unknown', () => {
    const event = normalizeCopilotEvent(
      { type: 'thinking_delta', content: 'reason step one then two' },
      'evt-thinking',
    )

    expect(event.type).toBe('thinking_delta')
    expect((event as { content?: string }).content).toContain('reason step one then two')
  })

  it('renders a thinking event as an expandable thought, not as Unknown', () => {
    const thinkingEvent = {
      id: 'evt-thinking',
      type: 'thinking_delta',
      status: 'running',
      receivedAt: 1,
      raw: {},
      content: 'reason step one then two',
    }
    const message: CopilotMessage = {
      id: 'assistant-1',
      role: 'assistant',
      content: '',
      events: [thinkingEvent as unknown as CopilotMessage['events'][number]],
      status: 'running',
      createdAt: 1,
    }

    const html = renderToStaticMarkup(<ChatMessageItem message={message} />)

    // Reasoning text must survive and be foldable, never replaced by a summary
    // or dropped into an "Unknown Copilot event" blob.
    expect(html).toContain('reason step one then two')
    expect(html).not.toContain('Unknown Copilot event')
    expect(html).toContain('</details>')
  })
})
