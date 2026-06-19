import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import type { ResumeValidityResponse, SkillDetail } from '@/api/types'
import type { SkillGraphNodeData } from '@/components/GraphCanvas'
import { PropertiesPanel } from './PropertiesPanel'

function nodeData(overrides: Partial<SkillGraphNodeData> = {}): SkillGraphNodeData {
  return {
    skillId: 'demo',
    label: 'review',
    mode: 'logic',
    status: 'error',
    dependsOn: ['draft'],
    filePath: 'phases/review/LOGIC.md',
    ...overrides,
  }
}

function validity(overrides: Partial<ResumeValidityResponse> = {}): ResumeValidityResponse {
  return {
    run_id: 'run-123',
    resume_allowed: false,
    reason: 'dirty_upstream',
    checkpoint_id: 'checkpoint-review',
    checkpoint_ns: 'agent:review',
    resume_from_node_id: 'review',
    resume_to_node_id: null,
    dirty_fields: ['execution_fingerprint'],
    snapshot_content_hash: `sha256:${'1'.repeat(64)}`,
    current_content_hash: `sha256:${'2'.repeat(64)}`,
    snapshot_execution_fingerprint: `sha256:${'3'.repeat(64)}`,
    current_execution_fingerprint: `sha256:${'4'.repeat(64)}`,
    ...overrides,
  }
}

function skillDetail(): SkillDetail {
  return {
    files: {
      'phases/review/LOGIC.md': ['---', 'name: review', 'actions:', '  - check', '---', 'Body'].join('\n'),
    },
  } as unknown as SkillDetail
}

describe('PropertiesPanel resume validity debug bar', () => {
  it('disables node Resume and explains dirty upstream validity failures', () => {
    const html = renderToStaticMarkup(
      <PropertiesPanel
        skillId="demo"
        skillDetail={skillDetail()}
        selectedNode={{ id: 'review', data: nodeData() }}
        runId="run-123"
        selectedNodeStatus="error"
        resumeValidity={validity()}
        onResumeNode={() => undefined}
      />,
    )

    expect(html).toContain('Checkpoint validity')
    expect(html).toContain('dirty_upstream')
    expect(html).toContain('execution_fingerprint')
    expect(html).toContain('Resume disabled')
    const resumeSlice = html.slice(html.indexOf('Resume disabled') - 240, html.indexOf('Resume disabled') + 240)
    expect(resumeSlice).toContain('disabled=""')
  })

  it('enables node Resume when checkpoint validity allows downstream resume', () => {
    const html = renderToStaticMarkup(
      <PropertiesPanel
        skillId="demo"
        skillDetail={skillDetail()}
        selectedNode={{ id: 'review', data: nodeData() }}
        runId="run-123"
        selectedNodeStatus="error"
        resumeValidity={validity({
          resume_allowed: true,
          reason: 'ok',
          dirty_fields: [],
          current_content_hash: `sha256:${'1'.repeat(64)}`,
          current_execution_fingerprint: `sha256:${'3'.repeat(64)}`,
        })}
        onResumeNode={() => undefined}
      />,
    )

    expect(html).toContain('Checkpoint validity')
    expect(html).toContain('Resume node')
    const resumeSlice = html.slice(html.indexOf('Resume node') - 240, html.indexOf('Resume node') + 240)
    expect(resumeSlice).not.toContain('disabled=""')
  })
})
