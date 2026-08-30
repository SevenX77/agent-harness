import { Handle, Position, type NodeProps } from '@xyflow/react'
import { AlertTriangle, Bot, Briefcase, CircleDot, Code, ListTree, Minus, Network, Pause, Plus, ShieldCheck, ShieldHalf } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { AgentStepsInline } from '@/components/studio/AgentStepsInline'
import { CONFLICT_ICON_CLASS, CONFLICT_TITLE, CONFLICT_VERB } from '@/components/studio/conflict-vocabulary'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { Popover, PopoverContent, PopoverAnchor } from '@/components/ui/popover'
import { Button } from '@/components/ui/button'
import { NodeCompileErrorBadge } from './NodeCompileErrorBadge'
import { nodeCardClass, type NodeCardRing } from './node-card'
import { subgraphProgressLabel } from '@/components/GraphCanvas/subgraph-run'
import { NodeRuntimeClock, nodeActivityText } from './node-runtime'
import { nodeStatusLabel, StatusCapsule } from './StatusCapsule'
import {
  SKILL_FLOW_SOURCE_HANDLE_ID,
  SKILL_FLOW_TARGET_HANDLE_ID,
  SUBGRAPH_BRIDGE_SOURCE_HANDLE_ID,
} from './subgraph-bridge-handles'
import type { SkillGraphNode, SkillGraphNodeData } from './types'

type PhaseKind = 'LOGIC' | 'AGENT' | 'SUBGRAPH'

export { formatNodeCompileError } from './NodeCompileErrorBadge'

function phaseKindLabel(data: Pick<SkillGraphNodeData, 'mode' | 'subgraphPath'>): PhaseKind {
  if (data.subgraphPath || data.mode === 'subgraph') return 'SUBGRAPH'
  if (data.mode === 'agent' || data.mode === 'skill' || data.mode === 'llm') return 'AGENT'
  return 'LOGIC'
}

function phaseKindIcon(kind: PhaseKind): typeof Bot {
  if (kind === 'LOGIC') return Code
  if (kind === 'SUBGRAPH') return Network
  return Bot
}

