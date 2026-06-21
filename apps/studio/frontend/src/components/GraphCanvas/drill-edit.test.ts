import { describe, expect, it } from 'vitest'
import { AxiosError, AxiosHeaders, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios'
import type { SkillDetail } from '@/api/types'
import { CURRENT_SCHEMA_VERSION } from '@/config/schema'
import { resolveWorkspaceIdentity } from '@/components/studio/workspace-identity'
import { buildNodes } from './build-nodes'
import { isDrilledChildEditable, isReadOnlySkillError, resolveSaveTarget } from './drill-edit'

// n2-canvas atom #14 (subgraph-drilldown — EDIT-WRITEBACK closure). These are the
// Layer-1 pure-function tests that pin the drilled-child edit-writeback wiring:
// child-identity derivation, child-scoped save routing, the read-only block, and
// the rejected-write rollback decision. Convention: pure-function vitest, no
// @testing-library (mirrors drill-stack.test.ts / build-nodes.test.ts).

describe('drilled child identity derivation', () => {
  it('derives the child skillId + workspaceRoot from the absolute child path', () => {
    // The drill effect fetches childGraph.path (the backend-resolved absolute child
    // root). `resolveWorkspaceIdentity('local:' + childPath)` is the SAME resolution
    // the (now-removed) pushNavSkill escape hatch relied on.
    const identity = resolveWorkspaceIdentity('local:/abs/workspaces/default/skills/child-skill')
    expect(identity.skillId).toBe('child-skill')
    expect(identity.workspaceRoot).toBe('/abs/workspaces/default/skills/child-skill')
  })

  it('builds drilled nodes keyed to the CHILD skillId with child-relative file paths', () => {
    // At depth Option A renders the child's full SkillDetail with buildNodes keyed to
    // the child identity, so each node carries data.skillId === childSkillId and a
    // child-relative filePath (phases/<id>/SKILL.md), not the parent's.
    const childSkillId = 'child-skill'
    const nodes = buildNodes(childSkillId, childDetail({
      phases: ['draft', 'review'],
      graph_topology: [
        { id: 'draft', src: 'phases/draft/SKILL.md', depends_on: [], mode: 'agent' },
        { id: 'review', src: 'phases/review/LOGIC.md', depends_on: ['draft'], mode: 'logic' },
      ],
      files: {
        'phases/draft/SKILL.md': ['---', 'name: draft', 'llm_role: writer', '---', 'Body'].join('\n'),
      },
    }), new Set(), () => {}, {})

    const draft = nodeData(nodes, 'draft')
    expect(draft.skillId).toBe(childSkillId)
    expect(draft.filePath).toBe('phases/draft/SKILL.md')
    const review = nodeData(nodes, 'review')
    expect(review.skillId).toBe(childSkillId)
    expect(review.filePath).toBe('phases/review/LOGIC.md')
  })
})

describe('resolveSaveTarget (child-scoped save routing)', () => {
  const parent = { skillId: 'parent-skill', workspaceRoot: '/ws/default/skills/parent-skill' }
  const child = { skillId: 'child-skill', workspaceRoot: '/ws/default/skills/child-skill' }

  it('returns the parent identity when NOT drilled (no drilled-child target)', () => {
    expect(resolveSaveTarget(parent, null)).toEqual(parent)
  })

  it('returns the CHILD identity when drilled into an editable child', () => {
    expect(resolveSaveTarget(parent, child)).toEqual(child)
  })

  it('never returns the parent skillId once a drilled child target is present', () => {
    const target = resolveSaveTarget(parent, child)
    expect(target.skillId).toBe('child-skill')
    expect(target.skillId).not.toBe('parent-skill')
    expect(target.workspaceRoot).toBe('/ws/default/skills/child-skill')
  })
})

describe('isDrilledChildEditable (read-only block, path-based, frontend-only)', () => {
  // Editable iff the child lives under the parent skill tree OR under the editable
  // workspace skills dir (dirname of the parent's workspaceRoot). A bundled child
  // (under the read-only public SKILLS_DIR) shares neither prefix → read-only.
  const parentRoot = '/app/workspaces/default/skills/parent-skill'

  it('treats a sibling child under the same workspace skills dir as editable', () => {
    expect(isDrilledChildEditable('/app/workspaces/default/skills/child-skill', parentRoot, false)).toBe(true)
  })

  it('treats a nested phases-as-subgraph child under the parent tree as editable', () => {
    expect(isDrilledChildEditable('/app/workspaces/default/skills/parent-skill/phases/sub', parentRoot, false)).toBe(true)
  })

  it('treats a bundled/public child (different root) as READ-ONLY', () => {
    expect(isDrilledChildEditable('/app/resources/skills/bundled-child', parentRoot, false)).toBe(false)
    expect(isDrilledChildEditable('/app/resources/skills/bundled-child', parentRoot, true)).toBe(false)
  })

  it('null parent root: read-only under Tauri (native writer never refuses), permitted in browser', () => {
    // Tauri + null parent root → must default read-only: the native writer has no
    // read-only guard, so a wrong "editable" verdict would silently mutate the bundle.
    expect(isDrilledChildEditable('/anywhere/child', null, true)).toBe(false)
    // Browser + null parent root → permit the attempt; the update_skill_file 403
    // (isReadOnlySkillError) is the reliable backstop.
    expect(isDrilledChildEditable('/anywhere/child', null, false)).toBe(true)
  })
})

describe('isReadOnlySkillError (browser 403 backstop)', () => {
  it('detects a 403 SKILL_READ_ONLY error_code', () => {
    expect(isReadOnlySkillError(axiosError(403, { error_code: 'SKILL_READ_ONLY' }))).toBe(true)
  })

  it('does NOT treat a 409 hash conflict or other errors as read-only', () => {
    expect(isReadOnlySkillError(axiosError(409, { error_code: 'HASH_CONFLICT' }))).toBe(false)
    expect(isReadOnlySkillError(axiosError(422, { error_code: 'MANIFEST_VALIDATION_FAILED' }))).toBe(false)
    expect(isReadOnlySkillError(new Error('boom'))).toBe(false)
  })
})

function nodeData(nodes: ReturnType<typeof buildNodes>, id: string) {
  const node = nodes.find((candidate) => candidate.id === id)
  if (!node || node.type !== 'skill') {
    throw new Error(`phase node ${id} not found`)
  }
  return node.data
}

function childDetail(overrides: {
  phases?: string[]
  graph_topology?: SkillDetail['graph_topology']
  files?: SkillDetail['files']
} = {}): SkillDetail {
  return {
    manifest: {
      schema_version: CURRENT_SCHEMA_VERSION,
      name: 'child',
      description: 'Child subgraph',
      io: {
        inputs: { type: 'object', properties: {} },
        outputs: { type: 'object', properties: {} },
      },
      phases: overrides.phases ?? [],
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

function axiosError(status: number, data: Record<string, unknown>): AxiosError {
  const config: InternalAxiosRequestConfig = { headers: new AxiosHeaders() }
  const response: AxiosResponse = {
    data,
    status,
    statusText: '',
    headers: {},
    config,
  }
  const error = new AxiosError('err', 'ERR_BAD_RESPONSE', config, null, response)
  error.isAxiosError = true
  return error
}
