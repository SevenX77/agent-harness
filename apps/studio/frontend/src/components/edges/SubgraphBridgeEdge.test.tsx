import { renderToStaticMarkup } from 'react-dom/server'
import type { CSSProperties } from 'react'
import { Position } from '@xyflow/react'
import { describe, expect, it, vi } from 'vitest'
import {
  SubgraphBridgeEdge,
  subgraphBridgeDashPaths,
  subgraphBridgePath,
  subgraphBridgePathLength,
} from './SubgraphBridgeEdge'

vi.mock('@xyflow/react', () => ({
  BaseEdge: ({
    id,
    path,
    className,
    style,
  }: {
    id: string
    path: string
    className?: string
    style?: CSSProperties
  }) => (
    <path data-edge-id={id} d={path} className={className} style={style} />
  ),
  Position: { Left: 'left', Right: 'right' },
}))

const baseProps: Parameters<typeof SubgraphBridgeEdge>[0] = {
  id: 'subgraph-preview',
  source: 'parent',
  target: 'group',
  sourceX: 100,
  sourceY: 40,
  targetX: 220,
  targetY: 112,
  sourcePosition: Position.Right,
  targetPosition: Position.Left,
  data: {
    hasTraceData: false,
    sourcePhaseId: 'parent',
    targetPhaseId: 'group',
  },
}

describe('SubgraphBridgeEdge', () => {
  it('uses an orthogonal route instead of a diagonal guessed-pixel line', () => {
    expect(subgraphBridgePath({ sourceX: 100, sourceY: 40, targetX: 220, targetY: 112 }))
      .toBe('M 100 40 L 160 40 L 160 112 L 220 112')
  })

  it('renders the orthogonal bridge path through React Flow BaseEdge', () => {
    const html = renderToStaticMarkup(<SubgraphBridgeEdge {...baseProps} />)

    expect(html).toContain('d="M 100 40 L 104 40"')
    expect(html).toContain('d="M 216 112 L 220 112"')
    expect(html).toContain('subgraph-bridge-edge')
    expect(html).not.toContain('d="M 100 40 L 220 112"')
    expect(html).not.toContain('subgraph-preview-terminal')
  })

  it('builds explicit dash segments that touch both bridge endpoints', () => {
    const length = subgraphBridgePathLength({ sourceX: 100, sourceY: 40, targetX: 220, targetY: 112 })
    const paths = subgraphBridgeDashPaths({ sourceX: 100, sourceY: 40, targetX: 220, targetY: 112 })

    expect(length).toBe(192)
    expect(paths[0]).toBe('M 100 40 L 104 40')
    expect(paths.at(-1)).toBe('M 216 112 L 220 112')
  })
})
