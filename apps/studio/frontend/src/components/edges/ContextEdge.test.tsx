import { isValidElement, type ReactElement, type ReactNode } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { Position } from '@xyflow/react'
import { describe, expect, it, vi } from 'vitest'
import { ContextEdge } from './ContextEdge'

vi.mock('@xyflow/react', () => ({
  BaseEdge: ({ id, path }: { id: string; path: string }) => <path data-edge-id={id} d={path} />,
  EdgeLabelRenderer: ({ children }: { children: ReactNode }) => <>{children}</>,
  Position: { Left: 'left', Right: 'right', Top: 'top', Bottom: 'bottom' },
  getBezierPath: vi.fn(() => ['M0,0 C50,0 50,100 100,100', 50, 50]),
}))

vi.mock('../ui/tooltip', () => ({
  Tooltip: ({ children }: { children: ReactNode }) => <>{children}</>,
  TooltipContent: ({ children }: { children: ReactNode }) => <div role="tooltip">{children}</div>,
  TooltipTrigger: ({ children }: { children: ReactNode }) => <>{children}</>,
}))

const baseProps: Parameters<typeof ContextEdge>[0] = {
  id: 'a->b',
  source: 'a',
  target: 'b',
  sourceX: 0,
  sourceY: 0,
  targetX: 100,
  targetY: 100,
  sourcePosition: Position.Right,
  targetPosition: Position.Left,
  data: {
    hasTraceData: false,
    sourcePhaseId: 'a',
    targetPhaseId: 'b',
  },
}

function findButton(node: ReactNode): ReactElement<{ onClick?: (event: { stopPropagation: () => void }) => void }> | null {
  if (!isValidElement(node)) {
    return null
  }
  const element = node as ReactElement<{ children?: ReactNode; onClick?: (event: { stopPropagation: () => void }) => void }>
  if (element.type === 'button') {
    return element
  }
  const children = element.props.children
  if (Array.isArray(children)) {
    for (const child of children) {
      const match = findButton(child)
      if (match) {
        return match
      }
    }
  }
  return findButton(children)
}

describe('ContextEdge', () => {
  it('renders a design-time edge dot button when hasTraceData is false', () => {
    const html = renderToStaticMarkup(<ContextEdge {...baseProps} />)

    expect(html).toContain('aria-label="查看连线传递数据"')
    expect(html).toContain('size-4')
    expect(html).toContain('bg-primary')
    expect(html).toContain('border-primary')
  })

  it('renders the design-time tooltip copy', () => {
    const html = renderToStaticMarkup(<ContextEdge {...baseProps} />)

    expect(html).toContain('运行后可查看传递数据')
  })

  it('clicking the design-time dot is a no-op beyond stopping propagation', () => {
    const stopPropagation = vi.fn()
    const button = findButton(ContextEdge(baseProps))

    expect(() => button?.props.onClick?.({ stopPropagation })).not.toThrow()
    expect(stopPropagation).toHaveBeenCalledOnce()
  })
})
