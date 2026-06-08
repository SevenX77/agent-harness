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
  // MVP1: node type is derived from the phase file name (SKILL/LOGIC/SUBGRAPH.md),
  // never from a mutable `mode` discriminator. A misleading topology mode must be ignored.
  it('derives phase ref node type from the file name, ignoring a misleading topology mode', () => {
    const refs = phaseRefsFromSkillDetail(skillDetail({
      phases: [
        { id: 'draft', src: 'phases/draft/SKILL.md', depends_on: [] },
        { id: 'shape', src: 'phases/shape/LOGIC.md', depends_on: ['draft'] },
        { id: 'review', src: 'phases/review/SUBGRAPH.md', depends_on: ['shape'] },
      ],
      graph_topology: [
        // topology mode intentionally contradicts the file name (MVP0 drift signal).
        { id: 'draft', src: 'phases/draft/SKILL.md', depends_on: [], mode: 'logic' },
        { id: 'shape', src: 'phases/shape/LOGIC.md', depends_on: ['draft'], mode: 'subgraph' },
        { id: 'review', src: 'phases/review/SUBGRAPH.md', depends_on: ['shape'], mode: 'skill' },
      ],
    }))

    expect(refs.find((ref) => ref.id === 'draft')?.mode).toBe('skill')
    expect(refs.find((ref) => ref.id === 'shape')?.mode).toBe('logic')
    expect(refs.find((ref) => ref.id === 'review')?.mode).toBe('subgraph')
    // depends_on (the real topology contract) is still carried through unchanged.
    expect(refs.find((ref) => ref.id === 'review')?.depends_on).toEqual(['shape'])
  })

  // MVP1: type comes from the phase file kind on disk. The backend topology carries the
  // engine AST discriminator `mode: "agent"` for SKILL.md phases and a directory-only
  // `src` (no file name). The serialize payload must reflect the real file kind ("skill"),
  // and must NOT coerce an agent into a wrong `logic` DTO from the bare directory src.
  it('derives an agent phase type from its SKILL.md file, not the stale topology mode "agent"', () => {
    const detail = skillDetail({
      phases: [{ id: 'segment', src: 'phases/segment', depends_on: ['input'] }],
      graph_topology: [
        { id: 'segment', src: 'phases/segment', depends_on: ['input'], mode: 'agent' },
      ],
    })
    detail.files = {
      'phases/segment/SKILL.md': '---\nname: segment\n---\n<role>r</role>\n<goal>g</goal>\n',
    }

    const refs = phaseRefsFromSkillDetail(detail)
    expect(refs.find((ref) => ref.id === 'segment')?.mode).toBe('skill')
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
    expect(createPhaseDraft(detail, 'subgraph', 'demo-skill')).toMatchObject({
      phaseId: 'subgraph',
      filePath: 'phases/subgraph/SUBGRAPH.md',
      phaseRef: { id: 'subgraph', src: 'phases/subgraph', depends_on: [], mode: 'subgraph' },
    })
  })

  // MVP1 scaffold contract (FROZEN skill-spec + engine MVP1):
  // Logic = pure-action node. No `mode:` discriminator, no legacy `<python_callable>`.
  // Action signature is the clean `def <name>(inputs) -> dict` form, registered via `actions:`
  // and invoked by a body `<action>` tag, with a companion phase-local action file.
  it('scaffolds a LOGIC.md as an mvp1 pure-action node (no mode/python_callable)', () => {
    const logic = createPhaseDraft(skillDetail(), 'logic')

    expect(logic.filePath).toBe('phases/logic/LOGIC.md')
    expect(logic.fileContent).not.toMatch(/^mode:/m)
    expect(logic.fileContent).not.toContain('<python_callable>')
    expect(logic.fileContent).toMatch(/^actions:/m)
    expect(logic.fileContent).toMatch(/^io:/m)
    expect(logic.fileContent).toMatch(/<action>\s*\w+\s*<\/action>/)

    // The action is a pure function: `def <name>(inputs) -> dict`, shipped as a phase-local file.
    const extraFiles = (logic as unknown as {
      extraFiles?: Array<{ filePath: string; fileContent: string }>
    }).extraFiles
    const actionFile = extraFiles?.find((file) => /\/actions\/\w+\.py$/.test(file.filePath))
    expect(actionFile).toBeDefined()
    expect(actionFile?.fileContent).toMatch(/def \w+\(inputs\)\s*->\s*dict/)
    expect(actionFile?.fileContent).not.toMatch(/def run\s*\(/)
  })

  // MVP1 Agent body = flat XML with required <role>/<goal>. No `mode:`, and the legacy
  // <system_prompt>/<exit_contract> shells are forbidden by FROZEN 05-agent-md-spec.
  it('scaffolds a SKILL.md agent with mvp1 body (role/goal; no mode/system_prompt/exit_contract)', () => {
    const skill = createPhaseDraft(skillDetail(), 'skill')

    expect(skill.filePath).toBe('phases/agent/SKILL.md')
    expect(skill.fileContent).not.toMatch(/^mode:/m)
    expect(skill.fileContent).not.toContain('<system_prompt>')
    expect(skill.fileContent).not.toContain('<exit_contract>')
    expect(skill.fileContent).toContain('<role>')
    expect(skill.fileContent).toContain('<goal>')
    expect(skill.fileContent).toMatch(/^io:/m)
  })

  // MVP1 Subgraph (Studio D7 upper authority): reference the child graph by local `path`,
  // no registry id. The engine AST/loader `target_skill` is treated as drift, not the target.
  it('scaffolds a SUBGRAPH.md by local path (no mode, no bare target_skill)', () => {
    const subgraph = createPhaseDraft(skillDetail(), 'subgraph', './subskills/review')

    expect(subgraph.filePath).toBe('phases/subgraph/SUBGRAPH.md')
    expect(subgraph.fileContent).not.toMatch(/^mode:/m)
    expect(subgraph.fileContent).not.toMatch(/^target_skill:/m)
    expect(subgraph.fileContent).toMatch(/^path:/m)
    expect(subgraph.fileContent).toContain('./subskills/review')
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
io:
  outputs:
    properties:
      report: { type: string }
---
`,
      'phases/review/LOGIC.md': `---
name: review
io:
  outputs:
    properties:
      report: { type: string }
---
`,
      'phases/publish/SKILL.md': `---
name: publish
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
io:
  outputs:
    properties:
      report: { type: string }
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
