import { describe, expect, it } from 'vitest'

import { buildCopilotSendPayload, visibleCopilotSocketError } from './useCopilot'

describe('buildCopilotSendPayload', () => {
  it('includes only the user message when no override or role is given', () => {
    expect(buildCopilotSendPayload('hello')).toEqual({ user_message: 'hello' })
  })

  it('attaches the selected role so the composer picker reaches the ws payload', () => {
    expect(buildCopilotSendPayload('hello', null, 'copilot_judge')).toEqual({
      user_message: 'hello',
      role: 'copilot_judge',
    })
  })

  it('keeps model_override behavior intact alongside role', () => {
    expect(buildCopilotSendPayload('hello', 'anthropic:claude', 'copilot_chat')).toEqual({
      user_message: 'hello',
      model_override: 'anthropic:claude',
      role: 'copilot_chat',
    })
  })

  it('attaches imported workspace root so the backend runs Copilot in that cwd', () => {
    expect(buildCopilotSendPayload('hello', null, 'copilot_chat', '/abs/imported-skill')).toEqual({
      user_message: 'hello',
      role: 'copilot_chat',
      workspace_root: '/abs/imported-skill',
    })
  })

  it('attaches structured judge context separately from the user message', () => {
    expect(buildCopilotSendPayload('judge it', null, 'copilot_judge', null, {
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
    })).toEqual({
      user_message: 'judge it',
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

  it('omits empty role and override values', () => {
    expect(buildCopilotSendPayload('hello', '', '', '   ')).toEqual({ user_message: 'hello' })
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
