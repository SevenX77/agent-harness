import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import type { SkillDetail } from '@/api/types'
import type { SkillGraphNodeData } from '@/components/GraphCanvas'
import { PropertiesPanel } from './PropertiesPanel'

// Deprecated / FROZEN-violating frontmatter fields must never be EDITABLE in the
// Properties form (any node kind). Asserted via their rendered field labels.
// NOTE: the read-only inspection `dl` shows a "Node type" row (the file-derived
// KIND label, NOT a settable `mode:` frontmatter field) — informational only.
// It used to be labelled "Mode", which wrongly implied mode was a settable
// property; the row is now reworded to make the file-as-truth-source explicit.
const DEPRECATED_LABELS = [
  'System prompt',
  'Exit contract',
  'Python callable',
  'Target skill',
  'Max retries',
  'Max nudges',
]

function baseData(overrides: Partial<SkillGraphNodeData>): SkillGraphNodeData {
  return {
    skillId: 'demo',
    label: 'phase',
    mode: 'logic',
    status: 'idle',
    dependsOn: [],
    ...overrides,
  }
}

function renderPanel(args: { id: string; data: SkillGraphNodeData; filePath: string; content: string }): string {
  const skillDetail = { files: { [args.filePath]: args.content } } as unknown as SkillDetail
  return renderToStaticMarkup(
    <PropertiesPanel
      skillId="demo"
      skillDetail={skillDetail}
      selectedNode={{ id: args.id, data: args.data }}
    />,
  )
}

describe('PropertiesPanel — per-kind whitelist form (R3)', () => {
  it('agent node shows only llm_role / tools / subagents, never deprecated fields', () => {
    const html = renderPanel({
      id: 'review',
      data: baseData({ mode: 'llm', filePath: 'phases/review/SKILL.md' }),
      filePath: 'phases/review/SKILL.md',
      content: ['---', 'name: review', 'llm_role: reviewer', '---', '<role>r</role>'].join('\n'),
    })

    expect(html).toContain('LLM role')
    expect(html).toContain('Tools')
    expect(html).toContain('Subagents')
    // No logic/subgraph-only editor controls.
    expect(html).not.toContain('Actions')
    expect(html).not.toContain('>Path<')
    for (const label of DEPRECATED_LABELS) {
      expect(html).not.toContain(`>${label}<`)
    }
  })

  it('logic node shows only actions / validator, never deprecated fields', () => {
    const html = renderPanel({
      id: 'normalize',
      data: baseData({ mode: 'logic', filePath: 'phases/normalize/LOGIC.md' }),
      filePath: 'phases/normalize/LOGIC.md',
      content: ['---', 'name: normalize', 'actions:', '  - strip_noise', '---', 'Body'].join('\n'),
    })

    expect(html).toContain('Actions')
    expect(html).toContain('Validator')
    expect(html).not.toContain('LLM role')
    expect(html).not.toContain('Subagents')
    expect(html).not.toContain('>Path<')
    for (const label of DEPRECATED_LABELS) {
      expect(html).not.toContain(`>${label}<`)
    }
  })

  it('subgraph node shows only path / validator, never deprecated fields', () => {
    const html = renderPanel({
      id: 'child',
      data: baseData({ mode: 'subgraph', subgraphPath: '/abs/child', filePath: 'phases/child/SUBGRAPH.md' }),
      filePath: 'phases/child/SUBGRAPH.md',
      content: ['---', 'name: child', 'path: /abs/child', '---', 'Body'].join('\n'),
    })

    expect(html).toContain('>Path<')
    expect(html).toContain('Validator')
    expect(html).not.toContain('LLM role')
    expect(html).not.toContain('Actions')
    expect(html).not.toContain('Subagents')
    for (const label of DEPRECATED_LABELS) {
      expect(html).not.toContain(`>${label}<`)
    }
  })

  it('subgraph node surfaces legacy target_skill as migration-needed instead of editable target_skill', () => {
    const html = renderPanel({
      id: 'child',
      data: baseData({ mode: 'subgraph', filePath: 'phases/child/SUBGRAPH.md' }),
      filePath: 'phases/child/SUBGRAPH.md',
      content: ['---', 'name: child', 'target_skill: legacy.registry.child', '---', 'Body'].join('\n'),
    })

    expect(html).toContain('Legacy child reference')
    expect(html).toContain('legacy.registry.child')
    expect(html).toContain('absolute path')
    expect(html).not.toContain('Target skill')
  })
})

describe('PropertiesPanel — read-only node type row (n2-properties #17)', () => {
  it('shows a file-derived "Node type" row, not a misleading "Mode" row', () => {
    const html = renderPanel({
      id: 'review',
      data: baseData({ mode: 'llm', filePath: 'phases/review/SKILL.md' }),
      filePath: 'phases/review/SKILL.md',
      content: ['---', 'name: review', 'llm_role: reviewer', '---', '<role>r</role>'].join('\n'),
    })

    // The old read-only inspection row was labelled "Mode" (implying a settable
    // property). It is reworded to "Node type" with a file-as-truth-source hint.
    expect(html).not.toContain('>Mode<')
    expect(html).toContain('>Node type<')
    expect(html).toContain('SKILL/LOGIC/SUBGRAPH.md')
    expect(html).toContain('not editable')
  })

  it('keeps the type row file-derived for a logic node too', () => {
    const html = renderPanel({
      id: 'normalize',
      data: baseData({ mode: 'logic', filePath: 'phases/normalize/LOGIC.md' }),
      filePath: 'phases/normalize/LOGIC.md',
      content: ['---', 'name: normalize', 'actions:', '  - strip_noise', '---', 'Body'].join('\n'),
    })

    expect(html).not.toContain('>Mode<')
    expect(html).toContain('>Node type<')
  })
})

describe('PropertiesPanel — node role Test control (R23)', () => {
  it('agent node renders a Test button next to the LLM role field', () => {
    const html = renderPanel({
      id: 'review',
      data: baseData({ mode: 'llm', filePath: 'phases/review/SKILL.md' }),
      filePath: 'phases/review/SKILL.md',
      content: ['---', 'name: review', 'llm_role: reviewer', '---', '<role>r</role>'].join('\n'),
    })

    expect(html).toContain('LLM role')
    expect(html).toContain('>Test<')
  })

  it('logic node has no role Test control', () => {
    const html = renderPanel({
      id: 'normalize',
      data: baseData({ mode: 'logic', filePath: 'phases/normalize/LOGIC.md' }),
      filePath: 'phases/normalize/LOGIC.md',
      content: ['---', 'name: normalize', 'actions:', '  - strip_noise', '---', 'Body'].join('\n'),
    })

    expect(html).not.toContain('>Test<')
  })

  it('subgraph node has no role Test control', () => {
    const html = renderPanel({
      id: 'child',
      data: baseData({ mode: 'subgraph', subgraphPath: '/abs/child', filePath: 'phases/child/SUBGRAPH.md' }),
      filePath: 'phases/child/SUBGRAPH.md',
      content: ['---', 'name: child', 'path: /abs/child', '---', 'Body'].join('\n'),
    })

    expect(html).not.toContain('>Test<')
  })
})
