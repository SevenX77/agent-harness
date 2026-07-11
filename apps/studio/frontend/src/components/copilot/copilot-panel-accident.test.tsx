import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

import type { CopilotEvent, CopilotMessage } from '../../types/copilot'
import { ChatMessageItem } from './copilot-panel'

// ToolApprovalCard imports the approval endpoint at module load; it is only
// called on click, never during a static render, but mock it so the import
// graph has no live network dependency.
vi.mock('../../api/client', () => ({
  resolveCopilotToolApproval: vi.fn(),
}))

const accidentEvents: CopilotEvent[] = [
  { id: 'e1', receivedAt: 1, raw: null, type: 'context_resolved', status: 'success', summary: 'ctx', detail: 'd' },
  { id: 'e2', receivedAt: 2, raw: null, type: 'thinking_delta', status: 'running', content: 'reason' },
  { id: 'e3', receivedAt: 3, raw: null, type: 'text_delta', status: 'running', content: 'Let我先全面了解这个 skill 的结构和内容。' },
  { id: 'e4', receivedAt: 4, raw: null, type: 'tool_use_start', status: 'running', tool_name: 'Read', tool_input: { file_path: 'GRAPH.md' } },
  { id: 'e5', receivedAt: 5, raw: null, type: 'tool_use_result', status: 'success', tool_name: 'Read', success: true, result_summary: 'ok' },
  { id: 'e6', receivedAt: 6, raw: null, type: 'tool_use_start', status: 'running', tool_name: 'Bash', tool_input: { command: 'Get-ChildItem -Recurse' } },
  { id: 'e7', receivedAt: 7, raw: null, type: 'tool_approval_required', status: 'pending', toolUseId: 'call_bash_1', toolName: 'Bash', detail: 'Get-ChildItem -Recurse -Depth 3' },
  { id: 'e8', receivedAt: 8, raw: null, type: 'tool_use_start', status: 'running', tool_name: 'Glob', tool_input: { pattern: '**/*.md' } },
  { id: 'e9', receivedAt: 9, raw: null, type: 'tool_use_start', status: 'running', tool_name: 'Glob', tool_input: { pattern: '**/*.yaml' } },
]

/**
 * The 2026-07-11 accident shape: a model (DeepSeek) that emits its narration
 * text BEFORE calling tools, so the pending Bash approval card and the trailing
 * tool calls all arrive AFTER the last text segment. The old panel sliced
 * everything past the final text away, so the approval card never reached the
 * DOM and the turn hung on an approval the user could not see. This test locks
 * the render layer (not just the transcript builder) so a future re-introduction
 * of that drop fails here.
 */
function accidentMessage(): CopilotMessage {
  return {
    id: 'assistant-accident',
    role: 'assistant',
    content: 'Let我先全面了解这个 skill 的结构和内容。',
    status: 'running',
    createdAt: 1,
    events: accidentEvents,
  }
}

describe('ChatMessageItem — accident replay (render layer)', () => {
  it('renders the pending approval card that arrives after mid-turn text (never drops it)', () => {
    const html = renderToStaticMarkup(
      <ChatMessageItem message={accidentMessage()} skillId="story-deconstruction-v3" />,
    )

    // The critical regression: the pending Bash approval card must reach the DOM
    // even though it arrived after the narration text.
    expect(html).toContain('Bash held for approval')
    expect(html).toContain('Get-ChildItem -Recurse -Depth 3')
    // And the trailing tool activity after the text is not silently swallowed.
    expect(html).toContain('Exploring')
  })
})
