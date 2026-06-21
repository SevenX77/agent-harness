import { NodeToolbar, Position } from '@xyflow/react'
import { useMemo } from 'react'
import type { EventEnvelope } from '@/api/types'
import { HitlPromptForm } from './HitlPromptForm'
import { latestHitlPrompt, type TraceHitlResumeRequest } from './hitl-prompt'

interface HitlNodeToolbarProps {
  traceEvents: readonly EventEnvelope[]
  submitting?: boolean
  onSubmitHitlResponse?: (request: TraceHitlResumeRequest) => void
}

/**
 * F4: the node-anchored HitL input box. When the run stream carries an
 * `interrupted`/HitL event, the paused node (id == phase_name) gets a floating
 * rich-text input box ABOVE it — so "which node is waiting" and "where you
 * answer" correspond spatially, instead of a fixed top/side bar.
 *
 * Rendered inside GraphCanvas's <ReactFlow> subtree so NodeToolbar can read the
 * React Flow store and position itself against the node. Reuses HitlPromptForm
 * (the same form the side panel uses) — no second form implementation.
 */
export function HitlNodeToolbar({ traceEvents, submitting = false, onSubmitHitlResponse }: HitlNodeToolbarProps) {
  const prompt = useMemo(() => latestHitlPrompt(traceEvents as EventEnvelope[]), [traceEvents])
  // Anchor to the node that went paused. The node id IS the phase name
  // (deriveNodeStatuses keys paused status by phase_name), so without a phase
  // name there is nothing to anchor to.
  const pausedNodeId = prompt?.phaseName ?? null
  if (!prompt || !pausedNodeId) return null

  return (
    <NodeToolbar nodeId={pausedNodeId} isVisible position={Position.Top} className="w-[320px] max-w-[80vw]">
      <HitlPromptForm prompt={prompt} submitting={submitting} onSubmitHitlResponse={onSubmitHitlResponse} />
    </NodeToolbar>
  )
}
