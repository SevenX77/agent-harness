import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

import { resolveCopilotToolApproval } from '../../api/client'
import type { CopilotToolApprovalRequiredEvent } from '../../types/copilot'
import { ToolApprovalCard, resolveToolApprovalDecision } from './tool-approval-card'

vi.mock('../../api/client', () => ({
  resolveCopilotToolApproval: vi.fn(),
}))

function heldEvent(
  overrides: Partial<CopilotToolApprovalRequiredEvent> = {},
): CopilotToolApprovalRequiredEvent {
  return {
    id: 'evt-tool',
    status: 'pending',
    receivedAt: 0,
    raw: {},
    type: 'tool_approval_required',
    toolUseId: 'tu-tool',
    toolName: 'Bash',
    detail: 'printf approved > approved.txt',
    ...overrides,
  }
}

describe('ToolApprovalCard', () => {
  it('renders Approve and Reject actions for a held Bash command', () => {
    const html = renderToStaticMarkup(
      <ToolApprovalCard event={heldEvent()} skillId="text-segmentation" />,
    )

    expect(html).toContain('Bash held for approval')
    expect(html).toContain('Approve')
    expect(html).toContain('Reject')
    expect(html).toContain('printf approved &gt; approved.txt')
  })

  it('renders an out-of-fence read hold with the target path', () => {
    const html = renderToStaticMarkup(
      <ToolApprovalCard
        event={heldEvent({ toolName: 'Read', detail: 'D:/somewhere/outside.md' })}
        skillId="text-segmentation"
      />,
    )

    expect(html).toContain('Read outside workspace held for approval')
    expect(html).toContain('D:/somewhere/outside.md')
  })

  it('approves a held tool call through the Copilot approval endpoint', async () => {
    vi.mocked(resolveCopilotToolApproval).mockResolvedValue({
      tool_use_id: 'tu-tool',
      approved: true,
      resolved: true,
      message: null,
    })

    const result = await resolveToolApprovalDecision({
      skillId: 'text-segmentation',
      event: heldEvent(),
      approve: true,
    })

    expect(resolveCopilotToolApproval).toHaveBeenCalledWith('text-segmentation', {
      toolUseId: 'tu-tool',
      approve: true,
    })
    expect(result.label).toBe('Bash approved.')
  })

  it('treats an unresolved (expired) approval as a failure', async () => {
    vi.mocked(resolveCopilotToolApproval).mockResolvedValue({
      tool_use_id: 'tu-tool',
      approved: true,
      resolved: false,
      message: 'approval_not_found',
    })

    await expect(
      resolveToolApprovalDecision({
        skillId: 'text-segmentation',
        event: heldEvent(),
        approve: true,
      }),
    ).rejects.toThrow('Approval expired: approval_not_found')
  })

  it('rejects a held tool call', async () => {
    vi.mocked(resolveCopilotToolApproval).mockResolvedValue({
      tool_use_id: 'tu-tool',
      approved: false,
      resolved: true,
      message: null,
    })

    const result = await resolveToolApprovalDecision({
      skillId: 'text-segmentation',
      event: heldEvent(),
      approve: false,
    })

    expect(resolveCopilotToolApproval).toHaveBeenCalledWith('text-segmentation', {
      toolUseId: 'tu-tool',
      approve: false,
    })
    expect(result.label).toBe('Bash rejected.')
  })
})
