import { describe, expect, it } from 'vitest'
import type { RuntimeConfig, SkillDetail } from '@/api/types'
import { staticEdgeInference } from './edge-static-inference'

// Topology: input -> fetch -> enrich -> report, with `draft` produced by both
// fetch and enrich (sequential overwrite: nearest ancestor wins), and report
// consuming `summary` plus a runtime_config file input. Field truth is
// declared in the FILES' frontmatter (the authoritative source); graph_topology
// carries only ids + depends_on — its io_fields projection is deliberately
// absent here because it degrades to empty on compile errors.
const graphMd = [
  '---',
  'io:',
  '  inputs:',
  '    type: object',
  '    properties:',
  '      topic: {type: string}',
  '      draft: {type: string}',
  '  outputs:',
  '    type: object',
  '    properties:',
  '      report: {type: string}',
  '---',
  '<phase depends_on="input">fetch</phase>',
].join('\n')

const fetchMd = [
  '---',
  'io:',
  '  inputs:',
  '    type: object',
  '    properties:',
  '      topic: {type: string}',
  '  outputs:',
  '    type: object',
  '    properties:',
  '      articles: {type: array}',
  '      draft: {type: string}',
  '---',
  'body',
].join('\n')

const enrichMd = [
  '---',
  'io:',
  '  inputs:',
  '    type: object',
  '    properties:',
  '      articles: {type: array}',
  '  outputs:',
  '    type: object',
  '    properties:',
  '      summary: {type: string}',
  '      draft: {type: string}',
  '---',
  'body',
].join('\n')

const reportMd = [
  '---',
  'io:',
  '  inputs:',
  '    type: object',
  '    properties:',
  '      summary: {type: string}',
  '      style_guide: {type: string}',
  '  outputs:',
  '    type: object',
  '    properties:',
  '      report: {type: string}',
  '---',
  '<role>r</role>',
].join('\n')

function detail(): SkillDetail {
  return {
    files: {
      'GRAPH.md': graphMd,
      'phases/fetch/LOGIC.md': fetchMd,
      'phases/enrich/LOGIC.md': enrichMd,
      'phases/report/SKILL.md': reportMd,
    },
    graph_topology: [
      { id: 'fetch', src: 'phases/fetch', depends_on: ['input'], mode: 'logic' },
      { id: 'enrich', src: 'phases/enrich', depends_on: ['fetch'], mode: 'logic' },
      { id: 'report', src: 'phases/report', depends_on: ['enrich'], mode: 'agent' },
    ],
  } as unknown as SkillDetail
}

function fieldMap(result: NonNullable<ReturnType<typeof staticEdgeInference>>) {
  return new Map(result.fields.map((field) => [field.name, field]))
}

function runtimeConfig(): RuntimeConfig {
  return {
    schema_version: 'studio.runtime_config.v2',
    inputs: {
      import_root: 'import_files',
      manifest: {
        root: [],
        phases: {
          report: [
            {
              kind: 'file',
              name: 'style.md',
              path: 'import_files/.phase/report/references/style.md',
              fields: [{ name: 'style_guide', type: 'string' }],
            },
          ],
        },
      },
      active: { root: {}, phases: {} },
      removed: { root: [], phases: {} },
    },
    artifacts: [],
  }
}

describe('staticEdgeInference', () => {
  it('returns root inputs only for the entry edge', () => {
    const result = staticEdgeInference(detail(), '__global_input__', 'fetch')
    expect(result).not.toBeNull()
    const fields = fieldMap(result!)
    expect(fields.get('topic')).toMatchObject({ from: 'input', consumed_by_target: true })
    expect(fields.get('draft')).toMatchObject({ from: 'input', consumed_by_target: false })
    expect(fields.has('articles')).toBe(false)
  })

  it('accumulates ancestor outputs along the chain, nearest ancestor winning on overwrite', () => {
    const result = staticEdgeInference(detail(), 'enrich', 'report')
    expect(result).not.toBeNull()
    const fields = fieldMap(result!)
    // Root inputs are still on the blackboard.
    expect(fields.get('topic')).toMatchObject({ from: 'input' })
    // fetch + enrich outputs accumulated.
    expect(fields.get('articles')).toMatchObject({ from: 'fetch' })
    expect(fields.get('summary')).toMatchObject({ from: 'enrich', consumed_by_target: true })
    // Both fetch and enrich output `draft` — the nearest ancestor (enrich) wins.
    expect(fields.get('draft')).toMatchObject({ from: 'enrich' })
  })

  it('includes the target runtime_config imports as via_file fields', () => {
    const result = staticEdgeInference(detail(), 'enrich', 'report', runtimeConfig())
    const fields = fieldMap(result!)
    expect(fields.get('style_guide')).toMatchObject({
      via_file: true,
      from: 'import_files/.phase/report/references/style.md',
      consumed_by_target: true,
    })
  })

  it('covers the terminal edge into the Output pseudo-node (source outputs included, root outputs consumed)', () => {
    const result = staticEdgeInference(detail(), 'report', '__global_output__')
    expect(result).not.toBeNull()
    const fields = fieldMap(result!)
    // The source phase's own outputs are on the blackboard at this dot.
    expect(fields.get('report')).toMatchObject({ from: 'report', consumed_by_target: true })
    expect(fields.get('summary')).toMatchObject({ from: 'enrich', consumed_by_target: false })
    expect(fields.get('topic')).toMatchObject({ from: 'input' })
  })

  it('returns null for unknown targets or empty topology', () => {
    expect(staticEdgeInference(detail(), 'enrich', 'nope')).toBeNull()
    expect(staticEdgeInference({ graph_topology: [] } as unknown as SkillDetail, 'a', 'b')).toBeNull()
    expect(staticEdgeInference(undefined, 'a', 'b')).toBeNull()
  })

  it('marks the result as a static inference for the dot panel to branch on', () => {
    const result = staticEdgeInference(detail(), '__global_input__', 'fetch')
    expect(result?.kind).toBe('static_inference')
    expect(result?.source).toBe('__global_input__')
    expect(result?.target).toBe('fetch')
  })
})
