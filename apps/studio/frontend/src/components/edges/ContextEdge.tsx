import * as ReactFlow from '@xyflow/react'
import type { Edge, EdgeProps } from '@xyflow/react'
import { Tooltip, TooltipContent, TooltipTrigger } from '../ui/tooltip'

export interface ContextEdgeData extends Record<string, unknown> {
  hasTraceData: boolean
  contextJson?: unknown
  sourcePhaseId: string
  targetPhaseId: string
}

type ContextEdgeModel = Edge<ContextEdgeData, 'contextEdge'>

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
  const [edgePath, labelX, labelY] = ReactFlow.getBezierPath({
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
                aria-label="查看连线传递数据"
                className={[
                  'block size-3 rounded-full border bg-transparent transition-colors',
                  hasTraceData
                    ? 'border-primary bg-primary'
                    : 'border-primary/70 hover:border-primary',
                ].join(' ')}
                onClick={(event) => {
                  event.stopPropagation()
                }}
              />
            </TooltipTrigger>
            <TooltipContent side="top">运行后可查看传递数据</TooltipContent>
          </Tooltip>
        </div>
      </ReactFlow.EdgeLabelRenderer>
    </>
  )
}
