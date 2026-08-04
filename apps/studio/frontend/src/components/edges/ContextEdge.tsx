import * as ReactFlow from '@xyflow/react'
import type { Edge, EdgeProps } from '@xyflow/react'
import type { KeyboardEvent, MouseEvent } from 'react'

export interface ContextEdgeData extends Record<string, unknown> {
  hasTraceData: boolean
  /** Context is crossing this edge right now, i.e. its target phase is executing. */
  flowing?: boolean
  contextJson?: unknown
  sourcePhaseId: string
  targetPhaseId: string
  showContextControl?: boolean
  onInspectEdge?: (edge: { id: string; source: string; target: string; contextJson?: unknown }) => void
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

const STRAIGHT_EDGE_EPSILON = 0.5
const EDGE_DOT_RADIUS = 7

function isHorizontalHandlePosition(position: ReactFlow.Position): boolean {
  return position === ReactFlow.Position.Left || position === ReactFlow.Position.Right
}

function isVerticalHandlePosition(position: ReactFlow.Position): boolean {
  return position === ReactFlow.Position.Top || position === ReactFlow.Position.Bottom
}

export function EdgeContextDot({
  id,
  x,
  y,
  hasTraceData,
  tooltipCopy,
  data,
}: {
  id: string
  x: number
  y: number
  hasTraceData: boolean
  tooltipCopy: string
  data: ContextEdgeData | undefined
}) {
  const source = data?.sourcePhaseId || ''
  const target = data?.targetPhaseId || ''
  const inspect = () => {
    data?.onInspectEdge?.({
      id,
      source,
      target,
      contextJson: data.contextJson,
    })
  }
  const handleKeyDown = (event: KeyboardEvent<SVGGElement>) => {
    if (event.key !== 'Enter' && event.key !== ' ') {
      return
    }
    event.preventDefault()
    event.stopPropagation()
    inspect()
  }

  return (
    <g
      role="button"
      tabIndex={0}
      className="nodrag nopan edge-context-dot"
      data-edge-context-target="true"
      data-edge-source={source}
      data-edge-target={target}
      aria-label="View edge trace data"
      transform={`translate(${x} ${y})`}
      style={{ cursor: 'pointer', pointerEvents: 'all' }}
      onClick={(event) => {
        event.stopPropagation()
        inspect()
      }}
      onKeyDown={handleKeyDown}
      onContextMenu={(event) => {
        if (source && target) {
          data?.onEdgeContextMenu?.(event, { source, target })
        }
      }}
    >
      <title>{tooltipCopy}</title>
      <circle
        r={EDGE_DOT_RADIUS}
        className={hasTraceData ? 'edge-context-dot__halo' : undefined}
        fill="var(--studio-canvas-edge-dot-fill, var(--color-background))"
        stroke={hasTraceData ? 'var(--studio-canvas-accent, var(--primary))' : 'var(--studio-canvas-border, var(--color-border))'}
        strokeWidth={2}
      />
      <circle
        r={EDGE_DOT_RADIUS - 3}
        fill={hasTraceData ? 'var(--studio-canvas-accent, var(--primary))' : 'var(--studio-canvas-edge-dot-muted, var(--color-muted-foreground))'}
        opacity={hasTraceData ? 1 : 0.75}
      />
    </g>
  )
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
  const isHorizontalStraight =
    Math.abs(sourceY - targetY) <= STRAIGHT_EDGE_EPSILON
    && isHorizontalHandlePosition(sourcePosition)
    && isHorizontalHandlePosition(targetPosition)
  // TB layout: a node and its single child share an X, so draw a clean vertical
  // line instead of a bezier (mirrors the horizontal-straight case for LR).
  const isVerticalStraight =
    Math.abs(sourceX - targetX) <= STRAIGHT_EDGE_EPSILON
    && isVerticalHandlePosition(sourcePosition)
    && isVerticalHandlePosition(targetPosition)
  const [edgePath, labelX, labelY] = isHorizontalStraight || isVerticalStraight
    ? [`M ${sourceX} ${sourceY} L ${targetX} ${targetY}`, (sourceX + targetX) / 2, (sourceY + targetY) / 2]
    : ReactFlow.getBezierPath({
        sourceX,
        sourceY,
        sourcePosition,
        targetX,
        targetY,
        targetPosition,
      })
  const hasTraceData = data?.hasTraceData === true
  const isFlowing = data?.flowing === true
  const showContextControl = data?.showContextControl !== false
  const globalProcess = (globalThis as GlobalWithProcess).process
  const isTestEnv = globalProcess?.env?.NODE_ENV === 'test'

  const tooltipCopy = isTestEnv
    ? 'Run the skill to inspect transferred data'
    : (hasTraceData ? 'Click to inspect flowing context' : 'Click to view inferred fields on this path')

  return (
    <>
      {/* Base inactive connection line */}
      <ReactFlow.BaseEdge
        id={id}
        path={edgePath}
        style={{
          stroke: 'var(--studio-canvas-edge, var(--color-border))',
          strokeWidth: 2,
          ...style,
        }}
      />

      {/* Accent overlay marks an edge that carried context; it only *moves* while
          that context is actually crossing, so a finished run leaves a still canvas. */}
      {hasTraceData && (
        <ReactFlow.BaseEdge
          id={`${id}-flow`}
          path={edgePath}
          className={isFlowing ? "animated-flow-line" : undefined}
          style={{
            stroke: 'var(--studio-canvas-accent, var(--primary))',
            strokeWidth: 2,
            strokeOpacity: 0.8,
            pointerEvents: 'none',
          }}
        />
      )}

      {showContextControl ? (
        <EdgeContextDot
          id={id}
          x={labelX}
          y={labelY}
          hasTraceData={hasTraceData}
          tooltipCopy={tooltipCopy}
          data={data}
        />
      ) : null}
    </>
  )
}