export function SkillNode({ data, selected }: NodeProps<SkillGraphNode>) {
  const { t } = useTranslation('canvas')
  const statusLabel = nodeStatusLabel(data.status)
  const isRunning = data.status === 'running'
  const kind = phaseKindLabel(data)
  const KindIcon = phaseKindIcon(kind)
  const subagentCount = data.subagents?.length ?? 0
  const compileErrors = data.compileErrors ?? []
  const hasGolden = data.goldenState === 'has-golden'
  const isLogicOk = data.goldenState === 'logic-ok'
  // N5 atom #1 (spec F1): when this node failed, surface its error summary in-place
  // on the node (not only the red badge, not only the Properties panel) so the user
  // sees why the run stopped right where it stopped.
  const inlineErrorMessage = data.status === 'error' && data.errorMessage ? data.errorMessage : null
  // N5 atom #3 (spec F3): an upstream edit invalidated this downstream node's
  // checkpoint (it is in the resume-validity `affected_downstream` set), so its
  // node-level Resume is grayed out. Dim the node and label why it can't continue.
  const isDirtyDownstream = data.isDirtyDownstream === true
  // N2 atom #15 (l3-step-edit): an AGENT node with its body + save callback wired
  // gets an inline L3 step editor — expand to add / remove / reorder / edit the
  // body's `<step>` blocks right on the canvas (no Properties detour). Logic /
  // subgraph nodes never get it (build-nodes leaves the callbacks undefined).
  // R3-8: the inline steps are a read-only projection (editing lives in the
  // editor), so showing them needs only the toggle callback and a body.
  const canShowSteps = kind === 'AGENT' && typeof data.onToggleSteps === 'function' && typeof data.agentBody === 'string'
  // canvas F7 (4): a SUBGRAPH container reports how far its own graph got, in both
  // states — the chip stays on the board when the container is expanded, so one
  // place carries the count whether the child board is showing or not.
  const subgraphProgressText = data.subgraphProgress ? subgraphProgressLabel(data.subgraphProgress) : null
  const activityText = data.activity ? nodeActivityText(data.activity, isRunning) : null

  const ring: NodeCardRing = data.isConflictCancelled
    ? 'destructive'
    : data.activeConflict
    ? 'warning'
    : selected
    ? 'selected'
    : 'none'
  const nodeContent = (
    <div
      aria-disabled={isDirtyDownstream || undefined}
      data-dirty-downstream={isDirtyDownstream || undefined}
      className={nodeCardClass({
        minWidth: 'min-w-[240px]',
        ring,
        extra: [isDirtyDownstream && 'opacity-50 grayscale', isRunning && 'studio-running-dash-frame'],
      })}
    >
      <Handle
        id={SKILL_FLOW_TARGET_HANDLE_ID}
        type="target"
        position={Position.Top}
        className="skill-flow-target-handle !size-2.5 !border-background !bg-primary opacity-60 group-hover:opacity-100 transition-opacity duration-200"
      />
      <div className="flex items-start gap-3">
        <div className="flex size-9 shrink-0 items-center justify-center rounded-md bg-secondary text-secondary-foreground">
          <KindIcon className="size-4" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-semibold text-foreground">{data.label}</div>
          <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
            <span>{kind}</span>
            {subagentCount > 0 ? (
              <Tooltip>
                <TooltipTrigger asChild>
                  <span
                    aria-label={`${subagentCount} subagents available`}
                    className="inline-flex size-5 items-center justify-center rounded-md border border-border bg-muted text-muted-foreground"
                  >
                    <Briefcase className="size-3" />
                  </span>
                </TooltipTrigger>
                <TooltipContent side="top">{subagentCount} subagents available</TooltipContent>
              </Tooltip>
            ) : null}
            {/* Golden coverage is a CLASSIFICATION of the node, not a verdict on
                this run, so it is carried by the shield glyph alone — colour on
                the canvas is reserved for severity (decision 2026-08-08 D2). */}
            <NodeCompileErrorBadge errors={compileErrors} scope="node" />
            {/* A filled dot beside the line is what every debugger has used for
                a breakpoint since gdb's front-ends (VS Code, IntelliJ, Chrome
                DevTools all draw one), so it needs no legend. Glyph only, no
                colour: on this canvas colour is reserved for severity (decision
                2026-08-08 D2), and a breakpoint is a choice, not a problem. */}
            {data.hasBreakpoint ? (
              <Tooltip>
                <TooltipTrigger asChild>
                  <span
                    data-node-breakpoint="set"
                    aria-label={t('node.breakpointSet')}
                    className="inline-flex size-5 items-center justify-center rounded-md border border-border bg-muted text-muted-foreground"
                  >
                    <CircleDot className="size-3" />
                  </span>
                </TooltipTrigger>
                <TooltipContent side="top">{t('node.breakpointSet')}</TooltipContent>
              </Tooltip>
            ) : null}
            {hasGolden ? (
              <Tooltip>
                <TooltipTrigger asChild>
                  <span
                    aria-label={t('node.goldenCaptured')}
                    className="inline-flex size-5 items-center justify-center rounded-md border border-border bg-muted text-muted-foreground"
                  >
                    <ShieldCheck className="size-3" />
                  </span>
                </TooltipTrigger>
                <TooltipContent side="top">Golden captured for this node</TooltipContent>
              </Tooltip>
            ) : isLogicOk ? (
              <Tooltip>
                <TooltipTrigger asChild>
                  <span
                    aria-label={t('node.logicOk')}
                    className="inline-flex size-5 items-center justify-center rounded-md border border-border bg-muted text-muted-foreground"
                  >
                    <ShieldHalf className="size-3" />
                  </span>
                </TooltipTrigger>
                <TooltipContent side="top">Predict ran this node — no golden yet</TooltipContent>
              </Tooltip>
            ) : null}
          </div>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1">
          <Tooltip>
            <TooltipTrigger asChild>
              <StatusCapsule status={data.status} />
            </TooltipTrigger>
            <TooltipContent side="top">{statusLabel}</TooltipContent>
          </Tooltip>
          {data.runtime ? <NodeRuntimeClock runtime={data.runtime} running={isRunning} /> : null}
          {activityText ? (
            <Tooltip>
              <TooltipTrigger asChild>
                <span
                  data-node-activity={isRunning ? 'running' : 'settled'}
                  aria-label={t('node.activity')}
                  className="text-[10px] tabular-nums leading-none text-muted-foreground"
                >
                  {activityText.short}
                </span>
              </TooltipTrigger>
              <TooltipContent side="top">{activityText.full}</TooltipContent>
            </Tooltip>
          ) : null}
          {subgraphProgressText ? (
            <Tooltip>
              <TooltipTrigger asChild>
                <span
                  aria-label={t('node.subgraphProgress')}
                  className="text-[10px] tabular-nums leading-none text-muted-foreground"
                >
                  {subgraphProgressText.short}
                </span>
              </TooltipTrigger>
              <TooltipContent side="top">{subgraphProgressText.full}</TooltipContent>
            </Tooltip>
          ) : null}
        </div>
      </div>
      {inlineErrorMessage ? (
        <div
          role="alert"
          aria-label={t('node.errorSummary')}
          className="mt-2 flex items-start gap-1.5 rounded-md border border-destructive/40 bg-destructive/10 px-2 py-1 text-xs text-destructive"
        >
          <AlertTriangle className="mt-0.5 size-3 shrink-0" />
          <span className="min-w-0 break-words">{inlineErrorMessage}</span>
        </div>
      ) : null}
      {isDirtyDownstream ? (
        <div
          role="note"
          aria-label={t('node.resumeUnavailable')}
          className="mt-2 flex items-start gap-1.5 rounded-md border border-border bg-muted/50 px-2 py-1 text-xs text-muted-foreground"
        >
          <Pause className="mt-0.5 size-3 shrink-0" />
          <span className="min-w-0 break-words">Resume unavailable — an upstream edit invalidated this node&apos;s checkpoint</span>
        </div>
      ) : null}
      {canShowSteps ? (
        <div className="mt-2">
          <button
            type="button"
            aria-label={data.isStepsExpanded ? t('node.collapseSteps') : t('node.viewSteps')}
            onClick={(event) => {
              event.stopPropagation()
              data.onToggleSteps?.()
            }}
            className="inline-flex items-center gap-1 rounded-md border border-border bg-card px-1.5 py-0.5 text-[11px] font-medium text-muted-foreground transition-colors hover:border-primary hover:text-foreground"
          >
            <ListTree className="size-3" />
            {data.isStepsExpanded ? t('node.hideSteps') : t('node.viewSteps')}
          </button>
          {data.isStepsExpanded ? (
            <div
              onClick={(event) => event.stopPropagation()}
              onDoubleClick={(event) => event.stopPropagation()}
            >
              <AgentStepsInline body={data.agentBody ?? ''} />
            </div>
          ) : null}
        </div>
      ) : null}
      {typeof data.onToggleSubgraph === 'function' ? (
        // Right-edge center expand toggle (设计 "右缘加号"). Shown on EVERY editable
        // SUBGRAPH node — including unresolved-path ones, which expand to the inline
        // recovery state — never on read-only preview children (their callback is
        // stripped). `top-1/2 -translate-y-1/2 translate-x-1/2` centers it on, and
        // half-overhangs, the node's right border.
        <div className="absolute right-0 top-1/2 z-10 -translate-y-1/2 translate-x-1/2">
          {data.isExpanded ? (
            <Handle
              id={SUBGRAPH_BRIDGE_SOURCE_HANDLE_ID}
              type="source"
              position={Position.Right}
              isConnectable={false}
              className="subgraph-bridge-source-handle"
            />
          ) : null}
          <button
            type="button"
            aria-label={data.isExpanded ? t('node.collapseSubgraph') : t('node.expandSubgraph')}
            onClick={(event) => {
              event.stopPropagation()
              data.onToggleSubgraph?.()
            }}
            className="nodrag nopan relative z-10 inline-flex size-5 items-center justify-center rounded-full border border-border bg-card text-foreground shadow-sm transition-colors hover:border-primary"
          >
            {data.isExpanded ? <Minus className="size-3" /> : <Plus className="size-3" />}
          </button>
        </div>
      ) : null}
      {/* N2 atom #13: expanding a subgraph node now renders a canvas-level dashed
          container with the child's REAL nodes/edges (see GraphCanvas
          subgraphExpansion), not an in-node row list. The toggle above only flips
          the expand state; the container is drawn beside this node on the canvas. */}
      <Handle
        id={SKILL_FLOW_SOURCE_HANDLE_ID}
        type="source"
        position={Position.Bottom}
        className="skill-flow-source-handle !size-2.5 !border-background !bg-primary opacity-60 group-hover:opacity-100 transition-opacity duration-200"
      />
    </div>
  )

  if (data.activeConflict) {
    return (
      <Popover open={true} modal={false}>
        <PopoverAnchor asChild>
          {nodeContent}
        </PopoverAnchor>
        <PopoverContent portalled={false} side="top" align="center" avoidCollisions={false} className="w-[280px] p-3 bg-popover border border-border rounded-md text-foreground shadow-xl z-50">
          <div className="flex items-start gap-2.5">
            <AlertTriangle className={`${CONFLICT_ICON_CLASS} mt-0.5`} aria-hidden />
            <div className="flex-1 min-w-0">
              <h4 className="text-xs font-semibold text-foreground">{CONFLICT_TITLE.sequentialOverwrite}</h4>
              <p className="mt-1 text-[11px] text-muted-foreground leading-normal">
                Field <code className="text-warning font-mono text-[10px] px-1 py-0.5 bg-muted/60 rounded">{data.activeConflict.fieldName}</code> is also output by upstream node <span className="font-semibold">{data.activeConflict.ancestorNodeId}</span>. Running this phase replaces that value.
              </p>
              <div className="mt-3 flex items-center justify-end gap-2">
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7 text-[11px] px-2 text-muted-foreground hover:text-foreground"
                  onClick={() => data.onCancelSequentialOverwrite?.(
                    data.activeConflict!.nodeId,
                    data.activeConflict!.fieldName,
                    data.activeConflict!.ancestorNodeId,
                  )}
                >
                  {CONFLICT_VERB.cancel}
                </Button>
                  <Button
                    size="sm"
                    variant="warning"
                    className="h-7 text-[11px] px-2.5 font-medium"
                    onClick={() => data.onAllowSequentialOverwrite?.(
                      data.activeConflict!.nodeId,
                      data.activeConflict!.fieldName,
                      data.activeConflict!.ancestorNodeId,
                    )}
                  >
                    {CONFLICT_VERB.overwrite}
                  </Button>
              </div>
            </div>
          </div>
        </PopoverContent>
      </Popover>
    )
  }

  return nodeContent
}
