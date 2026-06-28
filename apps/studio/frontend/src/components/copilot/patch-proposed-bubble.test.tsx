import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

import type { CopilotPatchProposedEvent } from '../../types/copilot'
import { createLocalWorkspaceSelection } from '../studio/workspace-identity'
import {
  PatchProposedBubble,
  PatchProposedBubbleView,
  copilotFileActionEffects,
  resolveCopilotCheckpointRoot,
  seedCopilotRestoreCheckpoint,
} from './patch-proposed-bubble'

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
    beforeHash: 'sha-before',
    afterHash: 'sha-after',
    diff: '@@ -1,3 +1,3 @@\n alpha\n-original\n+EDITED\n omega',
    checkpointId: 'checkpoint-1',
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

  it('renders checkpoint safety errors with Reject disabled', () => {
    const html = renderToStaticMarkup(
      <PatchProposedBubbleView
        event={patchEvent()}
        review="pending"
        busy={false}
        checkpointStatus={{
          state: 'unsafe',
          message: 'Checkpoint unavailable: this change cannot be safely restored.',
        }}
        showCompare={false}
        onAccept={vi.fn()}
        onReject={vi.fn()}
        onShowCompare={vi.fn()}
        onCloseCompare={vi.fn()}
      />,
    )

    expect(html).toContain('Checkpoint unavailable')
    expect(html).toContain('safely restored')
    expect(html).toContain('aria-label="Reject change"')
    expect(html).toContain('disabled=""')
  })
})

describe('seedCopilotRestoreCheckpoint', () => {
  it('does not publish applied when checkpoint seeding fails', async () => {
    const seedWorkspaceCheckpoint = vi.fn().mockRejectedValue(new Error('checkpoint seed failed'))
    const onApplied = vi.fn()

    const result = await seedCopilotRestoreCheckpoint({
      root: '/abs/demo',
      event: patchEvent(),
      seedWorkspaceCheckpoint,
      onApplied,
    })

    expect(seedWorkspaceCheckpoint).toHaveBeenCalledWith(
      '/abs/demo',
      'GRAPH.md',
      'alpha\noriginal\nomega',
      true,
    )
    expect(onApplied).not.toHaveBeenCalled()
    expect(result.state).toBe('unsafe')
    if (result.state !== 'unsafe') {
      throw new Error(`Expected unsafe checkpoint state, got ${result.state}`)
    }
    expect(result.message).toMatch(/checkpoint/i)
    expect(result.message).toMatch(/safely restore/i)
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

describe('resolveCopilotCheckpointRoot', () => {
  it('prefers the imported workspace root over the backend skill id', () => {
    expect(resolveCopilotCheckpointRoot('text-segmentation', '/abs/imported-skill')).toBe('/abs/imported-skill')
  })

  it('falls back to the workspace root encoded in a local workspace identity', () => {
    const identity = createLocalWorkspaceSelection('text-segmentation', '/abs/imported-skill')

    expect(resolveCopilotCheckpointRoot(identity, null)).toBe('/abs/imported-skill')
  })

  it('falls back to the short skill id for default workspace skills', () => {
    expect(resolveCopilotCheckpointRoot('text-segmentation', null)).toBe('text-segmentation')
  })
})
