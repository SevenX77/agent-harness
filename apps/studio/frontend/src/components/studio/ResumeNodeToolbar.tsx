import { NodeToolbar, Position } from '@xyflow/react'
import { Loader2 } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import type { ResumeValidityResponse } from '@/api/types'
import type { ResumeRunOptions } from '@/api/client'
import type { SkillNodeStatus } from '@/components/nodes'
import { nodeResumeOptionsFromValidity } from './node-resume'

/**
 * N5 atom #2 (spec F2): the node-anchored [Resume] control.
 *
 * After a real run fails, the resume affordance must sit ON the failed node — so
 * "the node you fixed" and "where you resume from" correspond spatially — instead
 * of living only in the right-side Properties panel. This mirrors HitlNodeToolbar:
 * a @xyflow/react NodeToolbar anchored to the failed node (id == phase name), so
 * it pans/zooms with the canvas. It reuses the SAME validity-driven resume request
 * builder (nodeResumeOptionsFromValidity) and the SAME resumeRun path the side
 * panel calls (onResumeNode -> Workspace.handleResumeNode -> resumeRun), carrying
 * resume_from_node_id so the engine resumes from this node. The global top-bar
 * Resume (whole-run from the last checkpoint) is a separate affordance and stays;
 * the two coexist.
 *
 * Rendered inside GraphCanvas's <ReactFlow> subtree so NodeToolbar can read the
 * React Flow store. Renders nothing unless there is an active run and the selected
 * node is in the error state (the same gate as NodeResumeDebugBar).
 */
interface ResumeNodeToolbarProps {
  runId: string | null
  nodeId: string | null
  nodeStatus: SkillNodeStatus | null
  resumeValidity: ResumeValidityResponse | null
  loading: boolean
  error: string | null
  resumeLoading: boolean
  onResumeNode?: (options: ResumeRunOptions) => Promise<void> | void
}

function resumeReason(
  loading: boolean,
  error: string | null,
  resumeValidity: ResumeValidityResponse | null,
): string {
  if (loading) return 'checking'
  if (error) return 'checkpoint.invalid'
  return resumeValidity?.reason ?? 'checkpoint.not_found'
}

export function ResumeNodeToolbar({
  runId,
  nodeId,
  nodeStatus,
  resumeValidity,
  loading,
  error,
  resumeLoading,
  onResumeNode,
}: ResumeNodeToolbarProps) {
  // Same gate as the side-panel NodeResumeDebugBar: only a failed node of an
  // active run can be resumed, so without those there is nothing to anchor.
  if (!runId || !nodeId || nodeStatus !== 'error') {
    return null
  }

  const allowed = Boolean(resumeValidity?.resume_allowed)
  const reason = resumeReason(loading, error, resumeValidity)
  const dirtyFields = resumeValidity?.dirty_fields ?? []
  const disabled = !allowed || loading || resumeLoading || !onResumeNode
  const buttonLabel = allowed ? (resumeLoading ? 'Resuming' : 'Resume node') : 'Resume disabled'

  const handleResume = () => {
    if (!allowed || !resumeValidity || !onResumeNode) {
      return
    }
    void onResumeNode(nodeResumeOptionsFromValidity(resumeValidity, nodeId))
  }

  return (
    <NodeToolbar nodeId={nodeId} isVisible position={Position.Top} className="w-[300px] max-w-[80vw]">
      <section
        className="rounded-md border border-border bg-card px-3 py-2 shadow-md"
        aria-label="Resume failed node"
      >
        <div className="flex items-center justify-between gap-2">
          <div className="min-w-0">
            <div className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
              Resume from node
            </div>
            <div className="mt-1 flex min-w-0 flex-wrap items-center gap-1.5 text-xs text-foreground">
              <Badge variant={allowed ? 'secondary' : 'destructive'}>{reason}</Badge>
              {dirtyFields.map((field) => (
                <Badge key={field} variant="outline">{field}</Badge>
              ))}
            </div>
            {error ? <div className="mt-1 text-xs text-muted-foreground">{error}</div> : null}
          </div>
          <Button type="button" size="sm" disabled={disabled} onClick={handleResume}>
            {loading ? <Loader2 className="size-3 animate-spin" data-icon="inline-start" /> : null}
            {buttonLabel}
          </Button>
        </div>
      </section>
    </NodeToolbar>
  )
}
