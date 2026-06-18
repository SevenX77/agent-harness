import { describe, expect, it } from 'vitest'
import type { GraphTopologyItem, SkillDetail } from '@/api/types'
import { CURRENT_SCHEMA_VERSION } from '@/config/schema'
import { INPUT_ID, OUTPUT_ID, type SkillGraphNodeData, type SkillNodeStatus } from '@/components/nodes'
import { buildNodes, buildNodesFromTopology, phaseKindFile } from './build-nodes'

describe('phaseKindFile', () => {
  it('maps an agent phase (mode "agent") to SKILL.md, not LOGIC.md', () => {
    expect(phaseKindFile({ mode: 'agent', subgraphPath: null })).toBe('SKILL.md')
  })

  it('maps legacy skill/llm modes to SKILL.md', () => {
    expect(phaseKindFile({ mode: 'skill', subgraphPath: null })).toBe('SKILL.md')
    expect(phaseKindFile({ mode: 'llm', subgraphPath: null })).toBe('SKILL.md')
  })

  it('maps subgraph and logic phases to their own kinds', () => {
    expect(phaseKindFile({ mode: 'subgraph', subgraphPath: null })).toBe('SUBGRAPH.md')
    expect(phaseKindFile({ mode: 'logic', subgraphPath: null })).toBe('LOGIC.md')
  })
})

describe('buildNodes', () => {
  it('classifies an agent (SKILL.md) phase as agent kind, not logic', () => {
    const nodes = buildNodes('demo', skillDetail({
      phases: ['draft', 'review'],
      graph_topology: [
        { id: 'draft', src: 'phases/draft/SKILL.md', depends_on: [], mode: 'agent' },
        { id: 'review', src: 'phases/review/LOGIC.md', depends_on: ['draft'], mode: 'logic' },
      ],
    }), new Set(), () => {}, {})

    const draft = phaseNode(nodes, 'draft')
    expect(draft.mode).toBe('agent')
    expect(draft.filePath).toBe('phases/draft/SKILL.md')

    const review = phaseNode(nodes, 'review')
    expect(review.mode).toBe('logic')
    expect(review.filePath).toBe('phases/review/LOGIC.md')
  })

  it('defaults every node to idle (no fabricated success) before any run', () => {
    const nodes = buildNodes('demo', skillDetail({
      phases: ['first', 'second'],
      graph_topology: [
        { id: 'first', src: 'phases/first/SKILL.md', depends_on: [], mode: 'agent' },
        { id: 'second', src: 'phases/second/LOGIC.md', depends_on: ['first'], mode: 'logic' },
      ],
    }), new Set(), () => {}, {})

    const statuses = nodes
      .filter((node) => node.type === 'skill')
      .map((node) => (node.data as SkillGraphNodeData).status)

    expect(statuses).toEqual(['idle', 'idle'])
    expect(statuses).not.toContain('success')
  })

  it('honors a real run status when present', () => {
    const statusByNodeId: Record<string, SkillNodeStatus> = { first: 'success' }
    const nodes = buildNodes('demo', skillDetail({
      phases: ['first', 'second'],
      graph_topology: [
        { id: 'first', src: 'phases/first/LOGIC.md', depends_on: [], mode: 'logic' },
        { id: 'second', src: 'phases/second/LOGIC.md', depends_on: ['first'], mode: 'logic' },
      ],
    }), new Set(), () => {}, statusByNodeId)

    expect(phaseNode(nodes, 'first').status).toBe('success')
    expect(phaseNode(nodes, 'second').status).toBe('idle')
  })

  it('always brackets phase nodes with global input/output nodes', () => {
    const nodes = buildNodes('demo', skillDetail({
      phases: ['only'],
      graph_topology: [{ id: 'only', src: 'phases/only/LOGIC.md', depends_on: [], mode: 'logic' }],
    }), new Set(), () => {}, {})

    expect(nodes[0].id).toBe(INPUT_ID)
    expect(nodes[nodes.length - 1].id).toBe(OUTPUT_ID)
  })

  it('does not treat legacy SUBGRAPH target_skill as a drillable child path', () => {
    const nodes = buildNodes('demo', skillDetail({
      phases: ['legacy'],
      graph_topology: [
        { id: 'legacy', src: 'phases/legacy/SUBGRAPH.md', depends_on: [], mode: 'subgraph', path: null },
      ],
      files: {
        'phases/legacy/SUBGRAPH.md': [
          '---',
          'target_skill: old.registry.child',
          '---',
          '',
        ].join('\n'),
      },
    }), new Set(), () => {}, {})

    const legacy = phaseNode(nodes, 'legacy')
    expect(legacy.subgraphPath).toBeNull()
    expect(legacy.onToggleSubgraph).toBeUndefined()
  })

  it('only exposes absolute subgraph paths for drill-down and trims surrounding whitespace', () => {
    const nodes = buildNodes('demo', skillDetail({
      phases: ['trimmed', 'relative'],
      graph_topology: [
        { id: 'trimmed', src: 'phases/trimmed/SUBGRAPH.md', depends_on: [], mode: 'subgraph', path: '  /abs/child  ' },
        { id: 'relative', src: 'phases/relative/SUBGRAPH.md', depends_on: [], mode: 'subgraph', path: 'legacy.registry.child' },
      ],
    }), new Set(), () => {}, {})

    expect(phaseNode(nodes, 'trimmed').subgraphPath).toBe('/abs/child')
    expect(phaseNode(nodes, 'trimmed').onToggleSubgraph).toBeTypeOf('function')
    expect(phaseNode(nodes, 'relative').subgraphPath).toBeNull()
    expect(phaseNode(nodes, 'relative').onToggleSubgraph).toBeUndefined()
  })
})

