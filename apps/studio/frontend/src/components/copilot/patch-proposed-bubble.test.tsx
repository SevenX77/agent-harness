import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import type { CopilotPatchProposedEvent } from '../../types/copilot'
import { PatchProposedBubble } from './patch-proposed-bubble'

function patchEvent(overrides: Partial<CopilotPatchProposedEvent> = {}): CopilotPatchProposedEvent {
  return {
    id: 'evt-patch',
    status: 'success',
    receivedAt: 0,
    raw: {},
    type: 'patch_proposed',
    toolUseId: 'tu-1',
    toolName: 'Edit',
    path: 'GRAPH.md',
    beforeExisted: true,
    beforeContent: 'alpha\noriginal\nomega',
    afterContent: 'alpha\nEDITED\nomega',
    review: 'pending',
    ...overrides,
  }
}

describe('PatchProposedBubble', () => {
  it('renders the file verb, +/- stats, the line diff, and Accept/Reject', () => {
    const html = renderToStaticMarkup(<PatchProposedBubble event={patchEvent()} skillId="demo" />)
    expect(html).toContain('Edited GRAPH.md')
    expect(html).toContain('+1')
    expect(html).toContain('−1')
    // Diff body shows the removed + added lines.
    expect(html).toContain('original')
    expect(html).toContain('EDITED')
    expect(html).toContain('Accept')
    expect(html).toContain('Reject')
  })

  it('labels a brand-new file as Created', () => {
    const html = renderToStaticMarkup(
      <PatchProposedBubble
        event={patchEvent({ beforeExisted: false, beforeContent: '', afterContent: 'new body', path: 'phases/p/LOGIC.md' })}
        skillId="demo"
      />,
    )
    expect(html).toContain('Created phases/p/LOGIC.md')
    expect(html).toContain('new body')
  })
})
