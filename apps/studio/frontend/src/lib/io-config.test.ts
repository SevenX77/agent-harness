/**
 * io-config — pure logic for the blackboard-first I/O config dialogs
 * (input region F3/F7, PM 2026-07-02 r3).
 */
import { describe, expect, it } from 'vitest'

import type { RuntimeConfig, SkillDetail } from '@/api/types'

import {
  applyIoInputChecks,
  blackboardAtNode,
  blackboardAtOutput,
  declaredInputFieldNames,
  reconcileInputFields,
  reconcileOutputFields,
  runtimeArtifactsOf,
  runtimeFileFieldsInImportScope,
} from './io-config'
import { parseFrontmatter } from './io-declarations'

interface FieldSchemaShape {
  type?: string
  required?: string[]
  properties?: Record<string, FieldSchemaShape>
}

/** Parse a written md string's frontmatter into a typed-enough shape for assertions. */
function parseFrontmatterYaml(content: string): {
  io: { inputs: { required?: string[]; properties: Record<string, FieldSchemaShape> } }
} {
  return parseFrontmatter(content) as never
}

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
      style_guide: {type: object}
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
  // no producer -> missing), style_guide (runtime_config -> not a blackboard gap)}.
  const RECON_REPORT = `---
io:
  inputs:
    type: object
    required: [segments, glossary]
    properties:
      segments: {type: array}
      glossary: {type: string}
      style_guide: {type: object}
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
    const rows = reconcileInputFields(reconDetail(), 'report', [
      { field: 'style_guide', type: 'object', path: 'import_files/.phase/report/ref/style.json' },
    ])

    // missing rows come first
    expect(rows[0]).toMatchObject({ name: 'glossary', state: 'missing' })
    expect(rows[0].reason).toMatch(/io\.inputs/)

    const byName = new Map(rows.map((r) => [r.name, r]))
    // consumed field present on the blackboard = matched
    expect(byName.get('segments')).toMatchObject({ state: 'matched', checked: true })
    // available upstream but not consumed
    expect(byName.get('chapters')).toMatchObject({ state: 'available', checked: false })
    // runtime_config-backed declarations are NOT blackboard gaps → never "missing"
    expect(byName.has('style_guide')).toBe(false)
  })

  it('flags graph inputs with no source as missing (Input pseudo-node / GRAPH.md)', () => {
    // GRAPH.md io.inputs = {chapters, project_id}, neither has runtime_config backing ->
    // both are declared graph inputs with no wired source → missing.
    const rows = reconcileInputFields(reconDetail(), '')
    expect(rows.every((r) => r.state === 'missing')).toBe(true)
    expect(rows.map((r) => r.name).sort()).toEqual(['chapters', 'project_id'])
    expect(rows[0].reason).toMatch(/graph input/)
  })

  it('does not flag a graph input already backed by a runtime_config import', () => {
    const withFile = `---
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
    required: [x]
    properties:
      x: {type: object}
phases: [fetch]
---
<phase depends_on="input" output>fetch</phase>
`
    const detail = { id: 'd', graph_topology: [{ id: 'fetch', depends_on: ['input'] }], files: { 'GRAPH.md': withFile } } as unknown as SkillDetail
    expect(reconcileInputFields(detail, '', [
      { field: 'chapters', type: 'array', dir: 'import_files/ch', pattern: 'c_{n}.json' },
    ])).toEqual([])
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
        { path: 'segments', type: 'array', checked: true },
        { path: 'project_id', type: 'string', checked: true },
        { path: 'chapters', type: 'array', checked: false },
      ],
      files: [
        {
          field: 'style_guide',
          type: 'object',
          path: 'import_files/report/ref/style.json',
        },
        {
          field: 'chapters_batch',
          type: 'array',
          dir: 'import_files/report/abc_segmentation',
          pattern: 'chapter_{n}_latest_*.json',
          numbers: [1, 2, 7],
        },
      ],
    })

    expect(next).toContain('project_id')
    expect(next).not.toMatch(/chapters:\s*\{?type: array\}?\s*$/m)
    expect(next).not.toContain('source: file')
    expect(next).not.toContain('dir: import_files/report/abc_segmentation')
    expect(next).not.toContain("pattern: chapter_{n}_latest_*.json")
    expect(next).toContain('style_guide')
    expect(next).toContain('chapters_batch')
    expect(next).toContain('<action>report</action>')
    const required = next.match(/required:\n(?:\s+- .+\n)+/)?.[0] ?? next
    expect(required).toContain('segments')
  })
})

describe('runtimeFileFieldsInImportScope', () => {
  const runtimeConfig = {
    schema_version: 'studio.runtime_config.v1',
    inputs: {
      import_root: 'import_files',
      manifest: {
        root: [
          {
            kind: 'dir',
            name: 'material',
            entries: [
              {
                kind: 'file',
                name: 'source.json',
                path: 'import_files/material/source.json',
                fields: [{ name: 'root_file', type: 'object' }],
              },
            ],
          },
          {
            kind: 'batch',
            name: 'chapter_{n}.json',
            stem: 'chapter',
            dir: 'import_files/chapter_batch',
            pattern: 'chapter_{n}.json',
            numbers: [1, 2],
          },
        ],
        phases: {
          segment: [
            {
              kind: 'file',
              name: 'source.json',
              path: 'import_files/.phase/segment/material/source.json',
              fields: [{ name: 'segment_file', type: 'object' }],
            },
          ],
        },
      },
      root: {},
      phases: {},
    },
    artifacts: [],
  } satisfies RuntimeConfig

  it('reads root import_files declarations for graph/input scope', () => {
    expect(runtimeFileFieldsInImportScope(runtimeConfig, null).map((decl) => decl.field)).toEqual([
      'root_file',
      'chapter',
    ])
  })

  it('reads only the selected .phase node scope for phase imports', () => {
    expect(runtimeFileFieldsInImportScope(runtimeConfig, 'segment').map((decl) => decl.field)).toEqual([
      'segment_file',
    ])
  })
})

describe('nested addressing (chapter.aa_number, PM 2026-07-03)', () => {
  // GRAPH.md io.inputs.chapter is an object with a nested aa_number; phase `seg`
  // consumes chapter.aa_number and produces a nested segmentation_result.
  const NESTED_GRAPH = `---
