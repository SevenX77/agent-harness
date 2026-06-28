import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

import { resolveCopilotBashApproval } from '../../api/client'
import type { CopilotBashApprovalRequiredEvent } from '../../types/copilot'
import { BashApprovalCard, resolveBashApprovalDecision } from './bash-approval-card'

vi.mock('../../api/client', () => ({
  resolveCopilotBashApproval: vi.fn(),
}))

function bashEvent(): CopilotBashApprovalRequiredEvent {
  return {
    id: 'evt-bash',
    status: 'pending',
    receivedAt: 0,
    raw: {},
    type: 'bash_approval_required',
    toolUseId: 'tu-bash',
    command: 'printf approved > approved.txt',
    blocked: true,
  }
}

describe('BashApprovalCard', () => {
  it('renders Approve and Reject actions for a held Bash command', () => {
    const html = renderToStaticMarkup(
      <BashApprovalCard event={bashEvent()} skillId="text-segmentation" />,
    )

    expect(html).toContain('Bash held for approval')
    expect(html).toContain('Approve')
    expect(html).toContain('Reject')
    expect(html).toContain('printf approved &gt; approved.txt')
  })

  it('approves a held Bash command through the Copilot approval endpoint', async () => {
    vi.mocked(resolveCopilotBashApproval).mockResolvedValue({
      tool_use_id: 'tu-bash',
      approved: true,
      executed: true,
      success: true,
      stdout: 'approved\n',
      stderr: '',
      returncode: 0,
      message: null,
    })

    const result = await resolveBashApprovalDecision({
      skillId: 'text-segmentation',
      event: bashEvent(),
      approve: true,
    })

    expect(resolveCopilotBashApproval).toHaveBeenCalledWith('text-segmentation', {
      toolUseId: 'tu-bash',
      approve: true,
    })
    expect(result.label).toBe('Command approved and executed.')
  })

  it('treats approval_not_found response as an approval failure', async () => {
    vi.mocked(resolveCopilotBashApproval).mockResolvedValue({
      tool_use_id: 'tu-bash',
      approved: true,
      executed: false,
      success: false,
      stdout: '',
      stderr: '',
      returncode: null,
      message: 'approval_not_found',
    })

    await expect(
      resolveBashApprovalDecision({
        skillId: 'text-segmentation',
        event: bashEvent(),
        approve: true,
      }),
    ).rejects.toThrow('Command approval failed: approval_not_found')
  })

  it('rejects a held Bash command without executing it', async () => {
    vi.mocked(resolveCopilotBashApproval).mockResolvedValue({
      tool_use_id: 'tu-bash',
      approved: false,
      executed: false,
      success: true,
      stdout: '',
      stderr: '',
      returncode: null,
      message: 'rejected',
    })

    const result = await resolveBashApprovalDecision({
      skillId: 'text-segmentation',
      event: bashEvent(),
      approve: false,
    })

    expect(resolveCopilotBashApproval).toHaveBeenCalledWith('text-segmentation', {
      toolUseId: 'tu-bash',
      approve: false,
    })
    expect(result.label).toBe('Command rejected.')
  })
})
