import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { PropertiesPanel, subagentSkillFilePath } from './Panels'

describe('PropertiesPanel', () => {
  it('renders an empty state without a selected node', () => {
    const html = renderToStaticMarkup(<PropertiesPanel selectedNode={null} />)

    expect(html).toContain('Select a node to inspect')
  })

  it('renders selected phase metadata in the sidebar panel', () => {
    const html = renderToStaticMarkup(
      <PropertiesPanel
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
    expect(html).toContain('input')
    expect(html).toContain('prepare')
    expect(html).toContain('phases/setup/LOGIC.md')
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
