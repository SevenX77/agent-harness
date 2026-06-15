import { describe, expect, it } from 'vitest'

import { buildCopilotSendPayload } from './useCopilot'

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

  it('omits empty role and override values', () => {
    expect(buildCopilotSendPayload('hello', '', '')).toEqual({ user_message: 'hello' })
  })
})
