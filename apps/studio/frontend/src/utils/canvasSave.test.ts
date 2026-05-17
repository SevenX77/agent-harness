import { describe, expect, it, vi } from 'vitest'
import { phasesFromCanvas, saveCanvasGraph } from './canvasSave'

describe('canvasSave', () => {
  it('builds serialize phases from non-position canvas topology', () => {
    const phases = phasesFromCanvas([
      { id: 'input', type: 'input', data: { label: 'Input' }, position: { x: 0, y: 0 } },
      { id: 'setup', type: 'agent', data: { label: 'setup', mode: 'logic', src: 'phases/setup' }, position: { x: 0, y: 0 } },
      { id: 'review', type: 'agent', data: { label: 'review', mode: 'llm', src: 'phases/review' }, position: { x: 0, y: 0 } },
      { id: 'output', type: 'output', data: { label: 'Output' }, position: { x: 0, y: 0 } },
    ], [
      { id: 'e-input-setup', source: 'input', target: 'setup' },
      { id: 'e-setup-review', source: 'setup', target: 'review' },
      { id: 'e-review-output', source: 'review', target: 'output' },
    ])

    expect(phases).toEqual([
      { id: 'setup', src: 'phases/setup', depends_on: [], mode: 'logic' },
      { id: 'review', src: 'phases/review', depends_on: ['setup'], mode: 'skill' },
    ])
  })

  it('serializes then writes GRAPH.md through the multi-file update binding', async () => {
    const api = {
      serializeGraph: vi.fn().mockResolvedValue({
        markdown_content: '# Graph',
        phase_count: 1,
        elapsed_ms: 1,
        current_hash: 'hash-1',
      }),
      updateSkillFiles: vi.fn().mockResolvedValue({
        manifest: { name: 'demo', type: 'graph', io: { inputs: [], outputs: [] }, phases: [], context_mapping: {} },
        graph_topology: [],
        node_schema_v21: {},
        io_schema: {},
        file_paths: {},
        files: { 'GRAPH.md': '# Graph' },
        has_golden: false,
        latest_run_metadata: null,
        lint_result: null,
      }),
    }

    await saveCanvasGraph(
      api,
      'demo',
      [{ id: 'setup', type: 'agent', data: { label: 'setup', mode: 'logic', src: 'phases/setup' }, position: { x: 0, y: 0 } }],
      [],
      { 'SKILL.md': '# Skill', 'GRAPH.md': '# Old' },
    )

    expect(api.serializeGraph).toHaveBeenCalledWith('demo', {
      phases: [{ id: 'setup', src: 'phases/setup', depends_on: [], mode: 'logic' }],
    })
    expect(api.updateSkillFiles).toHaveBeenCalledWith('demo', {
      'SKILL.md': '# Skill',
      'GRAPH.md': '# Graph',
    }, 'hash-1')
  })

  it('keeps save conflicts visible to the caller', async () => {
    const conflict = { response: { status: 409 } }
    const api = {
      serializeGraph: vi.fn().mockResolvedValue({
        markdown_content: '# Graph',
        phase_count: 1,
        elapsed_ms: 1,
        current_hash: 'hash-1',
      }),
      updateSkillFiles: vi.fn().mockRejectedValue(conflict),
    }

    await expect(saveCanvasGraph(
      api,
      'demo',
      [{ id: 'setup', type: 'agent', data: { label: 'setup', mode: 'logic', src: 'phases/setup' }, position: { x: 0, y: 0 } }],
      [],
      { 'GRAPH.md': '# Old' },
    )).rejects.toBe(conflict)
    expect(api.updateSkillFiles).toHaveBeenCalledOnce()
  })
})
