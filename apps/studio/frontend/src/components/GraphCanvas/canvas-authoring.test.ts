import { describe, expect, it } from 'vitest'
import type { SkillDetail } from '@/api/types'
import {
  connectPhaseRefs,
  createPhaseDraft,
  disconnectPhaseRefs,
  phaseRefsFromSkillDetail,
} from './canvas-authoring'

describe('canvas authoring helpers', () => {
  it('builds serializable phase refs from schema v2.1 manifest and topology modes', () => {
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
    expect(createPhaseDraft(detail, 'subgraph', 'demo-skill')).toMatchObject({
      phaseId: 'subgraph',
      filePath: 'phases/subgraph/SUBGRAPH.md',
      phaseRef: { id: 'subgraph', src: 'phases/subgraph', depends_on: [], mode: 'subgraph' },
    })
  })

  it('creates phase files that match the v2.1 node AST fields', () => {
    const detail = skillDetail()
    const logic = createPhaseDraft(detail, 'logic')
    const skill = createPhaseDraft(detail, 'skill')
    const subgraph = createPhaseDraft(detail, 'subgraph', 'demo-skill')

    expect(logic.fileContent).toContain('mode: logic')
    expect(logic.fileContent).toContain('<python_callable>')
    expect(logic.fileContent).not.toContain('execute_steps')

    expect(skill.fileContent).toContain('mode: skill')
    expect(skill.fileContent).toContain('tools: []')
    expect(skill.fileContent).toContain('<system_prompt>')
    expect(skill.fileContent).toContain('<exit_contract>')
    expect(skill.fileContent).not.toContain('llm_role')
    expect(skill.fileContent).not.toContain('agent_tools')
    expect(skill.fileContent).not.toContain('prompt:')

    expect(subgraph.fileContent).toContain('mode: subgraph')
    expect(subgraph.fileContent).toContain('target_skill: demo-skill')
    expect(subgraph.fileContent).not.toContain('sub_skill_ref')
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
})

function skillDetail(overrides: {
  phases?: Array<{ id: string; src: string; depends_on: string[] }>
  graph_topology?: SkillDetail['graph_topology']
} = {}): SkillDetail {
  return {
    manifest: {
      schema_version: '2.1',
      name: 'demo',
      description: 'Demo',
      phases: overrides.phases ?? [],
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
