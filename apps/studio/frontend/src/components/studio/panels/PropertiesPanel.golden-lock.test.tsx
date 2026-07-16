import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import type { SkillDetail } from '@/api/types'
import type { SkillGraphNodeData } from '@/components/GraphCanvas'
import { PropertiesPanel } from './PropertiesPanel'

// Design lock: golden lives in the I/O output region / editor diff / TracePanel —
// NEVER in the Properties panel (PM 2026-06-04, golden-eval mvp1-alignment F5;
// the per-node promote entry that drifted in was removed by PM decision 2026-07-15).

function nodeData(overrides: Partial<SkillGraphNodeData> = {}): SkillGraphNodeData {
  return {
    skillId: 'demo',
    label: 'segment',
    mode: 'agent',
    status: 'success',
    dependsOn: ['input'],
    filePath: 'phases/segment/SKILL.md',
    ...overrides,
  }
}

function skillDetail(): SkillDetail {
  return {
    files: {
      'phases/segment/SKILL.md': ['---', 'name: segment', '---', 'Body'].join('\n'),
    },
  } as unknown as SkillDetail
}

describe('PropertiesPanel golden design lock', () => {
  it('renders no golden promote entry for an agent node without golden', () => {
    const html = renderToStaticMarkup(
      <PropertiesPanel
        skillId="demo"
        skillDetail={skillDetail()}
        selectedNode={{ id: 'segment', data: nodeData() }}
        runId="run-123"
      />,
    )

    expect(html).not.toContain('Promote to golden')
    expect(html).not.toContain('No golden for this node yet')
  })

  it('renders no golden captured badge for an agent node with golden', () => {
    const html = renderToStaticMarkup(
      <PropertiesPanel
        skillId="demo"
        skillDetail={skillDetail()}
        selectedNode={{ id: 'segment', data: nodeData({ goldenState: 'has-golden' }) }}
        runId="run-123"
      />,
    )

    expect(html).not.toContain('Golden captured for this node')
  })
})
