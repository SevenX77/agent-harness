import { describe, expect, it } from 'vitest'
import { CURRENT_SCHEMA_VERSION } from '@/config/schema'
import type { SkillDetail } from '@/api/types'
import { inputFiles } from './panel-files'

// MVP1 (phase-editing F3 + region input): the I/O panel reads REAL input/schema/artifact/test-input
// state from the workspace. It must NOT fabricate phantom `input/sample.json` / `input/schema.json`
// files that do not exist on disk (the MVP0 projection). When there is no real input data, it shows
// an empty state instead of a fake sample.
function skillDetailWith(files: Record<string, string>): SkillDetail {
  return {
    manifest: {
      schema_version: CURRENT_SCHEMA_VERSION,
      name: 'demo',
      description: 'Demo',
      io: {
        inputs: { type: 'object', properties: { chapter_path: { type: 'string' } } },
        outputs: { type: 'object', properties: { segments: { type: 'array' } } },
      },
      phases: [],
    },
    graph_topology: [],
    node_schema_v21: {},
    io_schema: {},
    file_paths: {},
    files,
    manifest_errors: null,
    has_golden: false,
    latest_run_metadata: null,
    lint_result: null,
  } as unknown as SkillDetail
}

describe('inputFiles (MVP1 real I/O panel)', () => {
  it('does not fabricate an input/sample.json projection with no backing file on disk', () => {
    const detail = skillDetailWith({ 'GRAPH.md': '---\nname: demo\n---\n' })
    const paths = inputFiles(detail).map((file) => file.path)

    expect(paths).not.toContain('input/sample.json')
    expect(paths).not.toContain('input/schema.json')
  })

  it('surfaces real workspace test-input files instead of a fixed sample', () => {
    const detail = skillDetailWith({
      'GRAPH.md': '---\nname: demo\n---\n',
      '.workspace/test_inputs/chapter1.json': '{"chapter_path": "/novels/ch1.txt"}',
    })
    const paths = inputFiles(detail).map((file) => file.path)

    expect(paths).toContain('.workspace/test_inputs/chapter1.json')
  })
})
