import * as ReactFlow from '@xyflow/react'
import type { Edge, EdgeProps } from '@xyflow/react'
import type { ContextEdgeData } from './ContextEdge'

type SubgraphBridgeEdgeModel = Edge<ContextEdgeData, 'subgraphBridge'>

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
      path={`M ${sourceX} ${sourceY} L ${targetX} ${targetY}`}
      className="subgraph-bridge-edge"
      style={{
        pointerEvents: 'none',
        ...style,
      }}
    />
  )
}
