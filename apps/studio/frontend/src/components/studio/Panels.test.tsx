import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import type { SkillDetail } from '@/api/types'
import { WorkspaceProvider, type WorkspaceContextValue } from './WorkspaceContext'
import { CURRENT_SCHEMA_VERSION } from '@/config/schema'
import { AssetsPanel, PropertiesPanel, subagentSkillFilePath } from './Panels'

describe('PropertiesPanel', () => {
  it('renders an empty state without a selected node', () => {
    const html = renderToStaticMarkup(<PropertiesPanel selectedNode={null} />)

    expect(html).toContain('Select a node to inspect')
  })

  it('renders selected phase metadata in the sidebar panel', () => {
    const html = renderToStaticMarkup(
      <PropertiesPanel
        skillDetail={skillDetailWithFiles({
          'phases/setup/LOGIC.md': [
            '---',
            'name: setup',
            'mode: logic',
            '---',
            '<python_callable>',
            'prepare',
            '</python_callable>',
            '',
            'Body',
          ].join('\n'),
        })}
        selectedNode={{
          id: 'setup',
          data: {
            label: 'setup',
            mode: 'logic',
            status: 'idle',
            dependsOn: ['input'],
            role: null,
            tools: ['prepare'],
            filePath: 'phases/setup/LOGIC.md',
          },
        }}
      />,
    )

    expect(html).toContain('setup')
    expect(html).toContain('LOGIC')
    expect(html).toContain('Python callable')
    expect(html).not.toContain('System prompt')
    expect(html).toContain('input')
    expect(html).toContain('prepare')
    expect(html).toContain('phases/setup/LOGIC.md')
  })

  it('renders agent frontmatter fields for skill phase files', () => {
    const html = renderToStaticMarkup(
      <PropertiesPanel
        skillDetail={skillDetailWithFiles({
          'phases/review/SKILL.md': [
            '---',
            'name: review',
            'mode: skill',
            'tools:',
            '  - read_file',
            '---',
            '<system_prompt>',
            'Review the draft.',
            '</system_prompt>',
            '',
            '<exit_contract>',
            'Call finish_task.',
            '</exit_contract>',
            '',
            'Body',
          ].join('\n'),
        })}
        selectedNode={{
          id: 'review',
          data: {
            label: 'review',
            mode: 'skill',
            status: 'idle',
            dependsOn: [],
            role: 'reviewer',
            tools: ['read_file'],
            filePath: 'phases/review/SKILL.md',
          },
        }}
      />,
    )

    expect(html).toContain('System prompt')
    expect(html).toContain('Exit contract')
    expect(html).toContain('Tools')
    expect(html).not.toContain('Python callable')
  })

  it('renders subgraph frontmatter fields for subgraph phase files', () => {
    const html = renderToStaticMarkup(
      <PropertiesPanel
        skillDetail={skillDetailWithFiles({
          'phases/child/SUBGRAPH.md': [
            '---',
            'name: child',
            'mode: subgraph',
            'target_skill: child.skill',
            '---',
            'Body',
          ].join('\n'),
        })}
        selectedNode={{
          id: 'child',
          data: {
            label: 'child',
            mode: 'subgraph',
            status: 'idle',
            dependsOn: [],
            role: null,
            tools: [],
            filePath: 'phases/child/SUBGRAPH.md',
          },
        }}
      />,
    )

    expect(html).toContain('Target skill')
    expect(html).not.toContain('System prompt')
    expect(html).not.toContain('phase-tools')
  })

  it('disables frontmatter editing when phase YAML is invalid', () => {
    const html = renderToStaticMarkup(
      <PropertiesPanel
        skillDetail={skillDetailWithFiles({
          'phases/broken/LOGIC.md': [
            '---',
            'name: [broken',
            '---',
            'Body',
          ].join('\n'),
        })}
        selectedNode={{
          id: 'broken',
          data: {
            label: 'broken',
            mode: 'logic',
            status: 'idle',
            dependsOn: [],
            role: null,
            tools: [],
            filePath: 'phases/broken/LOGIC.md',
          },
        }}
      />,
    )

    expect(html).toContain('Frontmatter error')
    expect(html).toContain('disabled=""')
  })

  it('renders subagents in the selected phase metadata', () => {
    const html = renderToStaticMarkup(
      <PropertiesPanel
        skillId="demo-skill"
        selectedNode={{
          id: 'main',
          data: {
            label: 'main',
            mode: 'skill',
            status: 'idle',
            dependsOn: [],
            role: null,
            tools: ['read_file'],
            filePath: 'phases/main/SKILL.md',
            subagents: [
              {
                name: 'echo_expert',
                path: 'subskills/echo_expert',
                description: 'Echoes text from a child expert skill.',
              },
            ],
          },
        }}
      />,
    )

    expect(html).toContain('Subagents')
    expect(html).toContain('echo_expert')
    expect(html).toContain('Echoes text from a child expert skill.')
  })

  it('builds the onFileOpen path for subagent click navigation', () => {
    expect(subagentSkillFilePath('demo-skill', {
      name: 'echo_expert',
      path: 'subskills/echo_expert',
      description: 'Echoes text.',
    })).toBe('demo-skill/subskills/echo_expert/SKILL.md')
  })

  it('keeps subagent navigation on the onFileOpen path helper', () => {
    const source = subagentSkillFilePath.toString()

    expect(source).not.toContain('document.dispatchEvent')
    expect(source).not.toContain('addEventListener')
  })
})

