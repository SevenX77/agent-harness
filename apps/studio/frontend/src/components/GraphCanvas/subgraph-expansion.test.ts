import { describe, expect, it } from 'vitest'
import type { GraphTopologyItem } from '@/api/types'
import {
  INPUT_ID,
  OUTPUT_ID,
  SUBGRAPH_PREVIEW_INPUT_TARGET_HANDLE_ID,
} from '@/components/nodes'
import {
  buildSubgraphExpansion,
  isSubgraphPreviewId,
  type PositionedParentNode,
  type SubgraphExpansionRequest,
} from './subgraph-expansion'

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
  it('renders a loaded child as a dashed group plus real child nodes in the parent canvas', () => {
    const { nodes } = buildSubgraphExpansion(PARENT_NODES, [LOADED_REQUEST])

    const group = nodes.find((node) => node.type === 'subgraphGroup')
    expect(group).toBeDefined()
    expect(group?.data).toMatchObject({ parentLabel: 'expand', path: '/abs/child-skill', status: 'loaded' })

    const childInput = nodes.find((node) => node.type === 'globalInput')
    const childOutput = nodes.find((node) => node.type === 'globalOutput')
    expect(childInput?.id).toContain(INPUT_ID)
    expect(childOutput?.id).toContain(OUTPUT_ID)
    expect(childInput?.data.isSubgraphPreview).toBe(true)
    expect(childOutput?.data.isSubgraphPreview).toBe(true)

    const childPhases = nodes.filter((node) => node.type === 'skill')
    expect(childPhases).toHaveLength(2)
    expect(childPhases.map((node) => node.data.label).sort()).toEqual(['plan', 'write'])
    expect(childPhases.every((node) => node.data.isSubgraphPreview === true)).toBe(true)
    expect(nodes.every((node) => isSubgraphPreviewId(node.id))).toBe(true)
    expect(nodes.filter((node) => node.type !== 'subgraphGroup').every((node) => typeof node.width === 'number' && typeof node.height === 'number')).toBe(true)
  })

  it('uses normal contextEdge connectors for the expanded child topology', () => {
    const { edges } = buildSubgraphExpansion(PARENT_NODES, [LOADED_REQUEST])
    const internal = edges.filter((edge) => isSubgraphPreviewId(edge.source) && isSubgraphPreviewId(edge.target))

    expect(internal.length).toBeGreaterThanOrEqual(3)
    expect(internal.every((edge) => edge.type === 'contextEdge')).toBe(true)
    expect(internal.every((edge) => edge.data?.sourcePhaseId === edge.source)).toBe(true)
    expect(internal.every((edge) => edge.data?.targetPhaseId === edge.target)).toBe(true)
    expect(internal.some((edge) => edge.source.includes(INPUT_ID) && edge.target.includes('plan'))).toBe(true)
    expect(internal.some((edge) => edge.source.includes('plan') && edge.target.includes('write'))).toBe(true)
    expect(internal.some((edge) => edge.source.includes('write') && edge.target.includes(OUTPUT_ID))).toBe(true)
  })

  it('bridges from the parent subgraph node to the child input entry point', () => {
    const { edges } = buildSubgraphExpansion(PARENT_NODES, [LOADED_REQUEST])
    const bridges = edges.filter((edge) => edge.source === 'expand' && edge.target.includes(INPUT_ID))

    expect(bridges).toHaveLength(1)
    expect(bridges[0]?.type).toBe('contextEdge')
    expect(bridges[0]?.target).toContain(INPUT_ID)
    expect(bridges[0]?.targetHandle).toBe(SUBGRAPH_PREVIEW_INPUT_TARGET_HANDLE_ID)
    expect(bridges[0]?.data?.sourcePhaseId).toBe('expand')
    expect(bridges[0]?.data?.targetPhaseId).toBe(bridges[0]?.target)
  })

  it('anchors the child input beside the clicked expand node, not the whole graph center', () => {
    const { nodes } = buildSubgraphExpansion(PARENT_NODES, [LOADED_REQUEST])
    const childInput = nodes.find((node) => node.type === 'globalInput')
    const parent = PARENT_NODES.find((node) => node.id === 'expand')

    expect(childInput).toBeDefined()
    expect(childInput?.position.y).toBe(parent?.position.y)
    expect(childInput?.position.x ?? 0).toBeGreaterThan((parent?.position.x ?? 0) + 260 / 2)
  })

  it('renders a loading container bridged from the parent node', () => {
    const { nodes, edges } = buildSubgraphExpansion(PARENT_NODES, [
      { parentNodeId: 'expand', parentLabel: 'expand', path: '/abs/child', view: { status: 'loading' } },
    ])

    expect(nodes.filter((node) => node.type === 'skill')).toHaveLength(0)
    expect(nodes.filter((node) => node.type === 'globalInput' || node.type === 'globalOutput')).toHaveLength(0)
    expect(nodes.find((node) => node.type === 'subgraphGroup')?.data).toMatchObject({ status: 'loading' })
    expect(edges).toHaveLength(1)
    expect(edges[0]?.source).toBe('expand')
    expect(edges[0]?.target).toContain('::group::expand')
    expect(edges[0]?.type).toBe('contextEdge')
  })

  it('renders an error/recovery container bridged from the parent node', () => {
    const { nodes, edges } = buildSubgraphExpansion(PARENT_NODES, [
      {
        parentNodeId: 'expand',
        parentLabel: 'expand',
        path: '',
        view: { status: 'error', message: 'subgraph path unresolved' },
      },
    ])

    expect(nodes.filter((node) => node.type === 'skill')).toHaveLength(0)
    expect(nodes.find((node) => node.type === 'subgraphGroup')?.data).toMatchObject({
      status: 'error',
      message: 'subgraph path unresolved',
    })
    expect(edges).toHaveLength(1)
    expect(edges[0]?.source).toBe('expand')
    expect(edges[0]?.target).toContain('::group::expand')
    expect(edges[0]?.type).toBe('contextEdge')
  })

  it('returns nothing when there are no expansions', () => {
    const { nodes, edges } = buildSubgraphExpansion(PARENT_NODES, [])
    expect(nodes).toHaveLength(0)
    expect(edges).toHaveLength(0)
  })
})
