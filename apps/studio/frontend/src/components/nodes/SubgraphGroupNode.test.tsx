import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import { SubgraphGroupNode, subgraphGroupTitle } from './SubgraphGroupNode'

vi.mock('@xyflow/react', () => ({
  Handle: ({ type, position }: { type: string; position: string }) => (
    <span data-handle-position={position} data-handle-type={type} />
  ),
  Position: { Left: 'left' },
}))

describe('SubgraphGroupNode', () => {
  it('uses the child skill name as the inline preview title instead of the absolute path', () => {
    expect(subgraphGroupTitle({
      parentLabel: 'event_timeline',
      path: '/abs/story-deconstruction-v3/subgraph/event_timeline',
      status: 'loaded',
      childName: 'event_timeline',
    })).toBe('event_timeline')

    const html = renderToStaticMarkup(<SubgraphGroupNode
      {...({
        data: {
          parentLabel: 'event_timeline',
          path: '/abs/story-deconstruction-v3/subgraph/event_timeline',
          status: 'loaded',
          childName: 'event_timeline',
        },
      } as Parameters<typeof SubgraphGroupNode>[0])}
    />)

    expect(html).toContain('event_timeline')
    expect(html).not.toContain('/abs/story-deconstruction-v3/subgraph/event_timeline')
    expect(html).toContain('data-handle-position="left"')
  })

  it('falls back to the path basename while loading before the child name arrives', () => {
    expect(subgraphGroupTitle({
      parentLabel: 'event_timeline',
      path: 'C:\\skills\\story-deconstruction-v3\\subgraph\\event_timeline',
      status: 'loading',
    })).toBe('event_timeline')
  })
})
