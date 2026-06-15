import { describe, expect, it } from 'vitest'
import type { SkillDetail } from '@/api/types'
import { CURRENT_SCHEMA_VERSION } from '@/config/schema'
import {
  connectPhaseRefs,
  createPhaseDraft,
  disconnectPhaseRefs,
  phaseRefsFromSkillDetail,
  checkSequentialOverwrites,
  addSequentialOverwriteField,
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
    }

    // LOGIC.md: io slices + actions registry + validator; body <action>. No mode.
    expect(logic.fileContent).toContain('name: logic')
    expect(logic.fileContent).toContain('io:')
    expect(logic.fileContent).toContain('actions: [logic_action]')
    expect(logic.fileContent).toContain('validator: false')
    expect(logic.fileContent).toContain('<action>logic_action</action>')

    // Agent SKILL.md: llm_role + tools + io + validator; body role/goal/step/protocol.
    expect(skill.fileContent).toContain('name: agent')
    expect(skill.fileContent).toContain('llm_role: analyst')
    expect(skill.fileContent).toContain('tools: []')
    expect(skill.fileContent).toContain('io:')
    expect(skill.fileContent).toContain('validator: false')
    expect(skill.fileContent).toContain('<role>')
    expect(skill.fileContent).toContain('<goal>')
    expect(skill.fileContent).toContain('<step id="S1"')
    expect(skill.fileContent).toContain('<protocol id="P1">')

    // SUBGRAPH.md: absolute path placeholder + io + validator. Uses path, not target_skill.
    expect(subgraph.fileContent).toContain('name: subgraph')
    expect(subgraph.fileContent).toContain('path: /absolute/path/to/child_skill')
    expect(subgraph.fileContent).toContain('io:')
    expect(subgraph.fileContent).toContain('validator: false')
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

  it('rejects self dependencies, duplicate dependencies, and global nodes', () => {
    const detail = skillDetail({
      phases: [
        { id: 'draft', src: 'phases/draft/SKILL.md', depends_on: [] },
        { id: 'review', src: 'phases/review/LOGIC.md', depends_on: ['draft'] },
      ],
    })

    expect(connectPhaseRefs(detail, 'draft', 'draft')).toMatchObject({ ok: false, reason: 'self-dependency' })
    expect(connectPhaseRefs(detail, 'draft', 'review')).toMatchObject({ ok: false, reason: 'duplicate-dependency' })
    expect(connectPhaseRefs(detail, '__global_input__', 'review')).toMatchObject({ ok: false, reason: 'global-node' })
    expect(connectPhaseRefs(detail, 'draft', '__global_output__')).toMatchObject({ ok: false, reason: 'global-node' })
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

  it('rejects disconnecting global nodes and missing dependencies', () => {
    const detail = skillDetail({
      phases: [
        { id: 'draft', src: 'phases/draft/SKILL.md', depends_on: [] },
        { id: 'review', src: 'phases/review/LOGIC.md', depends_on: ['draft'] },
      ],
    })

    expect(disconnectPhaseRefs(detail, '__global_input__', 'review')).toMatchObject({ ok: false, reason: 'global-node' })
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
    files: {},
    manifest_errors: null,
    has_golden: false,
    latest_run_metadata: null,
    lint_result: null,
  }
}
