import { renderToStaticMarkup } from 'react-dom/server'
import type { ComponentProps } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { NodePropertiesPanel } from './NodePropertiesPanel'

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: ComponentProps<'button'>) => <button {...props}>{children}</button>,
}))

describe('NodePropertiesPanel', () => {
  it('renders phase metadata', () => {
    const html = renderToStaticMarkup(
      <NodePropertiesPanel
        onClose={() => undefined}
        node={{
          id: 'setup',
          label: 'setup',
          kind: 'phase',
          modeLabel: 'LOGIC',
          dependsOn: ['input'],
          role: 'Planner',
          tools: ['search'],
          filePath: 'phases/setup/LOGIC.md',
        }}
      />,
    )

    expect(html).toContain('Phase Properties')
    expect(html).toContain('setup')
    expect(html).toContain('LOGIC')
    expect(html).toContain('phases/setup/LOGIC.md')
  })

  it('renders input and output schema fields', () => {
    const inputHtml = renderToStaticMarkup(
      <NodePropertiesPanel
        onClose={() => undefined}
        node={{
          id: '__global_input__',
          label: 'Input',
          kind: 'input',
          filePath: 'io/inputs.json',
          fields: [{ name: 'topic', type: 'string' }],
        }}
      />,
    )
    const outputHtml = renderToStaticMarkup(
      <NodePropertiesPanel
        onClose={() => undefined}
        node={{
          id: '__global_output__',
          label: 'Output',
          kind: 'output',
          filePath: 'io/outputs.json',
          fields: [{ name: 'report', type: 'object' }],
        }}
      />,
    )

    expect(inputHtml).toContain('Input Schema')
    expect(inputHtml).toContain('topic')
    expect(outputHtml).toContain('Output Schema')
    expect(outputHtml).toContain('report')
  })
})
