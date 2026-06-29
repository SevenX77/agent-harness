import { renderToStaticMarkup } from 'react-dom/server'
import type { CSSProperties } from 'react'
import { Position } from '@xyflow/react'
import { describe, expect, it, vi } from 'vitest'
import {
  SubgraphBridgeEdge,
  subgraphBridgeDashArray,
  subgraphBridgePath,
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

  it('renders one continuous orthogonal path through React Flow BaseEdge', () => {
    const html = renderToStaticMarkup(<SubgraphBridgeEdge {...baseProps} />)

    // A single path carrying the whole orthogonal route — the dash rhythm comes
    // from a fitted stroke-dasharray, NOT from manually chunked sub-paths, so there
    // is no isolated dash forced onto the target endpoint.
    expect(html).toContain('d="M 100 40 L 160 40 L 160 112 L 220 112"')
    expect(html).toContain('subgraph-bridge-edge')
    expect(html).not.toContain('subgraph-preview-terminal')
  })

  it('fits a square dash rhythm so both endpoints land on a full dash', () => {
    // Polyline length for (100,40)->(220,112) is 60 + 72 + 60 = 192.
    const dash = subgraphBridgeDashArray({ sourceX: 100, sourceY: 40, targetX: 220, targetY: 112 })
    const [d, g] = dash.split(' ').map(Number)

    expect(d).toBe(g) // dash == gap (square rhythm)
    expect(d).toBeGreaterThan(3.5) // stays close to the 4px design unit
    expect(d).toBeLessThan(4.5)
    // (2k-1)*d == length => length/d is an ODD integer (modulo the 3-decimal
    // rounding of the emitted dash) => the pattern begins AND ends on a full
    // dash (dashes at both endpoints, gaps between).
    const units = 192 / d
    const nearest = Math.round(units)
    expect(Math.abs(units - nearest)).toBeLessThan(0.05)
    expect(nearest % 2).toBe(1)
  })
})
