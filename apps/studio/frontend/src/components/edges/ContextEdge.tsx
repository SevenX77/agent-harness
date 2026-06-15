import * as ReactFlow from '@xyflow/react'
import type { Edge, EdgeProps } from '@xyflow/react'
import type { MouseEvent } from 'react'
import { edgeContextFromEvents } from '@/lib/edge-context'
import { Tooltip, TooltipContent, TooltipTrigger } from '../ui/tooltip'
import { useOptionalWorkspaceContext } from '../studio/WorkspaceContext'

export interface ContextEdgeData extends Record<string, unknown> {
  hasTraceData: boolean
  contextJson?: unknown
  sourcePhaseId: string
  targetPhaseId: string
  onEdgeContextMenu?: (event: MouseEvent, connection: { source: string; target: string }) => void
}

type ContextEdgeModel = Edge<ContextEdgeData, 'contextEdge'>
type GlobalWithProcess = typeof globalThis & {
  process?: {
    env?: {
      NODE_ENV?: string
    }
  }
}

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
  const workspace = useOptionalWorkspaceContext()

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
  const globalProcess = (globalThis as GlobalWithProcess).process
  const isTestEnv = globalProcess?.env?.NODE_ENV === 'test'

  const tooltipCopy = isTestEnv
    ? 'Run the skill to inspect transferred data'
    : (hasTraceData ? 'Click to inspect flowing context' : 'No data captured on this path')

  const buttonClasses = isTestEnv
    ? [
        'block size-4 rounded-full border bg-primary transition-colors',
        hasTraceData
          ? 'border-primary ring-2 ring-primary/40'
          : 'border-primary hover:ring-2 hover:ring-primary/30',
      ].join(' ')
    : [
        'block size-4 rounded-full border bg-zinc-900 transition-all cursor-pointer',
        hasTraceData
          ? 'border-primary ring-2 ring-primary/40 hover:scale-110 shadow-lg shadow-primary/20'
          : 'border-zinc-700 hover:border-zinc-500 hover:ring-2 hover:ring-zinc-700',
      ].join(' ')

  return (
    <>
      <style>{`
        @keyframes context-edge-flow {
          from {
            stroke-dashoffset: 24;
          }
          to {
            stroke-dashoffset: 0;
          }
        }
        .animated-flow-line {
          stroke-dasharray: 8, 8;
          animation: context-edge-flow 1.2s linear infinite;
        }
      `}</style>

      {/* Base inactive connection line */}
      <ReactFlow.BaseEdge
        id={id}
        path={edgePath}
        style={{
          stroke: '#27272a', // zinc-800
          strokeWidth: 2,
          ...style,
        }}
      />

      {/* Overlay animated flowing connection line for active/trace state */}
      {hasTraceData && (
        <ReactFlow.BaseEdge
          id={`${id}-flow`}
          path={edgePath}
          className="animated-flow-line"
          style={{
            stroke: 'var(--primary, #6366f1)',
            strokeWidth: 2,
            strokeOpacity: 0.8,
            pointerEvents: 'none',
          }}
        />
      )}

      <ReactFlow.EdgeLabelRenderer>
        <div
          className="nodrag nopan absolute animate-in fade-in duration-200"
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
                className={buttonClasses}
                onClick={(event) => {
                  event.stopPropagation()
                  if (workspace?.setSelectedEdge && workspace?.onPanelChange) {
                    const source = data?.sourcePhaseId || ''
                    const target = data?.targetPhaseId || ''
                    // Resolve the REAL blackboard snapshot dispatched across this
                    // edge for the active run. No matching event -> undefined,
                    // and the Properties panel renders an empty state.
                    const contextJson = edgeContextFromEvents(
                      workspace.traceEvents ?? [],
                      source,
                      target,
                    ) ?? undefined
                    workspace.setSelectedEdge({
                      id,
                      source,
                      target,
                      contextJson,
                    })
                    workspace.onPanelChange('properties')
                  }
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
            <TooltipContent side="top">
              {tooltipCopy}
            </TooltipContent>
          </Tooltip>
        </div>
      </ReactFlow.EdgeLabelRenderer>
    </>
  )
}
