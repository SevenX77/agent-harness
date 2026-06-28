import * as ReactFlow from '@xyflow/react'
import type { Edge, EdgeProps } from '@xyflow/react'
import type { ContextEdgeData } from './ContextEdge'

type SubgraphBridgeEdgeModel = Edge<ContextEdgeData, 'subgraphBridge'>
const SUBGRAPH_BRIDGE_DASH = 4
const SUBGRAPH_BRIDGE_GAP = 4

interface Point {
  x: number
  y: number
}

function edgeCoordinate(value: number): string {
  const rounded = Math.round(value * 1000) / 1000
  return Object.is(rounded, -0) ? '0' : String(rounded)
}

function pointsEqual(a: Point, b: Point): boolean {
  return Math.abs(a.x - b.x) < 0.001 && Math.abs(a.y - b.y) < 0.001
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

export function subgraphBridgePathLength({
  sourceX,
  sourceY,
  targetX,
  targetY,
}: {
  sourceX: number
  sourceY: number
  targetX: number
  targetY: number
}): number {
  return polylineLength(subgraphBridgePoints({ sourceX, sourceY, targetX, targetY }))
}

function distance(a: Point, b: Point): number {
  return Math.abs(a.x - b.x) + Math.abs(a.y - b.y)
}

function polylineLength(points: Point[]): number {
  let length = 0
  for (let index = 1; index < points.length; index += 1) {
    length += distance(points[index - 1], points[index])
  }
  return length
}

function pointOnSegment(start: Point, end: Point, distanceFromStart: number): Point {
  const length = distance(start, end)
  if (length <= 0) return start
  const ratio = distanceFromStart / length
  return {
    x: start.x + (end.x - start.x) * ratio,
    y: start.y + (end.y - start.y) * ratio,
  }
}

function segmentPathAlongPolyline(points: Point[], startDistance: number, endDistance: number): string {
  const segmentPoints: Point[] = []
  let travelled = 0
  for (let index = 1; index < points.length; index += 1) {
    const segmentStart = points[index - 1]
    const segmentEnd = points[index]
    const segmentLength = distance(segmentStart, segmentEnd)
    const segmentFrom = travelled
    const segmentTo = travelled + segmentLength
    travelled = segmentTo
    const overlapFrom = Math.max(startDistance, segmentFrom)
    const overlapTo = Math.min(endDistance, segmentTo)
    if (overlapTo <= overlapFrom) continue

    const startPoint = pointOnSegment(segmentStart, segmentEnd, overlapFrom - segmentFrom)
    const endPoint = pointOnSegment(segmentStart, segmentEnd, overlapTo - segmentFrom)
    if (segmentPoints.length === 0 || !pointsEqual(segmentPoints[segmentPoints.length - 1], startPoint)) {
      segmentPoints.push(startPoint)
    }
    segmentPoints.push(endPoint)
  }
  return pathFromPoints(segmentPoints)
}

export function subgraphBridgeDashPaths(params: Parameters<typeof subgraphBridgePoints>[0]): string[] {
  const points = subgraphBridgePoints(params)
  const length = polylineLength(points)
  if (length <= 0) return []
  if (length <= SUBGRAPH_BRIDGE_DASH) {
    return [pathFromPoints(points)]
  }

  const intervals: Array<[number, number]> = []
  const addInterval = (start: number, end: number) => {
    const clampedStart = Math.max(0, Math.min(length, start))
    const clampedEnd = Math.max(clampedStart, Math.min(length, end))
    if (clampedEnd - clampedStart < 0.5) return
    const previous = intervals[intervals.length - 1]
    if (previous && clampedStart <= previous[1]) {
      previous[1] = Math.max(previous[1], clampedEnd)
      return
    }
    intervals.push([clampedStart, clampedEnd])
  }

  const sourceClip = 0
  const visibleLength = length - sourceClip
  addInterval(sourceClip, sourceClip + SUBGRAPH_BRIDGE_DASH)
  const finalStart = Math.max(sourceClip, length - SUBGRAPH_BRIDGE_DASH)
  for (
    let cursor = sourceClip + SUBGRAPH_BRIDGE_DASH + SUBGRAPH_BRIDGE_GAP;
    cursor + SUBGRAPH_BRIDGE_DASH <= finalStart - SUBGRAPH_BRIDGE_GAP;
    cursor += SUBGRAPH_BRIDGE_DASH + SUBGRAPH_BRIDGE_GAP
  ) {
    addInterval(cursor, cursor + SUBGRAPH_BRIDGE_DASH)
  }
  if (visibleLength > SUBGRAPH_BRIDGE_DASH) {
    addInterval(finalStart, length)
  }

  return intervals.map(([start, end]) => segmentPathAlongPolyline(points, start, end))
}

export function SubgraphBridgeEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  style,
}: EdgeProps<SubgraphBridgeEdgeModel>) {
  const paths = subgraphBridgeDashPaths({ sourceX, sourceY, targetX, targetY })
  return (
    <>
      {paths.map((path, index) => (
        <ReactFlow.BaseEdge
          key={`${id}-${index}`}
          id={`${id}-${index}`}
          path={path}
          className="subgraph-bridge-edge"
          style={{
            pointerEvents: 'none',
            ...style,
          }}
        />
      ))}
    </>
  )
}
