import { describe, expect, it } from 'vitest'
import type { GraphTopologyItem, ResumeValidityResponse, SkillDetail } from '@/api/types'
import { CURRENT_SCHEMA_VERSION } from '@/config/schema'
import { INPUT_ID, OUTPUT_ID, type SkillGraphNodeData, type SkillNodeStatus } from '@/components/nodes'
import { dirtyDownstreamFromValidity } from '@/components/studio/node-resume'
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

  it('brackets phase nodes with global input/output nodes', () => {
    const nodes = buildNodes('demo', skillDetail({
      phases: ['only'],
      graph_topology: [{ id: 'only', src: 'phases/only/LOGIC.md', depends_on: [], mode: 'logic' }],
    }), new Set(), () => {}, {})

    expect(nodes.map((node) => node.id)).toEqual([INPUT_ID, 'only', OUTPUT_ID])
    expect(nodes.map((node) => node.type)).toEqual(['globalInput', 'skill', 'globalOutput'])
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

  // N2 atom #16 (node-type-derivation, F1): node KIND must derive strictly from
  // FILE EXISTENCE, falling back to topology.mode when no node file is loaded —
  // and must NEVER fall back to the manifest-projected `phase.mode`. The legacy
  // standalone-agent manifest projects `phase.mode = 'llm'`; if that leaks into
  // the kind when neither a phase file nor a topology row exists, F1 is violated.
  it('never falls back to the manifest-projected phase.mode for node kind (F1)', () => {
    // A legacy standalone-agent skill: phasesFromManifest projects ONE phase with
    // mode 'llm'. We give it NO topology row and NO phase file, so the only thing
    // that could set the kind is the (forbidden) manifest phase.mode fallback.
    const nodes = buildNodes('demo', agentSkillDetail(), new Set(), () => {}, {})

    const phase = phaseNode(nodes, 'demo')
    // File-existence → (absent) → topology.mode → (absent) → default kind.
    // The manifest projection 'llm' (which maps to SKILL.md / agent) must NOT win.
    expect(phase.mode).toBe('logic')
    expect(phase.filePath).toBe('phases/demo/LOGIC.md')
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
    // Drill-down still requires a real path field, so a legacy target_skill
    // exposes no drillable path…
    expect(legacy.subgraphPath).toBeNull()
    // …but the inline expand toggle IS wired (it surfaces the recovery state for
    // exactly this unresolved case — F4, PM 2026-06-23).
    expect(legacy.onToggleSubgraph).toBeTypeOf('function')
  })

  it('keeps absolute and relative subgraph paths for drill-down and trims surrounding whitespace', () => {
    const nodes = buildNodes('demo', skillDetail({
      phases: ['trimmed', 'relative'],
      graph_topology: [
        { id: 'trimmed', src: 'phases/trimmed/SUBGRAPH.md', depends_on: [], mode: 'subgraph', path: '  /abs/child  ' },
        { id: 'relative', src: 'phases/relative/SUBGRAPH.md', depends_on: [], mode: 'subgraph', path: 'subgraph/child' },
      ],
    }), new Set(), () => {}, {}, {}, {}, {}, {}, '/skills/parent')

    expect(phaseNode(nodes, 'trimmed').subgraphPath).toBe('/abs/child')
    expect(phaseNode(nodes, 'trimmed').onToggleSubgraph).toBeTypeOf('function')
    // A relative path is still NOT drillable (subgraphPath null)…
    expect(phaseNode(nodes, 'relative').workspaceRoot).toBe('/skills/parent')
    expect(phaseNode(nodes, 'relative').subgraphPath).toBe('subgraph/child')
    // …yet every SUBGRAPH-kind node now gets the expand toggle, so the unresolved
    // one opens its inline recovery state instead of silently offering nothing.
    expect(phaseNode(nodes, 'relative').onToggleSubgraph).toBeTypeOf('function')
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

  it('auto-derives graying from a resume-validity response: affected downstream grayed, side branch not (N5 atom #3)', () => {
    // F-n5 end-to-end: an upstream edit makes the backend return a per-node affected_downstream
    // slice; dirtyDownstreamFromValidity projects it and buildNodes grays exactly those nodes.
    const validity: ResumeValidityResponse = {
      run_id: 'run-1',
      resume_allowed: false,
      reason: 'dirty_upstream',
      checkpoint_id: 'cp',
      checkpoint_ns: 'agent:draft',
      resume_from_node_id: 'draft',
      resume_to_node_id: null,
      dirty_fields: ['content_hash'],
      dirty_node_ids: ['draft', 'review'],
      affected_downstream: ['draft', 'review'],
      snapshot_content_hash: 'a',
      current_content_hash: 'b',
      snapshot_execution_fingerprint: null,
      current_execution_fingerprint: null,
    }
    const nodes = buildNodes('demo', skillDetail({
      phases: ['draft', 'review', 'sidebar'],
      graph_topology: [
        { id: 'draft', src: 'phases/draft/SKILL.md', depends_on: [], mode: 'agent' },
        { id: 'review', src: 'phases/review/LOGIC.md', depends_on: ['draft'], mode: 'logic' },
        { id: 'sidebar', src: 'phases/sidebar/LOGIC.md', depends_on: [], mode: 'logic' },
      ],
    }), new Set(), () => {}, {}, {}, {}, {}, {
      dirtyDownstreamNodeIds: dirtyDownstreamFromValidity(validity),
    })

    expect(phaseNode(nodes, 'draft').isDirtyDownstream).toBe(true)
    expect(phaseNode(nodes, 'review').isDirtyDownstream).toBe(true)
    // The unrelated side branch is absent from the per-node slice (B1) -> stays runnable.
    expect(phaseNode(nodes, 'sidebar').isDirtyDownstream).toBe(false)
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

  it('brackets drilled phase nodes with global input/output and preserves order + deps', () => {
    const nodes = buildNodesFromTopology('demo', ['plan', 'nested'], topology, {})
    expect(nodes.map((node) => node.id)).toEqual([INPUT_ID, 'plan', 'nested', OUTPUT_ID])

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

  it('withholds the step-edit toggle by default (no agentSteps = read-only/loading projection)', () => {
    // n2-canvas #14: with no agentSteps the topology-only view stays non-editable
    // (no onToggleSteps on AGENT nodes) — this is the read-only drilled projection.
    const nodes = buildNodesFromTopology('demo', ['plan', 'nested'], topology, {})
    expect(phaseNode(nodes, 'plan').onToggleSteps).toBeUndefined()
  })

  it('wires the AGENT step-edit toggle when agentSteps is supplied (editable loading path)', () => {
    // n2-canvas #14: the topology-only loading/fallback path threads the step-editor
    // open/close toggle on AGENT (SKILL.md) nodes; non-agent nodes stay untoggled.
    let toggled: string | null = null
    const nodes = buildNodesFromTopology('demo', ['plan', 'nested'], topology, {}, {
      expandedSteps: new Set(['plan']),
      onToggleSteps: (id) => { toggled = id },
    })
    const plan = phaseNode(nodes, 'plan')
    expect(plan.isStepsExpanded).toBe(true)
    expect(typeof plan.onToggleSteps).toBe('function')
    plan.onToggleSteps?.()
    expect(toggled).toBe('plan')
    // The nested subgraph (non-agent) node never gets a step toggle.
    expect(phaseNode(nodes, 'nested').onToggleSteps).toBeUndefined()
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

// A legacy standalone-agent skill (manifest.type === 'agent'). phasesFromManifest
// projects exactly ONE phase named after the manifest, with the manifest-derived
// mode 'llm'. Used to prove node-kind derivation does NOT leak that projection
// (atom #16 / F1) when no phase file and no topology row exist.
function agentSkillDetail(): SkillDetail {
  return {
    manifest: {
      type: 'agent',
      schema_version: '2.0',
      name: 'demo',
      description: 'Demo',
      license: null,
      version: null,
      author: null,
      metadata: null,
      agent_profile: {
        role: 'Agent',
        goal: 'Draft',
        steps: ['Draft'],
        constraints: [],
        domain_protocols: [],
        references: [],
        few_shot_examples: [],
        context_access: ['working_memory'],
        llm_role: 'Agent',
      },
      model_override: null,
      agent_tools: [],
      adopted_persona: null,
      user_prompt_template: null,
      context_mapping: {},
    },
    graph_topology: [],
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