schema_version: "v0.3.0"
name: nested
io:
  inputs:
    type: object
    required: [chapter]
    properties:
      chapter:
        type: object
        properties:
          aa_number: {type: integer}
          title: {type: string}
  outputs:
    type: object
    required: [segmentation_result]
    properties:
      segmentation_result: {type: object}
phases: [seg]
---
<phase depends_on="input" output>seg</phase>
`
  const SEG_MD = `---
io:
  inputs:
    type: object
    required: [chapter]
    properties:
      chapter:
        type: object
        required: [aa_number]
        properties:
          aa_number: {type: integer}
  outputs:
    type: object
    required: [segmentation_result]
    properties:
      segmentation_result:
        type: object
        properties:
          bb_number: {type: integer}
actions: [seg]
---
<action>seg</action>
`
  function nestedDetail(): SkillDetail {
    return {
      id: 'nested',
      graph_topology: [{ id: 'seg', depends_on: ['input'] }],
      files: { 'GRAPH.md': NESTED_GRAPH, 'phases/seg/LOGIC.md': SEG_MD },
    } as unknown as SkillDetail
  }

  it('blackboardAtNode expands nested object sub-fields as checkable rows', () => {
    const rows = blackboardAtNode(nestedDetail(), 'seg')
    const byPath = new Map(rows.map((r) => [r.path, r]))
    // parent object + its nested leaves are all addressable rows
    expect(byPath.get('chapter')).toMatchObject({ depth: 0, hasChildren: true, from: 'input' })
    // seg declares required chapter.aa_number → that nested path is checked
    expect(byPath.get('chapter.aa_number')).toMatchObject({ depth: 1, checked: true })
    // chapter.title is on the blackboard but not consumed → present, unchecked
    expect(byPath.get('chapter.title')).toMatchObject({ depth: 1, checked: false })
  })

  it('blackboardAtOutput expands nested output object sub-fields for display', () => {
    const rows = blackboardAtOutput(nestedDetail())
    const paths = rows.map((r) => r.path)
    expect(paths).toContain('segmentation_result')
    expect(paths).toContain('segmentation_result.bb_number')
  })

  it('applyIoInputChecks writes a nested io.inputs from a checked sub-path', () => {
    const next = applyIoInputChecks(SEG_MD, {
      blackboard: [
        { path: 'chapter', type: 'object', checked: false },
        { path: 'chapter.aa_number', type: 'integer', checked: true },
        { path: 'chapter.title', type: 'string', checked: false },
      ],
      files: [],
    })
    const fm = parseFrontmatterYaml(next)
    const chapter = fm.io.inputs.properties.chapter
    expect(chapter.type).toBe('object')
    expect(chapter.required).toEqual(['aa_number'])
    expect(chapter.properties?.aa_number).toMatchObject({ type: 'integer' })
    // unchecked title must NOT be written back
    expect(chapter.properties?.title).toBeUndefined()
    // chapter itself is required at the top level (parent of a required sub-path)
    expect(fm.io.inputs.required).toContain('chapter')
  })
})

describe('runtime artifacts manifest', () => {
  it('reads artifact rows from runtime_config', () => {
    const rows = runtimeArtifactsOf({
      schema_version: 'studio.runtime_config.v1',
      inputs: {
        import_root: 'import_files',
        manifest: { root: [], phases: {} },
        root: {},
        phases: {},
      },
      artifacts: [
        { stem: 'story_framework', mode: 'single', fields: ['story_framework'] },
        { stem: 'abc_segmentation', mode: 'per-item', fields: ['segments'] },
      ],
    })
    expect(rows).toHaveLength(2)
    expect(rows[1]).toMatchObject({ stem: 'abc_segmentation', mode: 'per-item' })
  })
})

describe('declaredInputFieldNames', () => {
  it('returns the declared io.inputs top-level field names (auto-match targets)', () => {
    expect(declaredInputFieldNames(GRAPH_MD)).toEqual(['chapters', 'project_id'])
    expect(declaredInputFieldNames(FETCH_MD)).toEqual(['chapters'])
  })

  it('returns [] when the document declares no io.inputs', () => {
    expect(declaredInputFieldNames(undefined)).toEqual([])
    expect(declaredInputFieldNames('---\nio:\n  outputs:\n    type: object\n---\n')).toEqual([])
  })
})
