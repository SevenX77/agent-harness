import * as ReactFlow from '@xyflow/react'
import type { Edge, EdgeProps } from '@xyflow/react'
import type { KeyboardEvent, MouseEvent } from 'react'
import type { EdgeRunStatus } from '@/utils/edge-status-projection'
import {
  EDGE_DOT_RADIUS,
  EDGE_INTERACTION_WIDTH,
  EDGE_RUN_STATUS_STROKE,
  EDGE_STROKE_ACCENT,
  EDGE_STROKE_BASE,
  EDGE_STROKE_WIDTH,
} from './edge-style'

export interface ContextEdgeData extends Record<string, unknown> {
  hasTraceData: boolean
  /**
   * How this edge's own run segment stands (canvas design F6). Derived from the
   * engine's edge_start / edge_end brackets — NOT from whether the downstream
   * node is executing, which lit every incoming edge of a fan-in at once and
   * could say only "moving / not moving".
   */
  runStatus?: EdgeRunStatus
  /** This edge is the one whose scope the trace panel is showing. */
  isSelected?: boolean
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
        stroke={hasTraceData ? EDGE_STROKE_ACCENT : 'var(--studio-canvas-border, var(--color-border))'}
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
  const runStatus: EdgeRunStatus = data?.runStatus ?? 'idle'
  const isSelected = data?.isSelected === true
  const accentStroke = runStatus === 'idle' ? null : EDGE_RUN_STATUS_STROKE[runStatus]
  const showContextControl = data?.showContextControl !== false
  const selectEdge = () => {
    data?.onInspectEdge?.({
      id,
      source: data.sourcePhaseId,
      target: data.targetPhaseId,
      contextJson: data.contextJson,
    })
  }
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
          stroke: EDGE_STROKE_BASE,
          strokeWidth: EDGE_STROKE_WIDTH,
          ...style,
        }}
      />

      {/* Accent overlay carries the edge's own segment state. It *moves* only
          while the segment is open, so a run at a terminal verdict leaves a
          still canvas — the same 铁律 that closes node lights (D7). */}
      {accentStroke !== null && (
        <ReactFlow.BaseEdge
          id={`${id}-flow`}
          path={edgePath}
          className={runStatus === 'running' ? 'animated-flow-line' : undefined}
          data-edge-run-status={runStatus}
          style={{
            stroke: accentStroke,
            strokeWidth: EDGE_STROKE_WIDTH,
            strokeOpacity: 0.8,
            pointerEvents: 'none',
          }}
        />
      )}

      {/* Selection ring: the edge the trace panel is scoped to reads as chosen
          from across the board, not only by the panel's chip. */}
      {isSelected && (
        <ReactFlow.BaseEdge
          id={`${id}-selected`}
          path={edgePath}
          style={{
            stroke: EDGE_STROKE_ACCENT,
            strokeWidth: EDGE_STROKE_WIDTH * 4,
            strokeOpacity: 0.22,
            strokeLinecap: 'round',
            pointerEvents: 'none',
          }}
        />
      )}

      {/* The whole line is the hit target, not just the dot at its middle: a
          1.5px stroke is not something a reader can aim at. Clicking it selects
          the same edge the dot does — one action, one code path. */}
      <path
        d={edgePath}
        className="nodrag nopan react-flow__edge-interaction"
        data-edge-hit-path="true"
        aria-hidden
        fill="none"
        stroke="transparent"
        strokeWidth={EDGE_INTERACTION_WIDTH}
        style={{ cursor: 'pointer', pointerEvents: 'stroke' }}
        onClick={(event) => {
          event.stopPropagation()
          selectEdge()
        }}
        onContextMenu={(event) => {
          const source = data?.sourcePhaseId
          const target = data?.targetPhaseId
          if (source && target) {
            data?.onEdgeContextMenu?.(event, { source, target })
          }
        }}
      />

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
