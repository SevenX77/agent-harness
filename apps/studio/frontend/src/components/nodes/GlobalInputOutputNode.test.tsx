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

function renderSelectedNode(data: GlobalNodeData): string {
  const nodeType = data.type === 'global-input' ? 'globalInput' : 'globalOutput'

  return renderToStaticMarkup(
    <GlobalInputOutputNode
      id="global"
      type={nodeType}
      data={data}
      selected
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
    expect(html).toContain('INPUT')
    expect(html).toContain('topic')
    expect(html).toContain('string')
    expect(html).toContain('cursor-pointer')
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
    expect(html).toContain('OUTPUT')
    expect(html).toContain('report')
    expect(html).toContain('object')
    expect(html).toContain('cursor-pointer')
  })

  it('omits empty state copy and schema eye button when schema has no fields', () => {
    const html = renderNode({
      type: 'global-input',
      schema: {
        inputs: [],
        outputs: [],
      },
    })

    expect(html).not.toContain('(no fields)')
    expect(html).not.toContain('aria-label="View full schema"')
  })

  it('uses the same selected ring treatment as graph nodes', () => {
    const html = renderSelectedNode({
      type: 'global-output',
      schema: {
        inputs: [],
        outputs: [],
      },
    })

    expect(html).toContain('border-primary')
    expect(html).toContain('ring-primary/30')
  })

  it('renders compile diagnostics on the boundary node badge', () => {
    const html = renderNode({
      type: 'global-input',
      schema: {
        inputs: [{ name: 'chapter', source: 'runtime', type: 'string', default: null }],
        outputs: [],
      },
      compileErrors: [
        {
          file: '.workspace/test_inputs',
          line: null,
          field: 'chapter',
          severity: 'fatal',
          message: "Graph input schema requires test input field 'chapter'",
          error_code: 'STUDIO_TEST_INPUT_MISSING',
        },
      ],
    })

    expect(html).toContain('1 compile error on this boundary')
    expect(html).toContain('chapter')
    expect(html).toContain('Graph input schema requires test input field')
  })
})
