import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { PropertiesPanel } from './Panels'

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
})
