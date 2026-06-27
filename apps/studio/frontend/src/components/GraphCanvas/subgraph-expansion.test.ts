import { describe, expect, it, vi } from 'vitest'
import type { GraphTopologyItem, SkillDetail } from '@/api/types'
import { CURRENT_SCHEMA_VERSION } from '@/config/schema'
import type { SkillGraphNode } from '@/components/nodes'
import {
  SUBGRAPH_BRIDGE_EDGE_TYPE,
  SUBGRAPH_BRIDGE_SOURCE_HANDLE_ID,
  SUBGRAPH_BRIDGE_TARGET_HANDLE_ID,
} from '@/components/nodes/subgraph-bridge-handles'
import {
  buildSubgraphExpansion,
  isSubgraphPreviewId,
  positionedParentNodes,
  type PositionedParentNode,
  type SubgraphExpansionRequest,
} from './subgraph-expansion'

const PARENT_NODES: PositionedParentNode[] = [
  { id: 'draft', type: 'skill', position: { x: 160, y: 150 } },
  { id: 'review', type: 'skill', position: { x: 160, y: 320 } },
  { id: 'expand', type: 'skill', position: { x: 160, y: 490 } },
]

function topologyRow(id: string, depends_on: string[], mode: string): GraphTopologyItem {
  return { id, src: `phases/${id}`, depends_on, mode }
}

const LOADED_REQUEST: SubgraphExpansionRequest = {
  parentNodeId: 'expand',
  parentLabel: 'expand',
  path: '/abs/child-skill',
  childSkillId: 'child-skill-id',
  view: {
    status: 'loaded',
    name: 'child-skill',
    phases: ['plan', 'write'],
    graphTopology: [
      topologyRow('plan', ['input'], 'agent'),
      { ...topologyRow('write', ['plan'], 'logic'), output: true },
    ],
  },
}

const CHILD_DETAIL: SkillDetail = {
  manifest: {
    schema_version: CURRENT_SCHEMA_VERSION,
    name: 'child-skill',
    description: 'Child skill',
    io: {
      inputs: {
        type: 'object',
        properties: { story: { type: 'string' } },
      },
      outputs: {
        type: 'object',
        properties: { summary: { type: 'string' } },
      },
    },
    phases: ['plan', 'write'],
  },
  graph_topology: [
    topologyRow('plan', ['input'], 'agent'),
    { ...topologyRow('write', ['plan'], 'logic'), output: true },
  ],
  file_paths: {},
  files: {
    'phases/plan/SKILL.md': '---\ntools:\n  - web_search\n---\n<step>Plan the work</step>\n',
    'phases/write/LOGIC.md': '---\npython_callable: write\n---\n',
  },
  has_golden: false,
  latest_run_metadata: null,
  lint_result: null,
}

