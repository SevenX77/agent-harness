/**
 * A breakpoint you set and a run that stopped are two different facts.
 *
 * The breakpoint is a standing choice about the skill: it is true before any run
 * exists and goes on being true after one finishes. The stop is what one run
 * did. The card shows both — a card that showed only the stop would leave the
 * user unable to see, on an idle board, where the next run is going to halt.
 *
 * Design: run-execution/mvp1-alignment.md F10 (「有断点的节点带标记」).
 */

import { renderToStaticMarkup } from 'react-dom/server'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import type { NodeProps } from '@xyflow/react'
import { SkillNode } from './SkillNode'
import type { SkillGraphNode, SkillGraphNodeData } from './types'

// xyflow's Handle needs a ReactFlow provider; stub the primitives so SkillNode
// renders standalone (same approach as SkillNode.golden.test.tsx).
vi.mock('@xyflow/react', () => ({
  Handle: () => <span data-testid="handle" />,
  Position: { Left: 'left', Right: 'right', Top: 'top', Bottom: 'bottom' },
}))

vi.mock('@/components/ui/tooltip', () => ({
  Tooltip: ({ children }: { children: ReactNode }) => <>{children}</>,
  TooltipTrigger: ({ children }: { children: ReactNode }) => <>{children}</>,
  TooltipContent: () => null,
}))

function renderNode(overrides: Partial<SkillGraphNodeData> = {}): string {
  const data: SkillGraphNodeData = {
    phasePath: 'review',
    skillId: 'demo',
    label: 'review',
    mode: 'logic',
    status: 'idle',
    dependsOn: [],
    ...overrides,
  }
  const props = { data, selected: false } as unknown as NodeProps<SkillGraphNode>
  return renderToStaticMarkup(<SkillNode {...props} />)
}

describe('a node carrying a breakpoint', () => {
  it('shows a mark even while nothing is running', () => {
    expect(renderNode({ hasBreakpoint: true })).toContain('data-node-breakpoint="set"')
  })

  it('shows no mark when no breakpoint is set on it', () => {
    expect(renderNode()).not.toContain('data-node-breakpoint')
  })

  it('keeps the mark while the run is stopped on it', () => {
    // Both facts at once: the capsule says what THIS run did, the mark says a
    // breakpoint is why it will stop here again next time.
    const html = renderNode({ hasBreakpoint: true, status: 'breakpoint' })

    expect(html).toContain('data-node-breakpoint="set"')
    expect(html).toContain('Breakpoint')
  })
})