describe('AssetsPanel', () => {
  it('renders real V1 skill root files and folders collapsed by default', () => {
    const html = renderAssetsPanel({
      'SKILL.md': '# Skill',
      'nodes/foo.md': '# Foo',
      'script/bar.py': 'print("bar")',
    })

    expect(html).toContain('SKILL.md')
    expect(html).toContain('nodes')
    expect(html).toContain('script')
    expect(html).not.toContain('foo.md')
    expect(html).not.toContain('bar.py')
    expect(html).not.toContain('GRAPH.md')
  })

  it('keeps nested trees collapsed at the root folder', () => {
    const html = renderAssetsPanel({
      'data/examples/fixtures/case.json': '{}',
    })

    expect(html).toContain('data')
    expect(html).not.toContain('examples')
    expect(html).not.toContain('fixtures')
    expect(html).not.toContain('case.json')
  })

  it('renders an empty file list without crashing', () => {
    const html = renderAssetsPanel({})

    expect(html).toContain('Skill Files')
    expect(html).not.toContain('GRAPH.md')
    expect(html).not.toContain('SKILL.md')
  })
})

function renderAssetsPanel(files: Record<string, string>): string {
  return renderToStaticMarkup(
    <WorkspaceProvider value={workspaceContextStub}>
      <AssetsPanel skillDetail={skillDetailWithFiles(files)} selectedNode={null} />
    </WorkspaceProvider>,
  )
}

function skillDetailWithFiles(files: Record<string, string>): SkillDetail {
  return {
    manifest: {
      schema_version: CURRENT_SCHEMA_VERSION,
      name: 'story-deconstruction',
      description: '(broken: manifest invalid)',
      io: {
        inputs: { type: 'object', properties: {} },
        outputs: { type: 'object', properties: {} },
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
  }
}

const workspaceContextStub: WorkspaceContextValue = {
  currentSkillId: 'story-deconstruction',
  navStack: [],
  activeFiles: {},
  activeFileDetails: {},
  splitMode: false,
  onFileOpen: () => undefined,
  openSplitEditor: () => undefined,
  closeFile: () => undefined,
  updateFileContent: () => undefined,
  markFileSaved: () => undefined,
  setFileInFlight: () => undefined,
  onSaveConflict: () => undefined,
  reloadOpenFile: async () => undefined,
  pushNavSkill: () => undefined,
  popNavTo: () => undefined,
}
