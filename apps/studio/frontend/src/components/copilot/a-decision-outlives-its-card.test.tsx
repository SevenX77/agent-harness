import { renderToStaticMarkup } from 'react-dom/server'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { copilotStore } from '../../store/copilotStore'
import type {
  CopilotEvent,
  CopilotMessage,
  CopilotPatchProposedEvent,
  CopilotToolApprovalRequiredEvent,
} from '../../types/copilot'
import { ToolApprovalCard } from './tool-approval-card'

vi.mock('../../api/client', () => ({
  resolveCopilotToolApproval: vi.fn(),
}))

/**
 * Problem ledger CP6.
 *
 * A decision the user makes on a card — approve this Bash call, accept this
 * patch — lived in the card's own `useState` and nowhere else. The session is
 * written to disk as JSON, so what got persisted was the card as it first
 * arrived: still pending, buttons still live. Collapse the panel and reopen it,
 * switch session tabs, or Restore chat after a cold start, and every decided
 * card came back undecided. Pressing its buttons then produced a red toast
 * reading `approval_not_found`, because the thing being decided was long gone.
 *
 * A decision is a fact about the message, so the message record owns it. The
 * card renders what the record says and remembers nothing the record cannot.
 */

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
    decision: 'pending',
    ...overrides,
  }
}

function proposedPatch(
  overrides: Partial<CopilotPatchProposedEvent> = {},
): CopilotPatchProposedEvent {
  return {
    id: 'evt-patch',
    status: 'success',
    receivedAt: 0,
    raw: {},
    type: 'patch_proposed',
    toolUseId: 'tu-patch',
    toolName: 'Write',
    path: 'GRAPH.md',
    beforeExisted: true,
    beforeContent: 'old',
    afterContent: 'new',
    beforeHash: null,
    afterHash: 'sha',
    diff: '',
    checkpointId: 'ckpt',
    review: 'pending',
    ...overrides,
  }
}

describe('a card is a function of the record, not of its own memory', () => {
  it('renders a decided approval as decided, from the event alone', () => {
    const html = renderToStaticMarkup(
      <ToolApprovalCard event={heldEvent({ decision: 'approved' })} skillId="demo" />,
    )

    // Not the word 'approved' anywhere — the detail line happens to contain it.
    // The card has to SAY the verdict it is carrying.
    expect(html).toContain('Bash approved.')
  })

  it('offers the buttons only while the record says pending', () => {
    const pending = renderToStaticMarkup(<ToolApprovalCard event={heldEvent()} skillId="demo" />)
    const denied = renderToStaticMarkup(
      <ToolApprovalCard event={heldEvent({ decision: 'denied' })} skillId="demo" />,
    )

    expect(pending).toContain('Approve')
    expect(denied).not.toContain('>Approve<')
  })
})

describe('the store is where a decision lands', () => {
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

  it('remembers an approval decision on the event the user decided', async () => {
    await seed([heldEvent()])

    copilotStore.decideToolApproval('evt-tool', 'approved')

    expect(eventById('evt-tool')).toMatchObject({
      type: 'tool_approval_required',
      decision: 'approved',
    })
  })

  it('remembers a patch review the same way', async () => {
    await seed([proposedPatch()])

    copilotStore.reviewPatch('evt-patch', 'accepted')

    expect(eventById('evt-patch')).toMatchObject({ review: 'accepted' })
  })

  it('leaves every other event alone', async () => {
    await seed([heldEvent(), heldEvent({ id: 'evt-other', toolUseId: 'tu-other' })])

    copilotStore.decideToolApproval('evt-other', 'denied')

    expect(eventById('evt-tool')).toMatchObject({ decision: 'pending' })
    expect(eventById('evt-other')).toMatchObject({ decision: 'denied' })
  })
})
