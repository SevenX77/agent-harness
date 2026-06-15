import { describe, expect, it } from 'vitest'
import type { SkillDetail } from '@/api/types'
import { CURRENT_SCHEMA_VERSION } from '@/config/schema'
import { INPUT_ID, OUTPUT_ID, type SkillGraphNodeData, type SkillNodeStatus } from '@/components/nodes'
import { buildNodes, phaseKindFile } from './build-nodes'

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
    files: {},
    manifest_errors: null,
    has_golden: false,
    latest_run_metadata: null,
    lint_result: null,
  }
}
