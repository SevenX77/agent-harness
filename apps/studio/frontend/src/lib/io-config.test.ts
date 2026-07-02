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
