import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import type { SkillDetail } from '@/api/types'
import type { SkillGraphNodeData } from '@/components/GraphCanvas'
import { PropertiesPanel } from './PropertiesPanel'

// Deprecated / FROZEN-violating frontmatter fields must never be EDITABLE in the
// Properties form (any node kind). Asserted via their rendered field labels.
// NOTE: the read-only inspection `dl` still shows a "Mode" row (the node KIND
// label, not a `mode:` frontmatter field) — that is informational, not an
// editor, so "Mode" is intentionally not in this deprecated-editor list.
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
