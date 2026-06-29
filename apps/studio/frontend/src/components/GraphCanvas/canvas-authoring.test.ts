import { describe, expect, it } from 'vitest'
import type { SkillDetail } from '@/api/types'
import { INPUT_ID, OUTPUT_ID } from '@/components/nodes'
import { CURRENT_SCHEMA_VERSION } from '@/config/schema'
import {
  connectPhaseRefs,
  createPhaseDraft,
  defaultPhaseId,
  disconnectPhaseRefs,
  isSafePhaseId,
  phaseDirectoryPath,
  phaseDirectoryIdsFromSkillDetail,
  reconnectPhaseRefs,
  phaseRefsFromSkillDetail,
  phaseNameError,
  renamePhaseRefs,
  removePhaseRefs,
  orphanPhaseDirectoryIds,
  checkSequentialOverwrites,
  addSequentialOverwriteField,
  planEdgeReconnect,
} from './canvas-authoring'

describe('canvas authoring helpers', () => {
  it('builds serializable phase refs from schema current version manifest and topology modes', () => {
    const refs = phaseRefsFromSkillDetail(skillDetail({
      phases: [
        { id: 'draft', src: 'phases/draft/SKILL.md', depends_on: [] },
        { id: 'review', src: 'phases/review/LOGIC.md', depends_on: ['draft'] },
      ],
      graph_topology: [
        { id: 'draft', src: 'phases/draft/SKILL.md', depends_on: [], mode: 'skill' },
        { id: 'review', src: 'phases/review/LOGIC.md', depends_on: ['draft'], mode: 'logic' },
      ],
    }))

    expect(refs).toEqual([
      { id: 'draft', src: 'phases/draft/SKILL.md', depends_on: [], mode: 'skill' },
      { id: 'review', src: 'phases/review/LOGIC.md', depends_on: ['draft'], mode: 'logic' },
    ])
  })

  it('keeps topology dependencies literal instead of rewriting graph-entry sentinels', () => {
    const refs = phaseRefsFromSkillDetail(skillDetail({
      phases: [
        { id: 'segmentation', src: 'phases/segmentation/SKILL.md', depends_on: ['input'] },
        { id: 'analysis', src: 'phases/analysis/LOGIC.md', depends_on: ['segmentation'] },
      ],
      graph_topology: [
        { id: 'segmentation', src: 'phases/segmentation/SKILL.md', depends_on: ['input'], mode: 'skill' },
        { id: 'analysis', src: 'phases/analysis/LOGIC.md', depends_on: ['segmentation'], mode: 'logic' },
      ],
    }))

    expect(refs).toEqual([
      { id: 'segmentation', src: 'phases/segmentation/SKILL.md', depends_on: ['input'], mode: 'skill' },
      { id: 'analysis', src: 'phases/analysis/LOGIC.md', depends_on: ['segmentation'], mode: 'logic' },
    ])
  })

  it('preserves explicit output markers from topology rows', () => {
    const refs = phaseRefsFromSkillDetail(skillDetail({
      phases: [
        { id: 'draft', src: 'phases/draft/SKILL.md', depends_on: [] },
        { id: 'review', src: 'phases/review/LOGIC.md', depends_on: ['draft'] },
      ],
      graph_topology: [
        { id: 'draft', src: 'phases/draft/SKILL.md', depends_on: [], mode: 'skill' },
        { id: 'review', src: 'phases/review/LOGIC.md', depends_on: ['draft'], mode: 'logic', output: true },
      ],
    }))

    expect(refs).toEqual([
      { id: 'draft', src: 'phases/draft/SKILL.md', depends_on: [], mode: 'skill' },
      { id: 'review', src: 'phases/review/LOGIC.md', depends_on: ['draft'], mode: 'logic', output: true },
    ])
  })

  it('creates logic, skill, and subgraph phase drafts with matching file paths', () => {
    const detail = skillDetail()

    expect(createPhaseDraft(detail, 'logic')).toMatchObject({
      phaseId: 'logic',
      filePath: 'phases/logic/LOGIC.md',
      phaseRef: { id: 'logic', src: 'phases/logic', depends_on: [], mode: 'logic' },
    })
    expect(createPhaseDraft(detail, 'skill')).toMatchObject({
      phaseId: 'agent',
      filePath: 'phases/agent/SKILL.md',
      phaseRef: { id: 'agent', src: 'phases/agent', depends_on: [], mode: 'skill' },
    })
    expect(createPhaseDraft(detail, 'subgraph')).toMatchObject({
      phaseId: 'subgraph',
      filePath: 'phases/subgraph/SUBGRAPH.md',
      phaseRef: { id: 'subgraph', src: 'phases/subgraph', depends_on: [], mode: 'subgraph' },
    })
  })

  it('scaffolds FROZEN-clean phase files with no deprecated frontmatter fields', () => {
    const detail = skillDetail()
    const logic = createPhaseDraft(detail, 'logic')
    const skill = createPhaseDraft(detail, 'skill')
    const subgraph = createPhaseDraft(detail, 'subgraph')

    // No scaffold may emit any FROZEN-violating field.
    for (const content of [logic.fileContent, skill.fileContent, subgraph.fileContent]) {
      expect(content).not.toContain('mode:')
      expect(content).not.toContain('system_prompt')
      expect(content).not.toContain('exit_contract')
      expect(content).not.toContain('python_callable')
      expect(content).not.toContain('target_skill')
      expect(content).not.toContain('depends_on')
      expect(content).not.toContain('sub_skill_ref')
    }

    // New canvas nodes are topologically clean: no dependencies and no output
    // marker are invented during creation.
    for (const draft of [logic, skill, subgraph]) {
      expect(draft.phaseRef.depends_on).toEqual([])
      expect(draft.phaseRef.output).toBeUndefined()
    }

    // But the source files should still use the MVP1 phase skeleton so users
    // edit real fields instead of starting from an under-shaped stub.
    expect(logic.fileContent).toContain('name: logic')
    expect(logic.fileContent).toContain('io:')
    expect(logic.fileContent).toContain('inputs:')
    expect(logic.fileContent).toContain('outputs:')
    expect(logic.fileContent).toContain('actions:')
    // LOGIC requires at least one <action> tag — scaffold it (empty) so the required
    // tag is discoverable, mirroring the agent scaffold's <role>/<goal>.
    expect(logic.fileContent).toContain('<action>')

    expect(skill.fileContent).toContain('name: agent')
    expect(skill.fileContent).toContain('io:')
    expect(skill.fileContent).toContain('inputs:')
    expect(skill.fileContent).toContain('outputs:')
    expect(skill.fileContent).toContain('<role>')
    expect(skill.fileContent).toContain('<goal>')

    expect(subgraph.fileContent).toContain('name: subgraph')
    expect(subgraph.fileContent).toContain('path:')
    expect(subgraph.fileContent).toContain('io:')
    expect(subgraph.fileContent).toContain('inputs:')
    expect(subgraph.fileContent).toContain('outputs:')
  })

  it('creates a phase draft with a submitted safe node name', () => {
    const detail = skillDetail({
      phases: [
        { id: 'logic', src: 'phases/logic/LOGIC.md', depends_on: [] },
      ],
    })

    expect(createPhaseDraft(detail, 'logic', [], 'summarize_events')).toMatchObject({
      phaseId: 'summarize_events',
      filePath: 'phases/summarize_events/LOGIC.md',
      phaseRef: { id: 'summarize_events', src: 'phases/summarize_events', depends_on: [], mode: 'logic' },
    })
  })

  it('appends a numeric suffix when the readable phase id already exists', () => {
    const detail = skillDetail({
      phases: [
        { id: 'logic', src: 'phases/logic/LOGIC.md', depends_on: [] },
        { id: 'logic-2', src: 'phases/logic-2/LOGIC.md', depends_on: [] },
      ],
    })

    expect(createPhaseDraft(detail, 'logic')).toMatchObject({
      phaseId: 'logic-3',
      filePath: 'phases/logic-3/LOGIC.md',
    })
  })

  it('reserves root phase directories that exist on disk even when GRAPH.md no longer lists them', () => {
    const detail = skillDetail({
      phases: [],
      files: {
        'GRAPH.md': 'graph before\n',
        'phases/logic/LOGIC.md': 'stale logic before\n',
        'phases/logic-2/LOGIC.md': 'stale logic 2 before\n',
        'subgraph/child/phases/logic/LOGIC.md': 'child skill phase is not a root phase\n',
      },
    })

    expect(phaseDirectoryIdsFromSkillDetail(detail)).toEqual(['logic', 'logic-2'])
    expect(defaultPhaseId(detail, 'logic')).toBe('logic-3')
    expect(createPhaseDraft(detail, 'logic')).toMatchObject({
      phaseId: 'logic-3',
      filePath: 'phases/logic-3/LOGIC.md',
      phaseRef: { id: 'logic-3', src: 'phases/logic-3', depends_on: [], mode: 'logic' },
    })
  })

  it('validates submitted phase names against both GRAPH.md and root phase directories', () => {
    const detail = skillDetail({
      phases: [
        { id: 'draft', src: 'phases/draft/SKILL.md', depends_on: [] },
      ],
      files: {
        'GRAPH.md': 'graph before\n',
        'phases/stale/LOGIC.md': 'stale before\n',
      },
    })

    expect(phaseNameError('', detail)).toBe('Phase name is required.')
    expect(phaseNameError('bad name', detail)).toContain('Phase names must start')
    expect(phaseNameError('draft', detail)).toBe('A phase named draft already exists.')
    expect(phaseNameError('stale', detail)).toBe('A phase named stale already exists.')
    expect(phaseNameError('next_phase', detail)).toBeNull()
  })

  it('finds root phase directories that are absent from the next GRAPH.md phase list', () => {
    const detail = skillDetail({
      phases: [
        { id: 'draft', src: 'phases/draft/SKILL.md', depends_on: [] },
      ],
      files: {
        'GRAPH.md': 'graph before\n',
        'phases/draft/SKILL.md': 'draft before\n',
        'phases/stale/LOGIC.md': 'stale before\n',
        'subgraph/child/phases/child_stale/LOGIC.md': 'child phase before\n',
      },
    })

    expect(orphanPhaseDirectoryIds(detail, [
      { id: 'draft', src: 'phases/draft', depends_on: [], mode: 'skill' },
    ])).toEqual(['stale'])
  })

  it('adds source as a dependency of the target phase', () => {
    const result = connectPhaseRefs(skillDetail({
      phases: [
        { id: 'draft', src: 'phases/draft/SKILL.md', depends_on: [] },
        { id: 'review', src: 'phases/review/LOGIC.md', depends_on: [] },
      ],
      graph_topology: [
        { id: 'draft', src: 'phases/draft/SKILL.md', depends_on: [], mode: 'skill' },
        { id: 'review', src: 'phases/review/LOGIC.md', depends_on: [], mode: 'logic' },
      ],
    }), 'draft', 'review')

    expect(result.ok).toBe(true)
    if (!result.ok) return
    expect(result.phases.find((phase) => phase.id === 'review')?.depends_on).toEqual(['draft'])
  })

  it('connects graph input to a phase by writing depends_on input', () => {
    const result = connectPhaseRefs(skillDetail({
      phases: [
        { id: 'draft', src: 'phases/draft/SKILL.md', depends_on: [] },
      ],
      graph_topology: [
        { id: 'draft', src: 'phases/draft/SKILL.md', depends_on: [], mode: 'skill' },
      ],
    }), INPUT_ID, 'draft')

    expect(result.ok).toBe(true)
    if (!result.ok) return
    expect(result.phases.find((phase) => phase.id === 'draft')?.depends_on).toEqual(['input'])
  })

  it('connects a phase to graph output by writing the explicit output marker', () => {
    const result = connectPhaseRefs(skillDetail({
      phases: [
        { id: 'draft', src: 'phases/draft/SKILL.md', depends_on: [] },
      ],
      graph_topology: [
        { id: 'draft', src: 'phases/draft/SKILL.md', depends_on: [], mode: 'skill' },
      ],
    }), 'draft', OUTPUT_ID)

    expect(result.ok).toBe(true)
    if (!result.ok) return
    expect(result.phases.find((phase) => phase.id === 'draft')?.output).toBe(true)
  })

  it('rejects self dependencies, duplicate dependencies, and unknown phase ids', () => {
    const detail = skillDetail({
      phases: [
        { id: 'draft', src: 'phases/draft/SKILL.md', depends_on: [] },
        { id: 'review', src: 'phases/review/LOGIC.md', depends_on: ['draft'] },
      ],
    })

    expect(connectPhaseRefs(detail, 'draft', 'draft')).toMatchObject({ ok: false, reason: 'self-dependency' })
    expect(connectPhaseRefs(detail, 'draft', 'review')).toMatchObject({ ok: false, reason: 'duplicate-dependency' })
    expect(connectPhaseRefs(detail, 'missing_phase', 'review')).toMatchObject({ ok: false, reason: 'unknown-phase' })
    expect(connectPhaseRefs(detail, 'draft', 'missing_phase')).toMatchObject({ ok: false, reason: 'unknown-phase' })
  })

  it('removes source from the target dependency list when disconnecting phase refs', () => {
    const result = disconnectPhaseRefs(skillDetail({
      phases: [
        { id: 'draft', src: 'phases/draft/SKILL.md', depends_on: [] },
        { id: 'review', src: 'phases/review/LOGIC.md', depends_on: ['draft', 'research'] },
        { id: 'research', src: 'phases/research/LOGIC.md', depends_on: [] },
      ],
    }), 'draft', 'review')

    expect(result.ok).toBe(true)
    if (!result.ok) return
    expect(result.phases.find((phase) => phase.id === 'review')?.depends_on).toEqual(['research'])
  })

  it('disconnects graph input and graph output boundary markers', () => {
    const detail = skillDetail({
      phases: [
        { id: 'draft', src: 'phases/draft/SKILL.md', depends_on: ['input'] },
      ],
      graph_topology: [
        { id: 'draft', src: 'phases/draft/SKILL.md', depends_on: ['input'], mode: 'skill', output: true },
      ],
    })

    const withoutInput = disconnectPhaseRefs(detail, INPUT_ID, 'draft')
    expect(withoutInput.ok).toBe(true)
    if (withoutInput.ok) {
      expect(withoutInput.phases.find((phase) => phase.id === 'draft')?.depends_on).toEqual([])
      expect(withoutInput.phases.find((phase) => phase.id === 'draft')?.output).toBe(true)
    }

    const withoutOutput = disconnectPhaseRefs(detail, 'draft', OUTPUT_ID)
    expect(withoutOutput.ok).toBe(true)
    if (withoutOutput.ok) {
      expect(withoutOutput.phases.find((phase) => phase.id === 'draft')?.depends_on).toEqual(['input'])
      expect(withoutOutput.phases.find((phase) => phase.id === 'draft')?.output).toBeUndefined()
    }
  })

  it('removes a phase and clears incoming dependencies when deleting phase refs', () => {
    const result = removePhaseRefs(skillDetail({
      phases: [
        { id: 'draft', src: 'phases/draft/SKILL.md', depends_on: [] },
        { id: 'review', src: 'phases/review/LOGIC.md', depends_on: ['draft'] },
        { id: 'publish', src: 'phases/publish/LOGIC.md', depends_on: ['review', 'draft'] },
      ],
    }), 'draft')

    expect(result.ok).toBe(true)
    if (!result.ok) return
    expect(result.phases.map((phase) => phase.id)).toEqual(['review', 'publish'])
    expect(result.phases.find((phase) => phase.id === 'review')?.depends_on).toEqual([])
    expect(result.phases.find((phase) => phase.id === 'publish')?.depends_on).toEqual(['review'])
    expect(phaseDirectoryPath('draft')).toBe('phases/draft')
  })

  it('renames a phase id, folder src, and every dependent reference together', () => {
    const result = renamePhaseRefs(skillDetail({
      phases: [
        { id: 'extract', src: 'phases/extract/SUBGRAPH.md', depends_on: [] },
        { id: 'stitch', src: 'phases/stitch/SKILL.md', depends_on: ['extract'] },
        { id: 'review', src: 'phases/review/LOGIC.md', depends_on: ['stitch', 'extract'] },
      ],
    }), 'extract', 'event_extraction')

    expect(result.ok).toBe(true)
    if (!result.ok) return
    expect(result.phases.map((phase) => phase.id)).toEqual(['event_extraction', 'stitch', 'review'])
    expect(result.phases[0]).toMatchObject({ src: 'phases/event_extraction' })
    expect(result.phases.find((phase) => phase.id === 'stitch')?.depends_on).toEqual(['event_extraction'])
    expect(result.phases.find((phase) => phase.id === 'review')?.depends_on).toEqual(['stitch', 'event_extraction'])
  })

  it('rejects duplicate or unsafe phase rename targets', () => {
    const detail = skillDetail({
      phases: [
        { id: 'extract', src: 'phases/extract/SUBGRAPH.md', depends_on: [] },
        { id: 'review', src: 'phases/review/LOGIC.md', depends_on: ['extract'] },
      ],
    })

    expect(isSafePhaseId('event_extraction')).toBe(true)
    expect(isSafePhaseId('event extraction')).toBe(false)
    expect(renamePhaseRefs(detail, 'extract', 'review')).toMatchObject({ ok: false, reason: 'duplicate-phase' })
    expect(renamePhaseRefs(detail, 'extract', '../escape')).toMatchObject({ ok: false, reason: 'invalid-phase' })
  })

  it('rejects disconnecting unknown phase ids and missing dependencies', () => {
    const detail = skillDetail({
      phases: [
        { id: 'draft', src: 'phases/draft/SKILL.md', depends_on: [] },
        { id: 'review', src: 'phases/review/LOGIC.md', depends_on: ['draft'] },
      ],
    })

    expect(disconnectPhaseRefs(detail, 'missing_phase', 'review')).toMatchObject({ ok: false, reason: 'unknown-phase' })
    expect(disconnectPhaseRefs(detail, 'review', 'draft')).toMatchObject({ ok: false, reason: 'missing-dependency' })
  })

  it('detects sequential overwrite conflicts correctly and honors allow_sequential_overwrite whitelist', () => {
    const detail = skillDetail({
      phases: [
        { id: 'draft', src: 'phases/draft/SKILL.md', depends_on: [] },
        { id: 'review', src: 'phases/review/LOGIC.md', depends_on: ['draft'] },
        { id: 'publish', src: 'phases/publish/SKILL.md', depends_on: ['review'] },
      ],
    })

    // Add mock files with yaml frontmatter
    detail.files = {
      'phases/draft/SKILL.md': `---
name: draft
mode: skill
io:
  outputs:
    properties:
      report: { type: string }
---
`,
      'phases/review/LOGIC.md': `---
name: review
mode: logic
io:
  outputs:
    properties:
      report: { type: string }
---
`,
      'phases/publish/SKILL.md': `---
name: publish
mode: skill
io:
  outputs:
    properties:
      report: { type: string }
allow_sequential_overwrite:
  - report
---
`,
    }

    const phases = [
      { id: 'draft', src: 'phases/draft/SKILL.md', depends_on: [], mode: 'skill' as const },
      { id: 'review', src: 'phases/review/LOGIC.md', depends_on: ['draft'], mode: 'logic' as const },
      { id: 'publish', src: 'phases/publish/SKILL.md', depends_on: ['review'], mode: 'skill' as const },
    ]

    const conflicts = checkSequentialOverwrites(detail, phases)

    // 'review' conflicts with 'draft' on 'report' since it's not whitelisted in 'review'.
    // 'publish' does NOT conflict since 'report' is whitelisted in 'publish'.
    expect(conflicts).toHaveLength(1)
    expect(conflicts[0]).toEqual({
      nodeId: 'review',
      fieldName: 'report',
      ancestorNodeId: 'draft',
    })
  })

  it('plans an edge reconnect as an old-target disconnect plus new-target connect', () => {
    // Drag the target endpoint of draft→review over to publish: review loses the
    // draft dependency, publish gains it. Both halves reuse disconnect/connect.
    const plan = planEdgeReconnect(
      { source: 'draft', target: 'review' },
      { source: 'draft', target: 'publish' },
    )

    expect(plan).toEqual({
      ok: true,
      disconnect: { source: 'draft', target: 'review' },
      connect: { source: 'draft', target: 'publish' },
    })
  })

  it('plans a source-endpoint reconnect by swapping the dependency provider', () => {
    // Drag the source endpoint of draft→publish over to review: publish stops
    // depending on draft and starts depending on review.
    const plan = planEdgeReconnect(
      { source: 'draft', target: 'publish' },
      { source: 'review', target: 'publish' },
    )

    expect(plan).toEqual({
      ok: true,
      disconnect: { source: 'draft', target: 'publish' },
      connect: { source: 'review', target: 'publish' },
    })
  })

  it('rejects reconnecting onto itself, back to the same endpoints, or with missing endpoints', () => {
    expect(planEdgeReconnect(
      { source: null, target: 'review' },
      { source: 'draft', target: 'review' },
    )).toMatchObject({ ok: false, reason: 'invalid-endpoint' })

    expect(planEdgeReconnect(
      { source: 'draft', target: 'review' },
      { source: 'review', target: 'review' },
    )).toMatchObject({ ok: false, reason: 'self-dependency' })

    expect(planEdgeReconnect(
      { source: 'draft', target: 'review' },
      { source: 'draft', target: 'review' },
    )).toMatchObject({ ok: false, reason: 'no-op' })
  })

  it('reconnects an edge as one combined phases list: old dependency removed and new one added', () => {
    // n2-canvas #8: a reconnect is a SINGLE atomic depends_on mutation. Dragging
    // the draft→review target over to publish must, in one pass, drop draft from
    // review.depends_on AND add draft to publish.depends_on — never two serialize
    // round-trips against separately-derived phase lists.
    const detail = skillDetail({
      phases: [
        { id: 'draft', src: 'phases/draft/SKILL.md', depends_on: [] },
        { id: 'review', src: 'phases/review/LOGIC.md', depends_on: ['draft'] },
        { id: 'publish', src: 'phases/publish/SKILL.md', depends_on: [] },
      ],
    })

    const result = reconnectPhaseRefs(
      detail,
      { source: 'draft', target: 'review' },
      { source: 'draft', target: 'publish' },
    )

    expect(result.ok).toBe(true)
    if (!result.ok) return
    expect(result.phases.find((phase) => phase.id === 'review')?.depends_on).toEqual([])
    expect(result.phases.find((phase) => phase.id === 'publish')?.depends_on).toEqual(['draft'])
  })

  it('reconnects a source-endpoint move on a shared target into one phases list', () => {
    // Drag the source endpoint of draft→publish over to review: publish drops
    // draft and gains review, all on the single publish phase, in one pass.
    const detail = skillDetail({
      phases: [
        { id: 'draft', src: 'phases/draft/SKILL.md', depends_on: [] },
        { id: 'review', src: 'phases/review/LOGIC.md', depends_on: [] },
        { id: 'publish', src: 'phases/publish/SKILL.md', depends_on: ['draft'] },
      ],
    })

    const result = reconnectPhaseRefs(
      detail,
      { source: 'draft', target: 'publish' },
      { source: 'review', target: 'publish' },
    )

    expect(result.ok).toBe(true)
    if (!result.ok) return
    expect(result.phases.find((phase) => phase.id === 'publish')?.depends_on).toEqual(['review'])
  })

  it('rejects reconnecting unknown phase ids, self-dependencies, no-ops, missing old deps, and duplicates', () => {
    const detail = skillDetail({
      phases: [
        { id: 'draft', src: 'phases/draft/SKILL.md', depends_on: [] },
        { id: 'review', src: 'phases/review/LOGIC.md', depends_on: ['draft'] },
        { id: 'publish', src: 'phases/publish/SKILL.md', depends_on: ['draft'] },
      ],
    })

    expect(reconnectPhaseRefs(detail, { source: 'draft', target: 'review' }, { source: 'draft', target: 'missing_phase' }))
      .toMatchObject({ ok: false, reason: 'unknown-phase' })
    expect(reconnectPhaseRefs(detail, { source: 'draft', target: 'review' }, { source: 'review', target: 'review' }))
      .toMatchObject({ ok: false, reason: 'self-dependency' })
    expect(reconnectPhaseRefs(detail, { source: 'draft', target: 'review' }, { source: 'draft', target: 'review' }))
      .toMatchObject({ ok: false, reason: 'no-op' })
    // The old edge is not backed by a real dependency (review→draft does not exist).
    expect(reconnectPhaseRefs(detail, { source: 'review', target: 'draft' }, { source: 'draft', target: 'publish' }))
      .toMatchObject({ ok: false, reason: 'missing-dependency' })
    // Moving draft→review's target onto publish, which already depends on draft.
    expect(reconnectPhaseRefs(detail, { source: 'draft', target: 'review' }, { source: 'draft', target: 'publish' }))
      .toMatchObject({ ok: false, reason: 'duplicate-dependency' })
  })

  it('updates markdown frontmatter correctly via addSequentialOverwriteField', () => {
    const markdown = `---
name: review
mode: logic
---
# review
`
    const updated = addSequentialOverwriteField(markdown, 'report')
    expect(updated).toContain('allow_sequential_overwrite:')
    expect(updated).toContain('- report')
    expect(updated).toContain('# review')
  })
})

function skillDetail(overrides: {
  phases?: Array<{ id: string; src: string; depends_on: string[] }>
  graph_topology?: SkillDetail['graph_topology']
  files?: Record<string, string>
} = {}): SkillDetail {
  const phases = overrides.phases ?? []
  const graph_topology = overrides.graph_topology ?? phases.map((p) => ({
    id: p.id,
    src: p.src,
    depends_on: p.depends_on,
    mode: p.src.endsWith('/SKILL.md') ? 'skill' : p.src.endsWith('/SUBGRAPH.md') ? 'subgraph' : 'logic',
  }))

  return {
    manifest: {
      schema_version: CURRENT_SCHEMA_VERSION,
      name: 'demo',
      description: 'Demo',
      io: {
        inputs: { type: 'object', properties: {} },
        outputs: { type: 'object', properties: {} },
      },
      phases: phases.map((p) => p.id),
    },
    graph_topology,
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
