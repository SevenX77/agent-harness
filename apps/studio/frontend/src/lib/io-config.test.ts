/**
 * io-config — pure logic for the blackboard-first I/O config dialogs
 * (input region F3/F7, PM 2026-07-02 r3).
 */
import { describe, expect, it } from 'vitest'

import type { SkillDetail } from '@/api/types'

import {
  applyGraphArtifacts,
  applyIoInputChecks,
  blackboardAtNode,
  graphArtifactsOf,
  reconcileInputFields,
  reconcileOutputFields,
} from './io-config'

const GRAPH_MD = `---
schema_version: "v0.3.0"
name: demo
io:
  inputs:
    type: object
    required: [chapters, project_id]
    properties:
      chapters: {type: array}
      project_id: {type: string}
  outputs:
    type: object
    required: [story_framework]
    properties:
      story_framework: {type: object}
phases: [fetch, report]
---
<phase depends_on="input">fetch</phase>
<phase depends_on="fetch" output>report</phase>
`

const FETCH_MD = `---
io:
  inputs:
    type: object
    required: [chapters]
    properties:
      chapters: {type: array}
  outputs:
    type: object
    required: [segments]
    properties:
      segments: {type: array}
actions: [fetch]
---
<action>fetch</action>
`

const REPORT_MD = `---
io:
  inputs:
    type: object
    required: [segments]
    properties:
      segments: {type: array}
      style_guide: {type: object, source: file, path: imports/ref/style.json}
  outputs:
    type: object
    required: [story_framework]
    properties:
      story_framework: {type: object}
actions: [report]
---
<action>report</action>
`

function detail(): SkillDetail {
  return {
    id: 'demo',
    graph_topology: [
      { id: 'fetch', depends_on: ['input'] },
      { id: 'report', depends_on: ['fetch'] },
    ],
    files: {
      'GRAPH.md': GRAPH_MD,
      'phases/fetch/LOGIC.md': FETCH_MD,
      'phases/report/SKILL.md': REPORT_MD,
    },
  } as unknown as SkillDetail
}

describe('blackboardAtNode', () => {
  it('lists blackboard fields with checked = declared in io.inputs', () => {
    const rows = blackboardAtNode(detail(), 'report')

    const byName = new Map(rows.map((r) => [r.name, r]))
    expect(byName.get('segments')).toMatchObject({ from: 'fetch', checked: true })
    expect(byName.get('chapters')).toMatchObject({ from: 'input', checked: false })
    expect(byName.get('project_id')).toMatchObject({ from: 'input', checked: false })
    expect(byName.has('style_guide')).toBe(false)
  })
})

describe('reconcileInputFields (r4: matched / available / missing)', () => {
  // report declares io.inputs {segments (on blackboard), glossary (required,
  // no producer → missing), style_guide (source:file → not a blackboard gap)}.
  const RECON_REPORT = `---
io:
  inputs:
    type: object
    required: [segments, glossary]
    properties:
      segments: {type: array}
      glossary: {type: string}
      style_guide: {type: object, source: file, path: imports/ref/style.json}
  outputs:
    type: object
    required: [story_framework]
    properties:
      story_framework: {type: object}
actions: [report]
---
<action>report</action>
`
  function reconDetail(): SkillDetail {
    return {
      id: 'demo',
      graph_topology: [
        { id: 'fetch', depends_on: ['input'] },
        { id: 'report', depends_on: ['fetch'] },
      ],
      files: {
        'GRAPH.md': GRAPH_MD,
        'phases/fetch/LOGIC.md': FETCH_MD,
        'phases/report/SKILL.md': RECON_REPORT,
      },
    } as unknown as SkillDetail
  }

  it('flags a declared-required input with no upstream producer as missing, at the top', () => {
    const rows = reconcileInputFields(reconDetail(), 'report')

    // missing rows come first
    expect(rows[0]).toMatchObject({ name: 'glossary', state: 'missing' })
    expect(rows[0].reason).toMatch(/io\.inputs/)

    const byName = new Map(rows.map((r) => [r.name, r]))
    // consumed field present on the blackboard = matched
    expect(byName.get('segments')).toMatchObject({ state: 'matched', checked: true })
    // available upstream but not consumed
    expect(byName.get('chapters')).toMatchObject({ state: 'available', checked: false })
    // source:'file' declarations are NOT blackboard gaps → never "missing"
    expect(byName.has('style_guide')).toBe(false)
  })

  it('flags graph inputs with no source as missing (Input pseudo-node / GRAPH.md)', () => {
    // GRAPH.md io.inputs = {chapters, project_id}, neither source:'file' →
    // both are declared graph inputs with no wired source → missing.
    const rows = reconcileInputFields(reconDetail(), '')
    expect(rows.every((r) => r.state === 'missing')).toBe(true)
    expect(rows.map((r) => r.name).sort()).toEqual(['chapters', 'project_id'])
    expect(rows[0].reason).toMatch(/graph input/)
  })

  it('does not flag a graph input already backed by a source:file import', () => {
    const withFile = `---
schema_version: "v0.3.0"
name: demo
io:
  inputs:
    type: object
    required: [chapters]
    properties:
      chapters: {type: array, source: file, dir: imports/ch, pattern: "c_{n}.json"}
  outputs:
    type: object
    required: [x]
    properties:
      x: {type: object}
phases: [fetch]
---
<phase depends_on="input" output>fetch</phase>
`
    const detail = { id: 'd', graph_topology: [{ id: 'fetch', depends_on: ['input'] }], files: { 'GRAPH.md': withFile } } as unknown as SkillDetail
    expect(reconcileInputFields(detail, '')).toEqual([])
  })
})

