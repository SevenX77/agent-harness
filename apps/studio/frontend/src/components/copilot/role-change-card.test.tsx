import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { parseRoleChangeSummary, RoleChangeCard } from './role-change-card'
import { ToolCallBubble } from './tool-call-bubble'
import type { CopilotToolUseResultEvent } from '../../types/copilot'

const UPDATE_SUMMARY = JSON.stringify({
  role_name: 'writer',
  before: {
    role_kind: 'graph_agent',
    model_fallback_enabled: true,
    intent: { thinking: false },
    model_groups: [{ canonical_id: 'old/model', display_name: 'Old', provider_models: [] }],
  },
  after: {
    role_kind: 'graph_agent',
    model_fallback_enabled: false,
    intent: { thinking: true },
    model_groups: [{ canonical_id: 'openai/gpt-5', display_name: 'GPT-5', provider_models: [] }],
  },
})

const CREATE_SUMMARY = JSON.stringify({
  role_name: 'fresh',
  before: null,
  after: {
    role_kind: 'graph_agent',
    model_fallback_enabled: true,
    intent: { thinking: false },
    model_groups: [{ canonical_id: 'openai/gpt-5', display_name: 'GPT-5', provider_models: [] }],
  },
})

function resultEvent(toolName: string, summary: string): CopilotToolUseResultEvent {
  return {
    id: 'evt-role-write',
    status: 'success',
    receivedAt: 0,
    raw: {},
    type: 'tool_use_result',
    tool_name: toolName,
    success: true,
    result_summary: summary,
  }
}

describe('parseRoleChangeSummary (R10.2 change card)', () => {
  it('parses update and create summaries from the role-write tools only', () => {
    const update = parseRoleChangeSummary('mcp__studio__update_llm_role', UPDATE_SUMMARY)
    expect(update?.role_name).toBe('writer')
    expect(update?.before).not.toBeNull()

    const create = parseRoleChangeSummary('mcp__studio__create_llm_role', CREATE_SUMMARY)
    expect(create?.role_name).toBe('fresh')
    expect(create?.before).toBeNull()

    expect(parseRoleChangeSummary('mcp__studio__compile_skill', UPDATE_SUMMARY)).toBeNull()
    expect(parseRoleChangeSummary('mcp__studio__update_llm_role', 'not json')).toBeNull()
  })
})

describe('RoleChangeCard', () => {
  it('shows the role change and a one-click undo button', () => {
    const change = parseRoleChangeSummary('mcp__studio__update_llm_role', UPDATE_SUMMARY)!
    const html = renderToStaticMarkup(<RoleChangeCard change={change} />)

    expect(html).toContain('writer')
    expect(html).toContain('openai/gpt-5')
    expect(html).toContain('old/model')
    expect(html.toLowerCase()).toContain('undo')
  })

  it('renders a create card with undo (delete) affordance', () => {
    const change = parseRoleChangeSummary('mcp__studio__create_llm_role', CREATE_SUMMARY)!
    const html = renderToStaticMarkup(<RoleChangeCard change={change} />)

    expect(html).toContain('fresh')
    expect(html.toLowerCase()).toContain('undo')
  })
})

describe('ToolCallBubble role-write integration', () => {
  it('renders the change card open (visible without a click) on success', () => {
    const html = renderToStaticMarkup(
      <ToolCallBubble event={resultEvent('mcp__studio__update_llm_role', UPDATE_SUMMARY)} />,
    )

    expect(html).toContain('open')
    expect(html).toContain('openai/gpt-5')
    expect(html.toLowerCase()).toContain('undo')
  })

  it('keeps plain summary rendering for other tools', () => {
    const html = renderToStaticMarkup(
      <ToolCallBubble event={resultEvent('mcp__studio__compile_skill', 'compiled ok')} />,
    )

    expect(html).toContain('compiled ok')
    expect(html.toLowerCase()).not.toContain('undo')
  })
})