describe('buildSubgraphExpansion', () => {
  it('renders a loaded child as a dashed group plus real child nodes in the parent canvas', () => {
    const { nodes } = buildSubgraphExpansion(PARENT_NODES, [LOADED_REQUEST])

    const group = nodes.find((node) => node.type === 'subgraphGroup')
    expect(group).toBeDefined()
    expect(group?.data).toMatchObject({ parentLabel: 'expand', path: '/abs/child-skill', status: 'loaded' })
    expect(group?.parentId).toBe('expand')

    const childPhases = nodes.filter((node) => node.type === 'skill')
    expect(childPhases).toHaveLength(2)
    expect(childPhases.map((node) => node.data.label).sort()).toEqual(['plan', 'write'])
    expect(childPhases.every((node) => node.parentId === group?.id)).toBe(true)
    expect(childPhases.every((node) => node.data.skillId === 'child-skill-id')).toBe(true)
    expect(childPhases.every((node) => node.selectable !== false)).toBe(true)
    expect(nodes.filter((node) => node.type !== 'subgraphGroup').every((node) => node.draggable === undefined)).toBe(true)
    expect(nodes.filter((node) => node.type !== 'subgraphGroup').every((node) => node.connectable === undefined)).toBe(true)
    expect(nodes.filter((node) => node.type !== 'subgraphGroup').every((node) => node.deletable === undefined)).toBe(true)
    expect(nodes.every((node) => isSubgraphPreviewId(node.id))).toBe(true)
    expect(nodes.filter((node) => node.type !== 'subgraphGroup').every((node) => typeof node.width === 'number' && typeof node.height === 'number')).toBe(true)
    expect(nodes.filter((node) => node.type !== 'subgraphGroup').map((node) => node.type).sort()).toEqual([
      'globalInput',
      'globalOutput',
      'skill',
      'skill',
    ])
  })

  it('uses the child SkillDetail path so expanded nodes are complete normal nodes', () => {
    const { nodes } = buildSubgraphExpansion(PARENT_NODES, [{
      ...LOADED_REQUEST,
      view: {
        status: 'loaded',
        name: 'child-skill',
        phases: ['plan', 'write'],
        graphTopology: [
          topologyRow('plan', [], 'agent'),
          topologyRow('write', ['plan'], 'logic'),
        ],
        detail: CHILD_DETAIL,
      },
    }])

    const plan = nodes.find((node) => node.type === 'skill' && node.data.label === 'plan')

    expect(plan?.data.tools).toEqual(['web_search'])
    expect(plan?.data.agentBody).toContain('<step>Plan the work</step>')
    expect(plan?.data.phaseId).toBe('plan')
    expect(plan?.id).not.toBe('plan')
    expect(plan?.data.resolvedSkillDetail).toBe(CHILD_DETAIL)
  })

  it('keeps nested subgraph nodes on the same SkillNode toggle contract', () => {
    const onToggleSubgraph = vi.fn()
    const nestedTopology = {
      ...topologyRow('nested', [], 'subgraph'),
      path: '/abs/grandchild-skill',
    }
    const nestedDetail: SkillDetail = {
      ...CHILD_DETAIL,
      manifest: {
        schema_version: CURRENT_SCHEMA_VERSION,
        name: 'child-skill',
        description: 'Child skill',
        io: {
          inputs: {
            type: 'object',
            properties: { story: { type: 'string' } },
          },
          outputs: {
            type: 'object',
            properties: { summary: { type: 'string' } },
          },
        },
        phases: ['nested'],
      },
      graph_topology: [nestedTopology],
      files: {
        'phases/nested/SUBGRAPH.md': '---\nname: nested\npath: /abs/grandchild-skill\n---\n',
      },
    }

    const { nodes } = buildSubgraphExpansion(PARENT_NODES, [{
      ...LOADED_REQUEST,
      view: {
        status: 'loaded',
        name: 'child-skill',
        phases: ['nested'],
        graphTopology: [nestedTopology],
        detail: nestedDetail,
      },
    }], { expandedSubgraphs: new Set(), onToggleSubgraph })
    const nested = nodes.find((node): node is SkillGraphNode => node.type === 'skill' && node.data.label === 'nested')

    expect(nested).toBeDefined()
    expect(nested?.id).toBe('__subpreview__::node::expand::nested')
    expect(nested?.data.phaseId).toBe('nested')
    expect(nested?.data.skillId).toBe('child-skill-id')
    expect(nested?.data.topologyOwnerSkillId).toBeUndefined()
    expect(nested?.data.onToggleSubgraph).toEqual(expect.any(Function))

    nested?.data.onToggleSubgraph?.()
    expect(onToggleSubgraph).toHaveBeenCalledWith('__subpreview__::node::expand::nested')
  })

  it('passes the topology owner through inline child nodes for nested expansion requests', () => {
    const nestedTopology = {
      ...topologyRow('nested', [], 'subgraph'),
      path: '/abs/root/subgraph/child/subgraph/grandchild',
    }

    const { nodes } = buildSubgraphExpansion(PARENT_NODES, [{
      ...LOADED_REQUEST,
      topologyOwnerSkillId: 'root-skill',
      view: {
        status: 'loaded',
        name: 'child-skill',
        phases: ['nested'],
        graphTopology: [nestedTopology],
      },
    }], { expandedSubgraphs: new Set(), onToggleSubgraph: () => undefined })
    const nested = nodes.find((node): node is SkillGraphNode => node.type === 'skill' && node.data.label === 'nested')

    expect(nested?.data.skillId).toBe('child-skill-id')
    expect(nested?.data.workspaceRoot).toBe('/abs/child-skill')
    expect(nested?.data.topologyOwnerSkillId).toBe('root-skill')
  })

  it('prefers the resolved child topology path over stale detail topology for nested subgraphs', () => {
    const resolvedTopology = {
      ...topologyRow('nested', [], 'subgraph'),
      path: '/abs/child-skill/subgraph/grandchild',
    }
    const staleDetail: SkillDetail = {
      ...CHILD_DETAIL,
      manifest: {
        schema_version: CURRENT_SCHEMA_VERSION,
        name: 'child-skill',
        description: 'Child skill',
        io: {
          inputs: { type: 'object', properties: {} },
          outputs: { type: 'object', properties: {} },
        },
        phases: ['nested'],
      },
      graph_topology: [{ ...topologyRow('nested', [], 'subgraph'), path: null }],
      files: {
        'phases/nested/SUBGRAPH.md': '---\nname: nested\ntarget_skill: stale.registry.child\n---\n',
      },
    }

    const { nodes } = buildSubgraphExpansion(PARENT_NODES, [{
      ...LOADED_REQUEST,
      view: {
        status: 'loaded',
        name: 'child-skill',
        phases: ['nested'],
        graphTopology: [resolvedTopology],
        detail: staleDetail,
      },
    }], { expandedSubgraphs: new Set(), onToggleSubgraph: () => undefined })
    const nested = nodes.find((node): node is SkillGraphNode => node.type === 'skill' && node.data.label === 'nested')

    expect(nested?.data.subgraphPath).toBe('/abs/child-skill/subgraph/grandchild')
    expect(nested?.data.workspaceRoot).toBe('/abs/child-skill')
    expect(nested?.data.onToggleSubgraph).toEqual(expect.any(Function))
  })

  it('uses normal contextEdge connectors for the expanded child topology', () => {
    const { edges } = buildSubgraphExpansion(PARENT_NODES, [LOADED_REQUEST])
    const internal = edges.filter((edge) => isSubgraphPreviewId(edge.source) && isSubgraphPreviewId(edge.target))

    expect(internal).toHaveLength(3)
    expect(internal.every((edge) => edge.type === 'contextEdge')).toBe(true)
    expect(internal.every((edge) => edge.data?.showContextControl !== false)).toBe(true)
    expect(internal.every((edge) => edge.data?.sourcePhaseId === edge.source)).toBe(true)
    expect(internal.every((edge) => edge.data?.targetPhaseId === edge.target)).toBe(true)
    expect(internal.some((edge) => edge.source.includes('__global_input__') && edge.target.includes('plan'))).toBe(true)
    expect(internal.some((edge) => edge.source.includes('plan') && edge.target.includes('write'))).toBe(true)
    expect(internal.some((edge) => edge.source.includes('write') && edge.target.includes('__global_output__'))).toBe(true)
  })

  it('emits the parent bridge as a visual-only handle-to-handle edge', () => {
    const { nodes, edges } = buildSubgraphExpansion(PARENT_NODES, [LOADED_REQUEST])
    const group = nodes.find((node) => node.type === 'subgraphGroup')
    const bridge = edges.find((edge) => edge.type === SUBGRAPH_BRIDGE_EDGE_TYPE)

    expect(bridge).toBeDefined()
    expect(bridge).toMatchObject({
      source: 'expand',
      target: group?.id,
      sourceHandle: SUBGRAPH_BRIDGE_SOURCE_HANDLE_ID,
      targetHandle: SUBGRAPH_BRIDGE_TARGET_HANDLE_ID,
      selectable: false,
      focusable: false,
      deletable: false,
      reconnectable: false,
    })
    expect(bridge?.data?.showContextControl).toBe(false)
  })

  it('places the group past the parent graph without encoding that span into the parent node', () => {
    const parents: PositionedParentNode[] = [
      { id: 'expand', type: 'skill', position: { x: 160, y: 490 } },
      { id: 'rightmost-parent', type: 'skill', position: { x: 720, y: 320 } },
    ]
    const { nodes, edges } = buildSubgraphExpansion(parents, [LOADED_REQUEST])
    const group = nodes.find((node) => node.type === 'subgraphGroup')
    const parentRight = 160 + 260 / 2
    const groupLeft = 160 - 260 / 2 + (group?.position.x ?? 0) - ((group?.width as number | undefined) ?? 0) / 2
    const bridge = edges.find((edge) => edge.type === SUBGRAPH_BRIDGE_EDGE_TYPE)

    expect(group?.parentId).toBe('expand')
    expect(groupLeft).toBeGreaterThan(parentRight)
    expect(bridge?.source).toBe('expand')
    expect(bridge?.target).toBe(group?.id)
  })

  it('restores absolute centers for parent-bound subgraph expansion nodes', () => {
    const { nodes } = buildSubgraphExpansion(PARENT_NODES, [LOADED_REQUEST])
    const absoluteNodes = positionedParentNodes([...PARENT_NODES.map((node) => ({
      id: node.id,
      type: 'skill' as const,
      position: node.position,
      width: node.width,
      height: node.height,
      data: {
        skillId: 'demo',
        label: node.id,
        mode: 'logic',
        status: 'idle' as const,
        dependsOn: [],
      },
    })), ...nodes])
    const group = nodes.find((node) => node.type === 'subgraphGroup')
    const absoluteGroup = absoluteNodes.find((node) => node.id === group?.id)

    expect(group?.parentId).toBe('expand')
    expect(absoluteGroup?.position.x).toBe((group?.position.x ?? 0) + 160 - 260 / 2)
  })

  it('anchors the first child phase beside the clicked expand node, not the whole graph center', () => {
    const { nodes } = buildSubgraphExpansion(PARENT_NODES, [LOADED_REQUEST])
    const childPlan = nodes.find((node) => node.type === 'skill' && node.data.label === 'plan')

    expect(childPlan).toBeDefined()
    expect(childPlan?.parentId).toBe('__subpreview__::group::expand')
    expect(childPlan?.position.y ?? 0).toBeGreaterThan(44 + 28)
    expect(childPlan?.position.x ?? 0).toBeGreaterThan(28)
  })

  it('places an expanded subgraph to the right of the whole visible parent topology', () => {
    const parents: PositionedParentNode[] = [
      { id: 'expand', type: 'skill', position: { x: 160, y: 490 } },
      { id: 'rightmost-parent', type: 'skill', position: { x: 720, y: 320 } },
    ]
    const { nodes } = buildSubgraphExpansion(parents, [LOADED_REQUEST])
    const group = nodes.find((node) => node.type === 'subgraphGroup')
    const parentGraphRight = 720 + 260 / 2
    const groupLeft = 160 - 260 / 2 + (group?.position.x ?? 0) - ((group?.width as number | undefined) ?? 0) / 2

    expect(groupLeft).toBeGreaterThan(parentGraphRight)
  })

  it('keeps expanded child phases centered on the same graph axis', () => {
    const { nodes } = buildSubgraphExpansion(PARENT_NODES, [LOADED_REQUEST])
    const childPhases = nodes.filter((node) => node.type === 'skill')

    expect(childPhases).toHaveLength(2)
    const axis = childPhases[0]?.position.x ?? 0
    for (const phase of childPhases) {
      expect(phase.position.x).toBeCloseTo(axis, 5)
    }
  })

  it('renders a loading container beside the parent node', () => {
    const { nodes, edges } = buildSubgraphExpansion(PARENT_NODES, [
      { parentNodeId: 'expand', parentLabel: 'expand', path: '/abs/child', view: { status: 'loading' } },
    ])

    expect(nodes.filter((node) => node.type === 'skill')).toHaveLength(0)
    expect(nodes.filter((node) => node.type !== 'subgraphGroup')).toHaveLength(0)
    expect(nodes.find((node) => node.type === 'subgraphGroup')?.data).toMatchObject({ status: 'loading' })
    expect(edges).toHaveLength(1)
    expect(edges[0]?.type).toBe(SUBGRAPH_BRIDGE_EDGE_TYPE)
  })

  it('renders an error/recovery container beside the parent node', () => {
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
    expect(edges[0]?.type).toBe(SUBGRAPH_BRIDGE_EDGE_TYPE)
  })

  it('returns nothing when there are no expansions', () => {
    const { nodes, edges } = buildSubgraphExpansion(PARENT_NODES, [])
    expect(nodes).toHaveLength(0)
    expect(edges).toHaveLength(0)
  })
})
