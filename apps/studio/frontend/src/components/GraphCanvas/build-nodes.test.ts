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

  it('populates an agent node tools from its SKILL.md frontmatter (mode is "agent", never "skill")', () => {
    const nodes = buildNodes('demo', skillDetail({
      phases: ['draft', 'review'],
      graph_topology: [
        { id: 'draft', src: 'phases/draft/SKILL.md', depends_on: [], mode: 'agent' },
        { id: 'review', src: 'phases/review/LOGIC.md', depends_on: ['draft'], mode: 'logic' },
      ],
      files: {
        'phases/draft/SKILL.md': ['---', 'name: draft', 'llm_role: writer', 'tools: [read_file, run_tests]', '---', 'Body'].join('\n'),
      },
    }), new Set(), () => {}, {})

    // The engine projects an agent phase's mode as 'agent', so tools must be read
    // from the SKILL.md frontmatter — the old `mode === 'skill'` guard left this
    // empty for every agent node.
    const draft = phaseNode(nodes, 'draft')
    expect(draft.mode).toBe('agent')
    expect(draft.tools).toEqual(['read_file', 'run_tests'])

    // A non-agent (logic) node exposes no tools.
    expect(phaseNode(nodes, 'review').tools).toEqual([])
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

  it('carries a per-node golden state through to node data, leaving others undefined', () => {
    const nodes = buildNodes('demo', skillDetail({
      phases: ['draft', 'review'],
      graph_topology: [
        { id: 'draft', src: 'phases/draft/SKILL.md', depends_on: [], mode: 'agent' },
        { id: 'review', src: 'phases/review/LOGIC.md', depends_on: ['draft'], mode: 'logic' },
      ],
    }), new Set(), () => {}, {}, {}, { draft: 'has-golden' })

    expect(phaseNode(nodes, 'draft').goldenState).toBe('has-golden')
    expect(phaseNode(nodes, 'review').goldenState).toBeUndefined()
  })

  it('threads a per-node error message into node data so the failed-node red light has a source', () => {
    const nodes = buildNodes('demo', skillDetail({
      phases: ['draft', 'review'],
      graph_topology: [
        { id: 'draft', src: 'phases/draft/SKILL.md', depends_on: [], mode: 'agent' },
        { id: 'review', src: 'phases/review/LOGIC.md', depends_on: ['draft'], mode: 'logic' },
      ],
    }), new Set(), () => {}, {}, {}, {}, { draft: 'validator: missing field x' })

    expect(phaseNode(nodes, 'draft').errorMessage).toBe('validator: missing field x')
    expect(phaseNode(nodes, 'review').errorMessage).toBeUndefined()
  })

  it('always brackets phase nodes with global input/output nodes', () => {
    const nodes = buildNodes('demo', skillDetail({
      phases: ['only'],
      graph_topology: [{ id: 'only', src: 'phases/only/LOGIC.md', depends_on: [], mode: 'logic' }],
    }), new Set(), () => {}, {})

    expect(nodes[0].id).toBe(INPUT_ID)
    expect(nodes[nodes.length - 1].id).toBe(OUTPUT_ID)
  })

  it('derives node kind from the phase FILE when topology.mode is absent (file is truth source)', () => {
    const nodes = buildNodes('demo', skillDetail({
      phases: ['draft'],
      // No graph_topology row → topology.mode is undefined for this phase.
      graph_topology: [],
      files: {
        'phases/draft/SKILL.md': ['---', 'name: draft', 'llm_role: writer', '---', 'Body'].join('\n'),
      },
    }), new Set(), () => {}, {})

    const draft = phaseNode(nodes, 'draft')
    expect(draft.mode).toBe('agent')
    expect(draft.filePath).toBe('phases/draft/SKILL.md')
  })

  it('lets the phase FILE override a stale topology.mode rather than trusting the mutable mode', () => {
    const nodes = buildNodes('demo', skillDetail({
      phases: ['draft'],
      // Stale topology.mode says "logic" but the directory only holds SKILL.md.
      graph_topology: [
        { id: 'draft', src: 'phases/draft/SKILL.md', depends_on: [], mode: 'logic' },
      ],
      files: {
        'phases/draft/SKILL.md': ['---', 'name: draft', 'llm_role: writer', '---', 'Body'].join('\n'),
      },
    }), new Set(), () => {}, {})

    const draft = phaseNode(nodes, 'draft')
    expect(draft.mode).toBe('agent')
    expect(draft.filePath).toBe('phases/draft/SKILL.md')
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

  // N2 atom #15 (l3-step-edit): the inline step editor is mounted only on AGENT
  // nodes, fed off the REAL on-disk body, and its save forwards through the
  // injected callback (which the canvas binds to the phase-file save path).
  it('wires the inline L3 step editor onto an agent node from its real body, not logic/subgraph nodes', () => {
    const agentBody = ['---', 'name: draft', 'llm_role: writer', '---', '<step id="S1" name="read">Read.</step>'].join('\n')
    const toggles: string[] = []
    const saves: Array<{ nodeId: string; filePath: string; currentBody: string; nextBody: string }> = []
    const nodes = buildNodes('demo', skillDetail({
      phases: ['draft', 'review'],
      graph_topology: [
        { id: 'draft', src: 'phases/draft/SKILL.md', depends_on: [], mode: 'agent' },
        { id: 'review', src: 'phases/review/LOGIC.md', depends_on: ['draft'], mode: 'logic' },
      ],
      files: { 'phases/draft/SKILL.md': agentBody },
    }), new Set(), () => {}, {}, {}, {}, {}, {
      expandedSteps: new Set(['draft']),
      onToggleSteps: (nodeId) => toggles.push(nodeId),
      onStepsSave: (nodeId, filePath, currentBody, nextBody) => saves.push({ nodeId, filePath, currentBody, nextBody }),
    })

    const draft = phaseNode(nodes, 'draft')
    // Body sourced from the real SkillDetail.files (NOT a hand-injected field).
    expect(draft.agentBody).toBe(agentBody)
    expect(draft.isStepsExpanded).toBe(true)
    expect(draft.onToggleSteps).toBeTypeOf('function')
    expect(draft.onStepsSave).toBeTypeOf('function')

    // The bound onStepsSave carries the node id + file path + the pre-edit body
    // (for the optimistic-lock hash) so the canvas can persist + hash correctly.
    draft.onStepsSave?.('<step id="S1" name="read">Edited.</step>')
    expect(saves).toEqual([
      { nodeId: 'draft', filePath: 'phases/draft/SKILL.md', currentBody: agentBody, nextBody: '<step id="S1" name="read">Edited.</step>' },
    ])
    draft.onToggleSteps?.()
    expect(toggles).toEqual(['draft'])

    // A logic node never gets the step editor.
    const review = phaseNode(nodes, 'review')
    expect(review.agentBody).toBeUndefined()
    expect(review.onToggleSteps).toBeUndefined()
    expect(review.onStepsSave).toBeUndefined()
    expect(review.isStepsExpanded).toBe(false)
  })

  it('flags only the affected-downstream nodes as dirty (N5 atom #3), leaving side branches normal', () => {
    const nodes = buildNodes('demo', skillDetail({
      phases: ['draft', 'review', 'sidebar'],
      graph_topology: [
        { id: 'draft', src: 'phases/draft/SKILL.md', depends_on: [], mode: 'agent' },
        { id: 'review', src: 'phases/review/LOGIC.md', depends_on: ['draft'], mode: 'logic' },
        { id: 'sidebar', src: 'phases/sidebar/LOGIC.md', depends_on: [], mode: 'logic' },
      ],
    }), new Set(), () => {}, {}, {}, {}, {}, {
      // The resume-validity `affected_downstream` set the backend returned.
      dirtyDownstreamNodeIds: new Set(['review']),
    })

    // Exactly the affected downstream node is grayed; the unrelated side branch is not.
    expect(phaseNode(nodes, 'review').isDirtyDownstream).toBe(true)
    expect(phaseNode(nodes, 'sidebar').isDirtyDownstream).toBe(false)
    expect(phaseNode(nodes, 'draft').isDirtyDownstream).toBe(false)
  })

  it('leaves every node normal when no dirty-downstream set is provided', () => {
    const nodes = buildNodes('demo', skillDetail({
      phases: ['draft', 'review'],
      graph_topology: [
        { id: 'draft', src: 'phases/draft/SKILL.md', depends_on: [], mode: 'agent' },
        { id: 'review', src: 'phases/review/LOGIC.md', depends_on: ['draft'], mode: 'logic' },
      ],
    }), new Set(), () => {}, {})

    expect(phaseNode(nodes, 'draft').isDirtyDownstream).toBe(false)
    expect(phaseNode(nodes, 'review').isDirtyDownstream).toBe(false)
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

  it('gives each drilled child phase a real per-kind filePath (closing the drill-edit loop), never undefined', () => {
    const mixed: GraphTopologyItem[] = [
      { id: 'plan', src: 'phases/plan/SKILL.md', depends_on: [], mode: 'agent' },
      { id: 'check', src: 'phases/check/LOGIC.md', depends_on: ['plan'], mode: 'logic' },
      { id: 'nested', src: 'phases/nested/SUBGRAPH.md', depends_on: ['plan'], mode: 'subgraph', path: '/skills/grandchild' },
    ]
    const nodes = buildNodesFromTopology('demo', ['plan', 'check', 'nested'], mixed, {})

    // filePath is RELATIVE to the child subgraph's own root, derived from the
    // resolved topology mode — so entering the child as its own skill and
    // opening this path lands on its real phase file (not a parent-scoped stub).
    expect(phaseNode(nodes, 'plan').filePath).toBe('phases/plan/SKILL.md')
    expect(phaseNode(nodes, 'check').filePath).toBe('phases/check/LOGIC.md')
    expect(phaseNode(nodes, 'nested').filePath).toBe('phases/nested/SUBGRAPH.md')
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
