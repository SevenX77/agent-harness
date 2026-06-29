import * as ReactFlow from '@xyflow/react'
import type { Edge, EdgeProps } from '@xyflow/react'
import type { ContextEdgeData } from './ContextEdge'

type SubgraphBridgeEdgeModel = Edge<ContextEdgeData, 'subgraphBridge'>

interface Point {
  x: number
  y: number
}

function edgeCoordinate(value: number): string {
  const rounded = Math.round(value * 1000) / 1000
  return Object.is(rounded, -0) ? '0' : String(rounded)
}

export function subgraphBridgePoints({
  sourceX,
  sourceY,
  targetX,
  targetY,
}: {
  sourceX: number
  sourceY: number
  targetX: number
  targetY: number
}): Point[] {
  if (Math.abs(sourceY - targetY) < 0.5) {
    return [
      { x: sourceX, y: sourceY },
      { x: targetX, y: targetY },
    ]
  }
  const midX = sourceX + (targetX - sourceX) / 2
  return [
    { x: sourceX, y: sourceY },
    { x: midX, y: sourceY },
    { x: midX, y: targetY },
    { x: targetX, y: targetY },
  ]
}

function pathFromPoints(points: Point[]): string {
  const [first, ...rest] = points
  if (!first) return ''
  return [
    `M ${edgeCoordinate(first.x)} ${edgeCoordinate(first.y)}`,
    ...rest.map((point) => `L ${edgeCoordinate(point.x)} ${edgeCoordinate(point.y)}`),
  ].join(' ')
}

export function subgraphBridgePath(params: Parameters<typeof subgraphBridgePoints>[0]): string {
  return pathFromPoints(subgraphBridgePoints(params))
}

const SUBGRAPH_BRIDGE_DASH = 4

function polylineLength(points: Point[]): number {
  let length = 0
  for (let index = 1; index < points.length; index += 1) {
    length += Math.hypot(points[index].x - points[index - 1].x, points[index].y - points[index - 1].y)
  }
  return length
}

/**
 * Dash pattern (dash == gap == d) fitted to the polyline's EXACT length so the
 * line begins with a full dash at the source (toggle button edge) and ends with
 * a full dash at the target (header edge). With k dashes and k-1 equal gaps,
 * (2k-1)·d = length, and we pick k so d stays ≈ SUBGRAPH_BRIDGE_DASH. A plain
 * static `stroke-dasharray: 4 4` can't do this: it leaves a truncated ~2px
 * fragment whenever the length isn't a clean multiple of the period.
 */
export function subgraphBridgeDashArray(params: Parameters<typeof subgraphBridgePoints>[0]): string {
  const length = polylineLength(subgraphBridgePoints(params))
  if (length <= 0) return '0'
  const k = Math.max(1, Math.round((length / SUBGRAPH_BRIDGE_DASH + 1) / 2))
  const d = length / (2 * k - 1)
  return `${edgeCoordinate(d)} ${edgeCoordinate(d)}`
}

export function SubgraphBridgeEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  style,
}: EdgeProps<SubgraphBridgeEdgeModel>) {
  // One continuous orthogonal path from the parent toggle to the subgraph header.
  // The dash rhythm is fitted to the path length (subgraphBridgeDashArray) so both
  // ends land on a FULL dash — a full dash leaves the button edge and a full dash
  // arrives at the header, with no truncated 2px fragment and no leading gap.
  const params = { sourceX, sourceY, targetX, targetY }
  const path = subgraphBridgePath(params)
  const strokeDasharray = subgraphBridgeDashArray(params)
  return (
    <ReactFlow.BaseEdge
      id={id}
      path={path}
      className="subgraph-bridge-edge"
      style={{
        pointerEvents: 'none',
        ...style,
        strokeDasharray,
      }}
    />
  )
}
