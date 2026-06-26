import { describe, expect, it, vi } from 'vitest'
import type { GraphTopologyItem, SkillDetail } from '@/api/types'
import { CURRENT_SCHEMA_VERSION } from '@/config/schema'
import {
  INPUT_ID,
  OUTPUT_ID,
  type SkillGraphNode,
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
  childSkillId: 'child-skill-id',
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
    topologyRow('plan', [], 'agent'),
    topologyRow('write', ['plan'], 'logic'),
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

    const childInput = nodes.find((node) => node.type === 'globalInput')
    const childOutput = nodes.find((node) => node.type === 'globalOutput')
    expect(childInput?.id).toContain(INPUT_ID)
    expect(childOutput?.id).toContain(OUTPUT_ID)
    expect(childInput?.data.skillId).toBe('child-skill-id')
    expect(childOutput?.data.skillId).toBe('child-skill-id')

    const childPhases = nodes.filter((node) => node.type === 'skill')
    expect(childPhases).toHaveLength(2)
    expect(childPhases.map((node) => node.data.label).sort()).toEqual(['plan', 'write'])
    expect(childPhases.every((node) => node.data.skillId === 'child-skill-id')).toBe(true)
    expect(childPhases.every((node) => node.selectable !== false)).toBe(true)
    expect(nodes.filter((node) => node.type !== 'subgraphGroup').every((node) => node.draggable === undefined)).toBe(true)
    expect(nodes.filter((node) => node.type !== 'subgraphGroup').every((node) => node.connectable === undefined)).toBe(true)
    expect(nodes.filter((node) => node.type !== 'subgraphGroup').every((node) => node.deletable === undefined)).toBe(true)
    expect(nodes.every((node) => isSubgraphPreviewId(node.id))).toBe(true)
    expect(nodes.filter((node) => node.type !== 'subgraphGroup').every((node) => typeof node.width === 'number' && typeof node.height === 'number')).toBe(true)
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

    const childInput = nodes.find((node) => node.type === 'globalInput')
    const childOutput = nodes.find((node) => node.type === 'globalOutput')
    const plan = nodes.find((node) => node.type === 'skill' && node.data.label === 'plan')

    expect(childInput?.data.schema.inputs).toEqual([{ name: 'story', type: 'string', source: 'runtime', default: null }])
    expect(childOutput?.data.schema.outputs).toEqual([{ name: 'summary', type: 'string', target: 'file', path: null }])
    expect(plan?.data.tools).toEqual(['web_search'])
    expect(plan?.data.agentBody).toContain('<step>Plan the work</step>')
    expect(plan?.data.phaseId).toBe('plan')
    expect(plan?.id).not.toBe('plan')
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

    expect(internal.length).toBeGreaterThanOrEqual(3)
    expect(internal.every((edge) => edge.type === 'contextEdge')).toBe(true)
    expect(internal.every((edge) => edge.data?.showContextControl !== false)).toBe(true)
    expect(internal.every((edge) => edge.data?.sourcePhaseId === edge.source)).toBe(true)
    expect(internal.every((edge) => edge.data?.targetPhaseId === edge.target)).toBe(true)
    expect(internal.some((edge) => edge.source.includes(INPUT_ID) && edge.target.includes('plan'))).toBe(true)
    expect(internal.some((edge) => edge.source.includes('plan') && edge.target.includes('write'))).toBe(true)
    expect(internal.some((edge) => edge.source.includes('write') && edge.target.includes(OUTPUT_ID))).toBe(true)
  })

  it('keeps the parent bridge visual out of React Flow edges and leaves a fixed toggle-to-frame span', () => {
    const { nodes, edges } = buildSubgraphExpansion(PARENT_NODES, [LOADED_REQUEST])
    const group = nodes.find((node) => node.type === 'subgraphGroup')
    const groupLeft = (group?.position.x ?? 0) - ((group?.width as number | undefined) ?? 0) / 2

    expect(edges.some((edge) => edge.source === 'expand')).toBe(false)
    expect(groupLeft).toBe(392)
  })

  it('anchors the child input beside the clicked expand node, not the whole graph center', () => {
    const { nodes } = buildSubgraphExpansion(PARENT_NODES, [LOADED_REQUEST])
    const childInput = nodes.find((node) => node.type === 'globalInput')
    const parent = PARENT_NODES.find((node) => node.id === 'expand')

    expect(childInput).toBeDefined()
    expect(childInput?.position.y).toBe(parent?.position.y)
    expect(childInput?.position.x ?? 0).toBeGreaterThan((parent?.position.x ?? 0) + 260 / 2)
  })

  it('keeps expanded child input, phases, and output centered on the same graph axis', () => {
    const { nodes } = buildSubgraphExpansion(PARENT_NODES, [LOADED_REQUEST])
    const childInput = nodes.find((node) => node.type === 'globalInput')
    const childOutput = nodes.find((node) => node.type === 'globalOutput')
    const childPhases = nodes.filter((node) => node.type === 'skill')

    expect(childInput).toBeDefined()
    expect(childOutput).toBeDefined()
    expect(childPhases).toHaveLength(2)
    for (const phase of childPhases) {
      expect(phase.position.x).toBeCloseTo(childInput?.position.x ?? 0, 5)
      expect(phase.position.x).toBeCloseTo(childOutput?.position.x ?? 0, 5)
    }
  })

  it('renders a loading container beside the parent node', () => {
    const { nodes, edges } = buildSubgraphExpansion(PARENT_NODES, [
      { parentNodeId: 'expand', parentLabel: 'expand', path: '/abs/child', view: { status: 'loading' } },
    ])

    expect(nodes.filter((node) => node.type === 'skill')).toHaveLength(0)
    expect(nodes.filter((node) => node.type === 'globalInput' || node.type === 'globalOutput')).toHaveLength(0)
    expect(nodes.find((node) => node.type === 'subgraphGroup')?.data).toMatchObject({ status: 'loading' })
    expect(edges).toHaveLength(0)
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
    expect(edges).toHaveLength(0)
  })

  it('returns nothing when there are no expansions', () => {
    const { nodes, edges } = buildSubgraphExpansion(PARENT_NODES, [])
    expect(nodes).toHaveLength(0)
    expect(edges).toHaveLength(0)
  })
})
