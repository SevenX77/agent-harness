import { describe, expect, it } from 'vitest'
import type { GraphTopologyItem } from '@/api/types'
import {
  buildSubgraphExpansion,
  isSubgraphPreviewId,
  type SubgraphExpansionRequest,
  type PositionedParentNode,
} from './subgraph-expansion'

// A small parent graph laid out top-to-bottom (positions are CENTERS, matching
// the canvas nodeOrigin=[0.5,0.5]). `expand` is the subgraph node being expanded.
const PARENT_NODES: PositionedParentNode[] = [
  { id: '__global_input__', type: 'globalInput', position: { x: 0, y: 0 } },
  { id: 'draft', type: 'skill', position: { x: 160, y: 150 } },
  { id: 'review', type: 'skill', position: { x: 160, y: 320 } },
  { id: 'expand', type: 'skill', position: { x: 160, y: 490 } },
  { id: '__global_output__', type: 'globalOutput', position: { x: 0, y: 660 } },
]

function topologyRow(id: string, depends_on: string[], mode: string): GraphTopologyItem {
  return { id, src: `phases/${id}`, depends_on, mode }
}

const LOADED_REQUEST: SubgraphExpansionRequest = {
  parentNodeId: 'expand',
  parentLabel: 'expand',
  path: '/abs/child-skill',
  view: {
    status: 'loaded',
    name: 'child-skill',
    phases: ['plan', 'write'],
    graphTopology: [
      topologyRow('plan', [], 'agent'),
      topologyRow('write', ['plan'], 'logic'),
    ],
  },
}

describe('buildSubgraphExpansion', () => {
  it('renders a loaded child as a dashed group + real child nodes + edges', () => {
    const { nodes } = buildSubgraphExpansion(PARENT_NODES, [LOADED_REQUEST])

    const group = nodes.find((node) => node.type === 'subgraphGroup')
    expect(group).toBeDefined()
    expect(group?.data).toMatchObject({ parentLabel: 'expand', path: '/abs/child-skill', status: 'loaded' })

    const childNodes = nodes.filter((node) => node.type === 'skill')
    expect(childNodes).toHaveLength(2)
    // Real child phases only — never a phase the child graph did not declare.
    const labels = childNodes.map((node) => (node.data as { label: string }).label).sort()
    expect(labels).toEqual(['plan', 'write'])
    // Child nodes carry the preview flag so the canvas click/drill handlers skip them.
    expect(childNodes.every((node) => (node.data as { isSubgraphPreview?: boolean }).isSubgraphPreview === true)).toBe(true)
    // All expansion node ids are namespaced/identifiable as preview elements.
    expect(nodes.every((node) => isSubgraphPreviewId(node.id))).toBe(true)
    // Child nodes MUST carry explicit width/height. They live outside the
    // useNodesState-backed `nodes` state, so React Flow's measurement changes
    // for them are dropped by onNodesChange — without explicit dimensions they
    // stay `visibility: hidden` (rendered but invisible) forever.
    expect(childNodes.every((node) => typeof node.width === 'number' && typeof node.height === 'number')).toBe(true)
  })

  it('anchors the dashed container to the right of the parent graph', () => {
    const { nodes } = buildSubgraphExpansion(PARENT_NODES, [LOADED_REQUEST])
    const group = nodes.find((node) => node.type === 'subgraphGroup')
    const groupWidth = (group?.width ?? (group?.style as { width?: number } | undefined)?.width ?? 0) as number
    const groupLeftEdge = (group?.position.x ?? 0) - groupWidth / 2
    // Parent graph's far-right edge: draft/review/expand are skill nodes (260 wide,
    // center x=160 → right edge=290). Container must sit entirely to their right.
    expect(groupLeftEdge).toBeGreaterThanOrEqual(290)
  })

  it('builds child intra edges from the child depends_on topology', () => {
    const { edges } = buildSubgraphExpansion(PARENT_NODES, [LOADED_REQUEST])
    // plan -> write is the only intra-child dependency edge.
    const intra = edges.filter((edge) => isSubgraphPreviewId(edge.source) && isSubgraphPreviewId(edge.target))
    expect(intra).toHaveLength(1)
    expect(intra[0].source).toContain('plan')
    expect(intra[0].target).toContain('write')
  })

  it('bridges the parent expand node to the child entry and terminal nodes', () => {
    const { edges } = buildSubgraphExpansion(PARENT_NODES, [LOADED_REQUEST])
    // entry bridge: expand -> plan (plan has no deps)
    const entryBridge = edges.find((edge) => edge.source === 'expand' && edge.target.includes('plan'))
    expect(entryBridge).toBeDefined()
    // terminal bridge: write -> expand (write has no dependents)
    const terminalBridge = edges.find((edge) => edge.source.includes('write') && edge.target === 'expand')
    expect(terminalBridge).toBeDefined()
  })

  it('renders a loading container with no child nodes', () => {
    const { nodes, edges } = buildSubgraphExpansion(PARENT_NODES, [
      { parentNodeId: 'expand', parentLabel: 'expand', path: '/abs/child', view: { status: 'loading' } },
    ])
    expect(nodes.filter((node) => node.type === 'skill')).toHaveLength(0)
    const group = nodes.find((node) => node.type === 'subgraphGroup')
    expect(group?.data).toMatchObject({ status: 'loading' })
    expect(edges).toHaveLength(0)
  })

  it('renders an error container carrying the message, with no child nodes', () => {
    const { nodes, edges } = buildSubgraphExpansion(PARENT_NODES, [
      {
        parentNodeId: 'expand',
        parentLabel: 'expand',
        path: '/abs/missing',
        view: { status: 'error', message: 'subgraph not found at /abs/missing' },
      },
    ])
    expect(nodes.filter((node) => node.type === 'skill')).toHaveLength(0)
    const group = nodes.find((node) => node.type === 'subgraphGroup')
    expect(group?.data).toMatchObject({ status: 'error', message: 'subgraph not found at /abs/missing' })
    expect(edges).toHaveLength(0)
  })

  it('returns nothing when there are no expansions', () => {
    const { nodes, edges } = buildSubgraphExpansion(PARENT_NODES, [])
    expect(nodes).toHaveLength(0)
    expect(edges).toHaveLength(0)
  })
})
