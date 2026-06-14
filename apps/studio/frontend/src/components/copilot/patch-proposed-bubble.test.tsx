import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import type { CopilotPatchProposedEvent } from '../../types/copilot'
import { PatchProposedBubble, copilotFileActionEffects } from './patch-proposed-bubble'

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
    // DEF-026: side-by-side compare affordance is always available.
    expect(html).toContain('Open side-by-side compare')
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

describe('copilotFileActionEffects (F5/DEF-025)', () => {
  it('applied → reload the editor buffer only (edit is live, review not settled)', () => {
    expect(copilotFileActionEffects('applied')).toEqual({ reload: true, recompile: false })
  })

  it('accepted → recompile only (buffer already shows the applied edit)', () => {
    expect(copilotFileActionEffects('accepted')).toEqual({ reload: false, recompile: true })
  })

  it('rejected → reload (file rewound) AND recompile', () => {
    expect(copilotFileActionEffects('rejected')).toEqual({ reload: true, recompile: true })
  })
})
