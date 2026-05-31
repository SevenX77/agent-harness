import * as ReactFlow from '@xyflow/react'
import type { Edge, EdgeProps } from '@xyflow/react'
import type { MouseEvent } from 'react'
import { Tooltip, TooltipContent, TooltipTrigger } from '../ui/tooltip'

export interface ContextEdgeData extends Record<string, unknown> {
  hasTraceData: boolean
  contextJson?: unknown
  sourcePhaseId: string
  targetPhaseId: string
  onEdgeContextMenu?: (event: MouseEvent, connection: { source: string; target: string }) => void
}

type ContextEdgeModel = Edge<ContextEdgeData, 'contextEdge'>

const HORIZONTAL_EDGE_EPSILON = 0.5

function isHorizontalHandlePosition(position: ReactFlow.Position): boolean {
  return position === ReactFlow.Position.Left || position === ReactFlow.Position.Right
}

export function ContextEdge({
  id,
  sourceX,
  sourceY,
  sourcePosition,
  targetX,
  targetY,
  targetPosition,
  style,
  data,
}: EdgeProps<ContextEdgeModel>) {
  const [edgePath, labelX, labelY] = Math.abs(sourceY - targetY) <= HORIZONTAL_EDGE_EPSILON
    && isHorizontalHandlePosition(sourcePosition)
    && isHorizontalHandlePosition(targetPosition)
    ? [`M ${sourceX} ${sourceY} L ${targetX} ${targetY}`, (sourceX + targetX) / 2, sourceY]
    : ReactFlow.getBezierPath({
        sourceX,
        sourceY,
        sourcePosition,
        targetX,
        targetY,
        targetPosition,
      })
  const hasTraceData = data?.hasTraceData === true

  return (
    <>
      <ReactFlow.BaseEdge id={id} path={edgePath} style={{ strokeWidth: 1.5, ...style }} />
      <ReactFlow.EdgeLabelRenderer>
        <div
          className="nodrag nopan absolute"
          style={{
            transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
            pointerEvents: 'all',
          }}
        >
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                data-edge-context-target="true"
                data-edge-source={data?.sourcePhaseId}
                data-edge-target={data?.targetPhaseId}
                aria-label="View edge trace data"
                className={[
                  'block size-4 rounded-full border bg-primary transition-colors',
                  hasTraceData
                    ? 'border-primary ring-2 ring-primary/40'
                    : 'border-primary hover:ring-2 hover:ring-primary/30',
                ].join(' ')}
                onClick={(event) => {
                  event.stopPropagation()
                }}
                onContextMenu={(event) => {
                  if (data?.sourcePhaseId && data?.targetPhaseId) {
                    data.onEdgeContextMenu?.(event, {
                      source: data.sourcePhaseId,
                      target: data.targetPhaseId,
                    })
                  }
                }}
              />
            </TooltipTrigger>
            <TooltipContent side="top">Run the skill to inspect transferred data</TooltipContent>
          </Tooltip>
        </div>
      </ReactFlow.EdgeLabelRenderer>
    </>
  )
}
