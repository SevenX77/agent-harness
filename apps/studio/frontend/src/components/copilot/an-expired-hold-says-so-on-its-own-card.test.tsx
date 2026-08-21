import { renderToStaticMarkup } from 'react-dom/server'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { copilotStore } from '../../store/copilotStore'
import type {
  CopilotEvent,
  CopilotMessage,
  CopilotToolApprovalRequiredEvent,
} from '../../types/copilot'
import { ToolApprovalCard } from './tool-approval-card'

vi.mock('../../api/client', () => ({
  resolveCopilotToolApproval: vi.fn(),
}))

/**
 * Problem ledger CP7.
 *
 * The backend has always stopped a task whose approval nobody answered: after
 * 30 minutes `can_use_tool` returns `interrupt=True`, deliberately NOT a
 * denial, so the model halts instead of running on with a refusal no human
 * made. None of that reached the screen. The expiry travelled as a generic
 * `error` event, which could say that something had expired but not WHICH
 * hold — so no card could recognise itself in it, and every one of them sat on
 * "Waiting for approval." with live Approve/Reject buttons over a task that
 * had already stopped.
 *
 * The fix is on the event contract, not on the card: the expiry now names its
 * `tool_use_id`, which is the only id the server has ever known the hold by.
 */

function heldEvent(
  overrides: Partial<CopilotToolApprovalRequiredEvent> = {},
): CopilotToolApprovalRequiredEvent {
  return {
    id: 'evt-held',
    status: 'pending',
    receivedAt: 0,
    raw: {},
    type: 'tool_approval_required',
    toolUseId: 'tu-held',
    toolName: 'Bash',
    detail: 'rm -rf /tmp/scratch',
    decision: 'pending',
    ...overrides,
  }
}

describe('a card whose hold expired stops asking to be answered', () => {
  it('says the hold expired and that the task stopped, instead of "Waiting for approval."', () => {
    const html = renderToStaticMarkup(
      <ToolApprovalCard event={heldEvent({ decision: 'timed_out' })} skillId="demo" />,
    )

    expect(html).not.toContain('Waiting for approval.')
    expect(html).toContain('timed out')
    // The task stop is the half a user cannot see anywhere else: the model is
    // not sitting there waiting, it has been halted.
    expect(html).toContain('stopped')
  })

  it('takes the buttons away — there is nothing left to answer', () => {
    const html = renderToStaticMarkup(
      <ToolApprovalCard event={heldEvent({ decision: 'timed_out' })} skillId="demo" />,
    )

    expect(html).not.toContain('>Approve<')
    expect(html).not.toContain('>Reject<')
  })
})

describe('the expiry finds its card by the id the server knows it by', () => {
  beforeEach(() => {
    copilotStore.reset(null)
  })

  async function seed(events: CopilotEvent[]): Promise<void> {
    const sessionId = copilotStore.ensureActiveSession()
    const message: CopilotMessage = {
      id: 'msg-1',
      role: 'assistant',
      content: '',
      events,
      status: 'success',
      createdAt: 0,
    }
    await copilotStore.appendMessage(message, sessionId)
  }

  function eventById(id: string): CopilotEvent | undefined {
    return copilotStore
      .getSnapshot()
      .messages.flatMap((message) => message.events)
      .find((event) => event.id === id)
  }

  it('settles the held approval carrying that tool_use_id', async () => {
    await seed([heldEvent()])

    copilotStore.timeOutToolApproval('tu-held')

    expect(eventById('evt-held')).toMatchObject({
      type: 'tool_approval_required',
      decision: 'timed_out',
    })
  })

  it('leaves a decision the user already made alone', async () => {
    // A verdict and an expiry can cross on the wire. The user's answer is the
    // one that happened; an expiry arriving behind it must not rewrite the
    // record into something nobody chose.
    await seed([heldEvent({ decision: 'approved' })])

    copilotStore.timeOutToolApproval('tu-held')

    expect(eventById('evt-held')).toMatchObject({ decision: 'approved' })
  })

  it('does nothing when no card carries that tool_use_id', async () => {
    await seed([heldEvent()])

    copilotStore.timeOutToolApproval('tu-someone-else')

    expect(eventById('evt-held')).toMatchObject({ decision: 'pending' })
  })
})
