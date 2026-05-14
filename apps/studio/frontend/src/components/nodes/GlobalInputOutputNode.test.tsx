import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import { GlobalInputOutputNode, type GlobalNodeData } from './GlobalInputOutputNode'

vi.mock('@xyflow/react', () => ({
  Handle: () => <span data-testid="handle" />,
  Position: { Left: 'left', Right: 'right', Top: 'top', Bottom: 'bottom' },
}))

function renderNode(data: GlobalNodeData): string {
  const nodeType = data.type === 'global-input' ? 'globalInput' : 'globalOutput'

  return renderToStaticMarkup(
    <GlobalInputOutputNode
      id="global"
      type={nodeType}
      data={data}
      selected={false}
      isConnectable
      draggable={false}
      selectable
      deletable={false}
      dragging={false}
      zIndex={0}
      positionAbsoluteX={0}
      positionAbsoluteY={0}
    />,
  )
}

describe('GlobalInputOutputNode', () => {
  it('renders input fields with type badges', () => {
    const html = renderNode({
      type: 'global-input',
      schema: {
        inputs: [{ name: 'topic', source: 'runtime', type: 'string', default: null }],
        outputs: [],
      },
    })

    expect(html).toContain('Input')
    expect(html).toContain('topic')
    expect(html).toContain('string')
    expect(html).toContain('border-t-primary')
  })

  it('renders output fields with type badges', () => {
    const html = renderNode({
      type: 'global-output',
      schema: {
        inputs: [],
        outputs: [{ name: 'report', target: 'artifact', type: 'object', path: null }],
      },
    })

    expect(html).toContain('Output')
    expect(html).toContain('report')
    expect(html).toContain('object')
    expect(html).toContain('border-t-muted-foreground')
  })

  it('renders an empty state when schema has no fields', () => {
    const html = renderNode({
      type: 'global-input',
      schema: {
        inputs: [],
        outputs: [],
      },
    })

    expect(html).toContain('(no fields)')
    expect(html).toContain('aria-label="查看完整 schema"')
  })
})