describe('reconcileOutputFields (r4: matched / available / missing)', () => {
  const RECON_GRAPH = `---
schema_version: "v0.3.0"
name: demo
io:
  inputs:
    type: object
    required: [chapters]
    properties:
      chapters: {type: array}
  outputs:
    type: object
    required: [story_framework, final_manifest]
    properties:
      story_framework: {type: object}
      final_manifest: {type: object}
phases: [fetch, report]
---
<phase depends_on="input">fetch</phase>
<phase depends_on="fetch" output>report</phase>
`
  function outDetail(): SkillDetail {
    return {
      id: 'demo',
      graph_topology: [
        { id: 'fetch', depends_on: ['input'] },
        { id: 'report', depends_on: ['fetch'] },
      ],
      files: {
        'GRAPH.md': RECON_GRAPH,
        'phases/fetch/LOGIC.md': FETCH_MD,
        'phases/report/SKILL.md': REPORT_MD,
      },
    } as unknown as SkillDetail
  }

  it('flags a declared-required output with no producer as missing, matches produced outputs', () => {
    const rows = reconcileOutputFields(outDetail())

    // final_manifest is required by io.outputs but no phase produces it
    expect(rows[0]).toMatchObject({ name: 'final_manifest', state: 'missing' })
    expect(rows[0].reason).toMatch(/io\.outputs/)

    const byName = new Map(rows.map((r) => [r.name, r]))
    // story_framework is declared io.outputs AND produced by report = matched
    expect(byName.get('story_framework')).toMatchObject({ state: 'matched', from: 'report' })
    // segments is on the blackboard universe but not a declared graph output
    expect(byName.get('segments')).toMatchObject({ state: 'available' })
  })
})

describe('applyIoInputChecks', () => {
  it('rebuilds io.inputs from checked blackboard fields plus file declarations', () => {
    const next = applyIoInputChecks(REPORT_MD, {
      blackboard: [
        { name: 'segments', type: 'array', checked: true },
        { name: 'project_id', type: 'string', checked: true },
        { name: 'chapters', type: 'array', checked: false },
      ],
      files: [
        {
          field: 'style_guide',
          type: 'object',
          path: 'imports/ref/style.json',
        },
        {
          field: 'chapters_batch',
          type: 'array',
          dir: 'imports/abc_segmentation',
          pattern: 'chapter_{n}_latest_*.json',
          numbers: [1, 2, 7],
        },
      ],
    })

    expect(next).toContain('project_id')
    expect(next).not.toMatch(/chapters:\s*\{?type: array\}?\s*$/m)
    expect(next).toContain('source: file')
    expect(next).toContain('dir: imports/abc_segmentation')
    expect(next).toContain("pattern: chapter_{n}_latest_*.json")
    expect(next).toContain('<action>report</action>')
    const required = next.match(/required:\n(?:\s+- .+\n)+/)?.[0] ?? next
    expect(required).toContain('segments')
  })
})

describe('graph artifacts manifest', () => {
  it('writes io.artifacts onto GRAPH.md and reads it back', () => {
    const next = applyGraphArtifacts(GRAPH_MD, [
      { stem: 'story_framework', mode: 'single', fields: ['story_framework'] },
      {
        stem: 'abc_segmentation',
        mode: 'per-item',
        fields: ['segments'],
      },
    ])

    expect(next).toContain('artifacts:')
    expect(next).toContain('stem: story_framework')
    expect(next).toContain('mode: per-item')
    expect(next).toContain('<phase depends_on="input">fetch</phase>')

    const detailWithArtifacts = {
      ...detail(),
      files: { 'GRAPH.md': next },
    } as unknown as SkillDetail
    const rows = graphArtifactsOf(detailWithArtifacts)
    expect(rows).toHaveLength(2)
    expect(rows[1]).toMatchObject({ stem: 'abc_segmentation', mode: 'per-item' })
  })

  it('removes the artifacts key when the list is empty', () => {
    const withArtifacts = applyGraphArtifacts(GRAPH_MD, [
      { stem: 'x', mode: 'single', fields: ['story_framework'] },
    ])
    const cleared = applyGraphArtifacts(withArtifacts, [])
    expect(cleared).not.toContain('artifacts:')
  })
})
