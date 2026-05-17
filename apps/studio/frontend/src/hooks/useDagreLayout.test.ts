import { describe, expect, it } from 'vitest'
import type { Edge, Node } from 'reactflow'
import { getLayoutedElements } from './useDagreLayout'

describe('getLayoutedElements', () => {
  it('places connected phase nodes on increasing vertical ranks', () => {
    const nodes: Node[] = [
      { id: 'final', position: { x: 0, y: 0 }, data: {} },
      { id: 'setup', position: { x: 0, y: 0 }, data: {} },
      { id: 'branch', position: { x: 0, y: 0 }, data: {} },
    ]
    const edges: Edge[] = [
      { id: 'e-branch-final', source: 'branch', target: 'final' },
      { id: 'e-setup-branch', source: 'setup', target: 'branch' },
    ]

    const layouted = getLayoutedElements(nodes, edges)
    const byId = new Map(layouted.nodes.map((node) => [node.id, node]))

    expect(byId.get('setup')?.position.y).toBeLessThan(byId.get('branch')?.position.y ?? 0)
    expect(byId.get('branch')?.position.y).toBeLessThan(byId.get('final')?.position.y ?? 0)
    expect(layouted.edges).toBe(edges)
  })

  it('returns an empty graph without invoking layout work', () => {
    const edges: Edge[] = []

    expect(getLayoutedElements([], edges)).toEqual({ nodes: [], edges })
  })
})
