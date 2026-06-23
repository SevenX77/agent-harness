import { describe, expect, it } from 'vitest'
import type { GraphTopologyItem } from '@/api/types'
import { INPUT_ID, OUTPUT_ID } from '@/components/nodes'
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

// The expansion renders the child with the SAME recursive pipeline the main
// canvas uses (buildNodesFromTopology + buildEdges + auto-layout), so a loaded
// child is a self-contained graph: its OWN global input/output nodes, real phase
// nodes, and contextEdge connectors (the dotted-midpoint edge). Helpers below find
// the namespaced preview ids that wrap each child element.
const previewInput = `__subpreview__::expand::${INPUT_ID}`
const previewOutput = `__subpreview__::expand::${OUTPUT_ID}`

describe('buildSubgraphExpansion', () => {
  it('renders a loaded child as a dashed group + its own in/out nodes + real phases', () => {
    const { nodes } = buildSubgraphExpansion(PARENT_NODES, [LOADED_REQUEST])

    const group = nodes.find((node) => node.type === 'subgraphGroup')
    expect(group).toBeDefined()
    expect(group?.data).toMatchObject({ parentLabel: 'expand', path: '/abs/child-skill', status: 'loaded' })

    // Point 2: the child has its OWN global input + output nodes (recursive, same
    // as the parent canvas) — not just bare phases bridged to the parent.
    expect(nodes.some((node) => node.type === 'globalInput' && node.id === previewInput)).toBe(true)
    expect(nodes.some((node) => node.type === 'globalOutput' && node.id === previewOutput)).toBe(true)

    const childPhases = nodes.filter((node) => node.type === 'skill')
    expect(childPhases).toHaveLength(2)
    const labels = childPhases.map((node) => (node.data as { label: string }).label).sort()
    expect(labels).toEqual(['plan', 'write'])
    // Child phase nodes carry the preview flag so the canvas click/drill handlers skip them.
    expect(childPhases.every((node) => (node.data as { isSubgraphPreview?: boolean }).isSubgraphPreview === true)).toBe(true)
    // EVERY emitted node (in/out + phases + group) is namespaced as a preview element.
    expect(nodes.every((node) => isSubgraphPreviewId(node.id))).toBe(true)
    // All preview nodes MUST carry explicit width/height. They live outside the
    // useNodesState-backed `nodes` state, so React Flow's measurement changes for
    // them are dropped by onNodesChange — without explicit dimensions they stay
    // `visibility: hidden` (rendered but invisible) forever.
    expect(nodes.filter((n) => n.type !== 'subgraphGroup').every((node) => typeof node.width === 'number' && typeof node.height === 'number')).toBe(true)
  })

  it('connects the child with contextEdge connectors (dotted-midpoint, same as the parent canvas)', () => {
    const { edges } = buildSubgraphExpansion(PARENT_NODES, [LOADED_REQUEST])
    // Internal child edges run input -> plan -> write -> output, all contextEdge so
    // the clickable midpoint dot renders exactly like the main graph (point 2).
    const internal = edges.filter((edge) => isSubgraphPreviewId(edge.source) && isSubgraphPreviewId(edge.target))
    expect(internal.length).toBeGreaterThanOrEqual(3)
    expect(internal.every((edge) => edge.type === 'contextEdge')).toBe(true)
    // input -> plan, plan -> write, write -> output
    expect(internal.some((e) => e.source === previewInput && e.target.includes('plan'))).toBe(true)
    expect(internal.some((e) => e.source.includes('plan') && e.target.includes('write'))).toBe(true)
    expect(internal.some((e) => e.source.includes('write') && e.target === previewOutput)).toBe(true)
  })

  it('bridges the parent subgraph node to the child IN/OUT nodes', () => {
    const { edges } = buildSubgraphExpansion(PARENT_NODES, [LOADED_REQUEST])
    // parent expand node -> child input ; child output -> parent expand node.
    expect(edges.some((e) => e.source === 'expand' && e.target === previewInput)).toBe(true)
    expect(edges.some((e) => e.source === previewOutput && e.target === 'expand')).toBe(true)
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

  it('renders a loading container with no child nodes', () => {
    const { nodes, edges } = buildSubgraphExpansion(PARENT_NODES, [
      { parentNodeId: 'expand', parentLabel: 'expand', path: '/abs/child', view: { status: 'loading' } },
    ])
    expect(nodes.filter((node) => node.type === 'skill')).toHaveLength(0)
    expect(nodes.filter((node) => node.type === 'globalInput' || node.type === 'globalOutput')).toHaveLength(0)
    const group = nodes.find((node) => node.type === 'subgraphGroup')
    expect(group?.data).toMatchObject({ status: 'loading' })
    expect(edges).toHaveLength(0)
  })

  it('renders an error/recovery container carrying the message, with no child nodes', () => {
    const { nodes, edges } = buildSubgraphExpansion(PARENT_NODES, [
      {
        parentNodeId: 'expand',
        parentLabel: 'expand',
        path: '',
        view: { status: 'error', message: 'subgraph path unresolved' },
      },
    ])
    expect(nodes.filter((node) => node.type === 'skill')).toHaveLength(0)
    const group = nodes.find((node) => node.type === 'subgraphGroup')
    expect(group?.data).toMatchObject({ status: 'error', message: 'subgraph path unresolved' })
    expect(edges).toHaveLength(0)
  })

  it('returns nothing when there are no expansions', () => {
    const { nodes, edges } = buildSubgraphExpansion(PARENT_NODES, [])
    expect(nodes).toHaveLength(0)
    expect(edges).toHaveLength(0)
  })
})
