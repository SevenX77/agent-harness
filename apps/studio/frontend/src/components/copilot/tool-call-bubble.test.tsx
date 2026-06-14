import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import type { CopilotToolUseResultEvent, CopilotToolUseStartEvent } from '../../types/copilot'
import { ToolCallBubble } from './tool-call-bubble'

function startEvent(toolName: CopilotToolUseStartEvent['tool_name']): CopilotToolUseStartEvent {
  return {
    id: 'evt-start',
    status: 'running',
    receivedAt: 0,
    raw: {},
    type: 'tool_use_start',
    tool_name: toolName,
    tool_input: { file_path: 'GRAPH.md' },
  }
}

function resultEvent(
  toolName: string,
  success: boolean,
): CopilotToolUseResultEvent {
  return {
    id: 'evt-result',
    status: success ? 'success' : 'error',
    receivedAt: 0,
    raw: {},
    type: 'tool_use_result',
    tool_name: toolName,
    success,
    result_summary: 'summary line',
  }
}

describe('ToolCallBubble (F1 folded tool calls)', () => {
  it('folds each tool call into a collapsible details/summary, not omitted', () => {
    const html = renderToStaticMarkup(<ToolCallBubble event={resultEvent('Read', true)} />)

    expect(html).toContain('<details')
    expect(html).toContain('<summary')
    // The full output is present inside the fold (collapsed, never dropped).
    expect(html).toContain('summary line')
  })

  it('labels tool classes with semantic verbs', () => {
    expect(renderToStaticMarkup(<ToolCallBubble event={resultEvent('Read', true)} />)).toContain('Explored')
    expect(renderToStaticMarkup(<ToolCallBubble event={resultEvent('Write', true)} />)).toContain('Worked')
    expect(renderToStaticMarkup(<ToolCallBubble event={resultEvent('Edit', true)} />)).toContain('Worked')
    expect(renderToStaticMarkup(<ToolCallBubble event={resultEvent('Bash', true)} />)).toContain('Ran')
  })

  it('uses present-tense verbs while a tool is still running', () => {
    expect(renderToStaticMarkup(<ToolCallBubble event={startEvent('Read')} />)).toContain('Exploring')
    expect(renderToStaticMarkup(<ToolCallBubble event={startEvent('Bash')} />)).toContain('Running')
  })

  it('keeps a failed tool call expanded so the error is visible', () => {
    const html = renderToStaticMarkup(<ToolCallBubble event={resultEvent('Bash', false)} />)

    expect(html).toContain('Bash failed')
    // react-dom renders a defaulted-open <details> with the `open` attribute.
    expect(html).toMatch(/<details[^>]*\sopen/)
  })
})
