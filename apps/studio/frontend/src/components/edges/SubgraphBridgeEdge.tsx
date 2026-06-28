import * as ReactFlow from '@xyflow/react'
import type { Edge, EdgeProps } from '@xyflow/react'
import type { ContextEdgeData } from './ContextEdge'

type SubgraphBridgeEdgeModel = Edge<ContextEdgeData, 'subgraphBridge'>

function edgeCoordinate(value: number): string {
  const rounded = Math.round(value * 1000) / 1000
  return Object.is(rounded, -0) ? '0' : String(rounded)
}

export function subgraphBridgePath({
  sourceX,
  sourceY,
  targetX,
  targetY,
}: {
  sourceX: number
  sourceY: number
  targetX: number
  targetY: number
}): string {
  if (Math.abs(sourceY - targetY) < 0.5) {
    return `M ${edgeCoordinate(sourceX)} ${edgeCoordinate(sourceY)} L ${edgeCoordinate(targetX)} ${edgeCoordinate(targetY)}`
  }
  const midX = sourceX + (targetX - sourceX) / 2
  return [
    `M ${edgeCoordinate(sourceX)} ${edgeCoordinate(sourceY)}`,
    `L ${edgeCoordinate(midX)} ${edgeCoordinate(sourceY)}`,
    `L ${edgeCoordinate(midX)} ${edgeCoordinate(targetY)}`,
    `L ${edgeCoordinate(targetX)} ${edgeCoordinate(targetY)}`,
  ].join(' ')
}

export function SubgraphBridgeEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  style,
}: EdgeProps<SubgraphBridgeEdgeModel>) {
  return (
    <ReactFlow.BaseEdge
      id={id}
      path={subgraphBridgePath({ sourceX, sourceY, targetX, targetY })}
      className="subgraph-bridge-edge"
      style={{
        pointerEvents: 'none',
        ...style,
      }}
    />
  )
}