describe('buildNodesFromTopology (drilled child graph)', () => {
  const topology: GraphTopologyItem[] = [
    { id: 'plan', src: 'phases/plan/SKILL.md', depends_on: [], mode: 'agent' },
    { id: 'nested', src: 'phases/nested/SUBGRAPH.md', depends_on: ['plan'], mode: 'subgraph', path: '/skills/grandchild' },
  ]

  it('brackets drilled phases with global input/output and preserves order + deps', () => {
    const nodes = buildNodesFromTopology('demo', ['plan', 'nested'], topology, {})
    expect(nodes[0].id).toBe(INPUT_ID)
    expect(nodes[nodes.length - 1].id).toBe(OUTPUT_ID)

    const plan = phaseNode(nodes, 'plan')
    expect(plan.mode).toBe('agent')
    expect(plan.dependsOn).toEqual([])

    const nested = phaseNode(nodes, 'nested')
    expect(nested.dependsOn).toEqual(['plan'])
  })

  it('exposes a nested subgraph child path so deeper drilling is possible', () => {
    const nodes = buildNodesFromTopology('demo', ['plan', 'nested'], topology, {})
    expect(phaseNode(nodes, 'nested').subgraphPath).toBe('/skills/grandchild')
    expect(phaseNode(nodes, 'plan').subgraphPath).toBeNull()
  })

  it('defaults drilled phases to idle and carries through a real status', () => {
    const nodes = buildNodesFromTopology('demo', ['plan', 'nested'], topology, { plan: 'success' })
    expect(phaseNode(nodes, 'plan').status).toBe('success')
    expect(phaseNode(nodes, 'nested').status).toBe('idle')
  })
})

function phaseNode(nodes: ReturnType<typeof buildNodes>, id: string): SkillGraphNodeData {
  const node = nodes.find((candidate) => candidate.id === id)
  if (!node || node.type !== 'skill') {
    throw new Error(`phase node ${id} not found`)
  }
  return node.data as SkillGraphNodeData
}

function skillDetail(overrides: {
  phases?: string[]
  graph_topology?: SkillDetail['graph_topology']
  files?: SkillDetail['files']
} = {}): SkillDetail {
  const phases = overrides.phases ?? []

  return {
    manifest: {
      schema_version: CURRENT_SCHEMA_VERSION,
      name: 'demo',
      description: 'Demo',
      io: {
        inputs: { type: 'object', properties: {} },
        outputs: { type: 'object', properties: {} },
      },
      phases,
    },
    graph_topology: overrides.graph_topology,
    node_schema_v21: {},
    io_schema: {},
    file_paths: {},
      files: overrides.files ?? {},
    manifest_errors: null,
    has_golden: false,
    latest_run_metadata: null,
    lint_result: null,
  }
}
