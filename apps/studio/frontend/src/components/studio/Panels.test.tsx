// @vitest-environment jsdom
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import type { SkillDetail } from '@/api/types'
import { WorkspaceProvider, type WorkspaceContextValue } from './WorkspaceContext'
import { CURRENT_SCHEMA_VERSION } from '@/config/schema'
import { AssetsPanel, PropertiesPanel, subagentSkillFilePath } from './Panels'

vi.hoisted(() => {
  if (typeof window !== 'undefined' && !window.matchMedia) {
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: (query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: () => undefined,
        removeListener: () => undefined,
        addEventListener: () => undefined,
        removeEventListener: () => undefined,
        dispatchEvent: () => false,
      }),
    })
  }
})

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

describe('PropertiesPanel', () => {
  it('renders graph frontmatter fields without a selected node', () => {
    const html = renderToStaticMarkup(
      <PropertiesPanel
        skillDetail={skillDetailWithFiles({
          'GRAPH.md': [
            '---',
            'schema_version: v0.3.0',
            'name: story-deconstruction',
            'description: Builds story analysis.',
            'llm_role: analyst',
            'io:',
            '  inputs:',
            '    type: object',
            '    properties: {}',
            '  outputs:',
            '    type: object',
            '    properties: {}',
            'phases:',
            '  - setup',
            '---',
            '<phase>setup</phase>',
          ].join('\n'),
        })}
        selectedNode={null}
      />,
    )

    expect(html).toContain('GRAPH.md')
    expect(html).toContain('name')
    expect(html).toContain('story-deconstruction')
    expect(html).toContain('description')
    expect(html).toContain('Builds story analysis.')
    expect(html).toContain('llm_role')
    expect(html).toContain('id="graph-llm-role"')
    expect(html).not.toContain('Select a node to inspect')
    expect(html).not.toContain('schema_version')
    expect(html).not.toContain('phases')
    expect(html).not.toContain('id="graph-io"')
  })

  it('renders selected phase editable fields in the sidebar panel', () => {
    const html = renderToStaticMarkup(
      <PropertiesPanel
        skillDetail={skillDetailWithFiles({
          'phases/setup/LOGIC.md': [
            '---',
            'name: setup',
            'actions:',
            '  - prepare',
            '---',
            'Body',
          ].join('\n'),
        })}
        selectedNode={{
          id: 'setup',
          data: {
            skillId: 'demo',
            label:'setup',
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
    // FROZEN whitelist: a logic node edits actions + validator, never the
    // deprecated mode/python_callable/system_prompt fields.
    expect(html).toContain('actions')
    expect(html).toContain('prepare')
    expect(html).not.toContain('Python callable')
    expect(html).not.toContain('System prompt')
    expect(html).not.toContain('>Depends On<')
    expect(html).not.toContain('>input<')
    expect(html).not.toContain('>File<')
    expect(html).not.toContain('phases/setup/LOGIC.md')
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
            skillId: 'demo',
            label:'review',
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

    // FROZEN whitelist: an agent node edits llm_role + tools + subagents, never
    // the deprecated system_prompt/exit_contract/python_callable fields.
    expect(html).toContain('llm_role')
    expect(html).toContain('tools')
    expect(html).toContain('subagents')
    expect(html).not.toContain('System prompt')
    expect(html).not.toContain('Exit contract')
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
            skillId: 'demo',
            label:'child',
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

    // FROZEN whitelist: a subgraph node exposes name/path/validator/iterate, never
    // the deprecated target_skill/system_prompt fields.
    expect(html).toContain('>name<')
    expect(html).toContain('>path<')
    expect(html).toContain('>validator<')
    expect(html).toContain('>iterate<')
    expect(html).not.toContain('id="phase-io"')
    expect(html).toContain('aria-label="Reconnect path"')
    expect(html).not.toContain('Target skill')
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
            skillId: 'demo',
            label:'broken',
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

  it('does not render selected-node subagents as read-only metadata', () => {
    const html = renderToStaticMarkup(
      <PropertiesPanel
        skillId="demo-skill"
        selectedNode={{
          id: 'main',
          data: {
            skillId: 'demo',
            label:'main',
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

    expect(html).not.toContain('echo_expert')
    expect(html).not.toContain('Echoes text from a child expert skill.')
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

    expect(html).toContain('story-deconstruction')
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

  it('shows no subgraphs (no hardcoded mock) when the skill has none', () => {
    const html = renderAssetsPanel({ 'phases/step1/LOGIC.md': '---\nname: step1\n---\n' })

    // The panel must render gateway/skill facts only - never the old hardcoded
    // intent_classifier / translator_subgraph fallback.
    expect(html).not.toContain('intent_classifier')
    expect(html).not.toContain('translator_subgraph')
    expect(html).toContain('Subgraphs')
  })

  it('renders REAL subgraph membership from the topology (label + absolute path)', () => {
    const html = renderToStaticMarkup(
      <WorkspaceProvider value={workspaceContextStub}>
        <AssetsPanel
          skillDetail={{
            ...skillDetailWithFiles({}),
            graph_topology: [
              { id: 'setup', src: 'phases/setup', depends_on: [], mode: 'logic' },
              {
                id: 'translate',
                src: 'phases/translate',
                depends_on: ['setup'],
                mode: 'subgraph',
                path: '/abs/skills/translator',
              },
            ],
          }}
          selectedNode={null}
        />
      </WorkspaceProvider>,
    )

    // Real phase label + real absolute path are surfaced; resolved → "Linked".
    expect(html).toContain('translate')
    expect(html).toContain('/abs/skills/translator')
    expect(html).toContain('Linked')
    // Logic phases are not subgraph members.
    expect(html).not.toContain('phases/setup')
  })

  it('uses styled path affordances without native titles and exposes absolute root paths', () => {
    const skillRoot = '/abs/skills/story-deconstruction'
    const subgraphRoot = '/abs/skills/story-deconstruction/subgraph/text-segmentation'
    const html = renderToStaticMarkup(
      <WorkspaceProvider value={workspaceContextStub}>
        <AssetsPanel
          skillId="story-deconstruction"
          workspaceRoot={skillRoot}
          skillDetail={{
            ...skillDetailWithFiles({
              'SKILL.md': '# Skill',
              'phases/segment/SUBGRAPH.md': '---\nname: segment\npath: subgraph/text-segmentation\n---\n',
            }),
            graph_topology: [
              {
                id: 'segment',
                src: 'phases/segment',
                depends_on: [],
                mode: 'subgraph',
                path: subgraphRoot,
              },
            ],
          }}
          selectedNode={null}
        />
      </WorkspaceProvider>,
    )

    expect(html).not.toContain('title=')
    expect(html).toContain(`aria-label="story-deconstruction (${skillRoot})"`)
    expect(html).toContain(`aria-label="segment (${subgraphRoot})"`)
  })

  it('keeps each subgraph folder collapsed by default', () => {
    const html = renderToStaticMarkup(
      <WorkspaceProvider value={workspaceContextStub}>
        <AssetsPanel
          skillDetail={{
            ...skillDetailWithFiles({}),
            graph_topology: [
              {
                id: 'story_analysis',
                src: 'phases/story_analysis',
                depends_on: [],
                mode: 'subgraph',
                path: '/abs/skills/story_analysis',
              },
            ],
          }}
          selectedNode={null}
        />
      </WorkspaceProvider>,
    )

    expect(html).toContain('data-subgraph-folder="true"')
    expect(html).toContain('data-subgraph-default-expanded="false"')
    expect(html).not.toContain('data-subgraph-folder-contents="true"')
  })

  it('keeps the assets split panes constrained to the sidebar height', () => {
    const html = renderAssetsPanel({ 'phases/step1/LOGIC.md': '---\nname: step1\n---\n' })

    expect(html).toContain('data-assets-panel-stable-height="true"')
    expect(html).toContain('data-assets-split-container="true"')
    expect(html).toContain('flex h-full min-h-0 flex-col')
    expect(html).toContain('data-assets-subgraphs-drawer="true"')
    expect(html).toContain('overflow-hidden px-0 pb-2')
    expect(html).toContain('grid h-full min-h-0')
    expect(html).not.toContain('h-[calc(100vh-1.5rem)]')
    expect(html).not.toContain('px-1.5 pb-2')
    expect(html).not.toContain('calc(100vh - 5.25rem)')
  })

  it('renders section bars as visible rows and makes the subgraphs bar the collapse trigger', () => {
    const html = renderAssetsPanel({ 'phases/step1/LOGIC.md': '---\nname: step1\n---\n' })

    expect(html).toContain('data-assets-section-bar="true"')
    expect(html).toContain('bg-muted/55')
    expect(html).toContain('data-assets-section-toggle="true"')
    expect(html).toContain('aria-label="Collapse Subgraphs Files"')
    expect(html).toContain('aria-expanded="true"')
    expect(html).toContain('w-full cursor-pointer justify-between')
  })

  it('keeps only one subgraph folder expanded at a time', async () => {
    const container = document.createElement('div')
    document.body.appendChild(container)
    const root = createRoot(container)

    try {
      await act(async () => {
        root.render(
          <WorkspaceProvider value={workspaceContextStub}>
            <AssetsPanel
              skillDetail={{
                ...skillDetailWithFiles({}),
                graph_topology: [
                  {
                    id: 'segmentation',
                    src: 'phases/segmentation',
                    depends_on: [],
                    mode: 'subgraph',
                    path: '/abs/skills/segmentation',
                    level: 1,
                  } as NonNullable<SkillDetail['graph_topology']>[number],
                  {
                    id: 'event_extraction',
                    src: 'phases/event_extraction',
                    depends_on: ['segmentation'],
                    mode: 'subgraph',
                    path: '/abs/skills/event_extraction',
                    level: 2,
                  } as NonNullable<SkillDetail['graph_topology']>[number],
                ],
              }}
              selectedNode={null}
            />
          </WorkspaceProvider>,
        )
      })

      const first = container.querySelector<HTMLButtonElement>('button[aria-label="segmentation (/abs/skills/segmentation)"]')
      const second = container.querySelector<HTMLButtonElement>('button[aria-label="event_extraction (/abs/skills/event_extraction)"]')
      expect(first).not.toBeNull()
      expect(second).not.toBeNull()
      expect(container.querySelectorAll('[data-subgraph-folder-contents="true"]')).toHaveLength(0)

      await act(async () => {
        first?.click()
      })
      expect(first?.getAttribute('aria-expanded')).toBe('true')
      expect(second?.getAttribute('aria-expanded')).toBe('false')
      expect(container.querySelectorAll('[data-subgraph-folder-contents="true"]')).toHaveLength(1)

      await act(async () => {
        second?.click()
      })
      expect(first?.getAttribute('aria-expanded')).toBe('false')
      expect(second?.getAttribute('aria-expanded')).toBe('true')
      expect(container.querySelectorAll('[data-subgraph-folder-contents="true"]')).toHaveLength(1)
    } finally {
      await act(async () => {
        root.unmount()
      })
      document.body.removeChild(container)
    }
  })

  it('does not draw an extra hard border between asset sections', () => {
    const html = renderAssetsPanel({ 'phases/step1/LOGIC.md': '---\nname: step1\n---\n' })

    expect(html).not.toContain('border-y border-border/40')
    expect(html).not.toContain('bg-border/60')
  })

  it('surfaces a referenced subgraph with no path honestly as missing', () => {
    const html = renderToStaticMarkup(
      <WorkspaceProvider value={workspaceContextStub}>
        <AssetsPanel
          skillDetail={{
            ...skillDetailWithFiles({}),
            graph_topology: [
              { id: 'translate', src: 'phases/translate', depends_on: [], mode: 'subgraph', path: null },
            ],
          }}
          selectedNode={null}
        />
      </WorkspaceProvider>,
    )

    expect(html).toContain('translate')
    expect(html).toContain('Missing path')
    expect(html).toContain('unresolvable')
  })

  it('surfaces a legacy subgraph target_skill as migration-needed, not linked', () => {
    const html = renderToStaticMarkup(
      <WorkspaceProvider value={workspaceContextStub}>
        <AssetsPanel
          skillDetail={{
            ...skillDetailWithFiles({
              'phases/translate/SUBGRAPH.md': [
                '---',
                'name: translate',
                'target_skill: legacy.registry.child',
                '---',
                '',
              ].join('\n'),
            }),
            graph_topology: [
              { id: 'translate', src: 'phases/translate', depends_on: [], mode: 'subgraph', path: null },
            ],
          }}
          selectedNode={null}
        />
      </WorkspaceProvider>,
    )

    expect(html).toContain('translate')
    expect(html).toContain('Migration needed')
    expect(html).toContain('legacy.registry.child')
    expect(html).not.toContain('Linked')
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
