import { Handle, Position, type NodeProps } from '@xyflow/react'
import { AlertTriangle, Bot, Briefcase, CheckCircle2, Circle, Code, ListTree, Minus, Network, Pause, Plus, Radio, ShieldCheck, ShieldHalf, Workflow } from 'lucide-react'
import { AgentStepsInline } from '@/components/studio/AgentStepsInline'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { Popover, PopoverContent, PopoverAnchor } from '@/components/ui/popover'
import { Button } from '@/components/ui/button'
import type { CompileError } from '@/api/types'
import { SUBGRAPH_BRIDGE_SOURCE_HANDLE_ID } from './subgraph-bridge-handles'
import type { SkillGraphNode, SkillGraphNodeData, SkillNodeStatus } from './types'

type PhaseKind = 'LOGIC' | 'AGENT' | 'SUBGRAPH'

/**
 * One-line `field · L<line> — message` projection of a single compile/lint error for the
 * canvas node tooltip (authoring N3 atom #4). The leading `field · L<line>` locator is
 * dropped segment-by-segment when the engine could not attribute it, so a field-less or
 * line-less error still reads as just its message. Pure + string-only so it is SSR-safe and
 * unit-testable without rendering the Radix Tooltip (which portals its content).
 */
export function formatNodeCompileError(error: CompileError): string {
  const segments: string[] = []
  if (error.field) {
    segments.push(error.field)
  }
  if (typeof error.line === 'number') {
    segments.push(`L${error.line}`)
  }
  const locator = segments.join(' · ')
  return locator ? `${locator} — ${error.message}` : error.message
}

const STATUS_STYLE: Record<SkillNodeStatus, { label: string, className: string, icon: typeof Circle }> = {
  idle: {
    label: 'Idle',
    className: 'border-border bg-card text-muted-foreground',
    icon: Circle,
  },
  running: {
    label: 'Running',
    className: 'animate-pulse-primary border-primary bg-primary/10 text-primary',
    icon: Radio,
  },
  success: {
    label: 'Success',
    className: 'border-emerald-500/45 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400',
    icon: CheckCircle2,
  },
  error: {
    label: 'Error',
    className: 'border-destructive/50 bg-destructive/10 text-destructive',
    icon: AlertTriangle,
  },
  paused: {
    label: 'Paused',
    className: 'border-amber-500/45 bg-amber-500/10 text-amber-700 dark:text-amber-300',
    icon: Pause,
  },
  breakpoint: {
    label: 'Breakpoint',
    className: 'border-fuchsia-500/45 bg-fuchsia-500/10 text-fuchsia-700 dark:text-fuchsia-300',
    icon: Workflow,
  },
}

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
  const style = STATUS_STYLE[data.status]
  const StatusIcon = style.icon
  const kind = phaseKindLabel(data)
  const KindIcon = phaseKindIcon(kind)
  const subagentCount = data.subagents?.length ?? 0
  const compileErrors = data.compileErrors ?? []
  const compileErrorCount = compileErrors.length
  // The expanded per-error list (field · line — message) lives on the trigger's accessible
  // name + native title too, so the detail is reachable without opening the portalled Radix
  // Tooltip (and survives SSR / screen readers) — same idiom as PropertiesPanel's marker.
  const compileErrorSummary = compileErrorCount > 0
    ? `${compileErrorCount} compile error${compileErrorCount === 1 ? '' : 's'} on this node: ${compileErrors.map(formatNodeCompileError).join('; ')}`
    : ''
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
  const canEditSteps = kind === 'AGENT' && typeof data.onToggleSteps === 'function' && typeof data.agentBody === 'string'

  const nodeContent = (
    <div
      aria-disabled={isDirtyDownstream || undefined}
      data-dirty-downstream={isDirtyDownstream || undefined}
      className={[
        'group relative min-w-[240px] cursor-pointer rounded-md border bg-card p-3 text-card-foreground shadow-sm transition-colors',
        isDirtyDownstream ? 'opacity-50 grayscale' : '',
        data.isConflictCancelled
          ? 'border-destructive ring-2 ring-destructive/30'
          : data.activeConflict
          ? 'border-amber-500 ring-2 ring-amber-500/30'
          : selected
          ? 'border-primary ring-2 ring-primary/30'
          : 'border-border',
      ].join(' ')}
    >
      <Handle type="target" position={Position.Top} className="!size-2.5 !border-background !bg-primary opacity-60 group-hover:opacity-100 transition-opacity duration-200" />
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
            {compileErrorCount > 0 ? (
              <Tooltip>
                <TooltipTrigger asChild>
                  <span
                    aria-label={compileErrorSummary}
                    title={compileErrorSummary}
                    className="inline-flex items-center gap-0.5 rounded-md border border-destructive/40 bg-destructive/10 px-1 font-medium text-destructive"
                  >
                    <AlertTriangle className="size-3" />
                    {compileErrorCount}
                  </span>
                </TooltipTrigger>
                <TooltipContent side="top">
                  <div className="mb-1 font-medium">
                    {compileErrorCount} compile error{compileErrorCount === 1 ? '' : 's'} on this node
                  </div>
                  <ul className="space-y-0.5">
                    {compileErrors.map((error, index) => (
                      <li key={`${error.field ?? 'node'}:${error.line ?? '?'}:${index}`}>
                        {formatNodeCompileError(error)}
                      </li>
                    ))}
                  </ul>
                </TooltipContent>
              </Tooltip>
            ) : null}
            {hasGolden ? (
              <Tooltip>
                <TooltipTrigger asChild>
                  <span
                    aria-label="Golden captured"
                    className="inline-flex size-5 items-center justify-center rounded-md border border-emerald-500/45 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
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
                    aria-label="Logic OK (predict ran, no golden yet)"
                    className="inline-flex size-5 items-center justify-center rounded-md border border-amber-500/45 bg-amber-500/10 text-amber-700 dark:text-amber-300"
                  >
                    <ShieldHalf className="size-3" />
                  </span>
                </TooltipTrigger>
                <TooltipContent side="top">Predict ran this node — no golden yet</TooltipContent>
              </Tooltip>
            ) : null}
          </div>
        </div>
        <Tooltip>
          <TooltipTrigger asChild>
            <span className={['inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[11px] font-medium', style.className].join(' ')}>
              <StatusIcon className="size-3" />
              {style.label}
            </span>
          </TooltipTrigger>
          <TooltipContent side="top">{style.label}</TooltipContent>
        </Tooltip>
      </div>
      {inlineErrorMessage ? (
        <div
          role="alert"
          aria-label="Node error summary"
          className="mt-2 flex items-start gap-1.5 rounded-md border border-destructive/40 bg-destructive/10 px-2 py-1 text-xs text-destructive"
        >
          <AlertTriangle className="mt-0.5 size-3 shrink-0" />
          <span className="min-w-0 break-words">{inlineErrorMessage}</span>
        </div>
      ) : null}
      {isDirtyDownstream ? (
        <div
          role="note"
          aria-label="Resume unavailable: upstream changed"
          className="mt-2 flex items-start gap-1.5 rounded-md border border-border bg-muted/50 px-2 py-1 text-xs text-muted-foreground"
        >
          <Pause className="mt-0.5 size-3 shrink-0" />
          <span className="min-w-0 break-words">Resume unavailable — an upstream edit invalidated this node&apos;s checkpoint</span>
        </div>
      ) : null}
      {canEditSteps ? (
        <div className="mt-2">
          <button
            type="button"
            aria-label={data.isStepsExpanded ? 'Collapse steps' : 'Edit steps'}
            onClick={(event) => {
              event.stopPropagation()
              data.onToggleSteps?.()
            }}
            className="inline-flex items-center gap-1 rounded-md border border-border bg-card px-1.5 py-0.5 text-[11px] font-medium text-muted-foreground transition-colors hover:border-primary hover:text-foreground"
          >
            <ListTree className="size-3" />
            {data.isStepsExpanded ? 'Hide steps' : 'Edit steps'}
          </button>
          {data.isStepsExpanded ? (
            <div
              onClick={(event) => event.stopPropagation()}
              onDoubleClick={(event) => event.stopPropagation()}
            >
              <AgentStepsInline
                body={data.agentBody ?? ''}
                onSave={(nextBody) => data.onStepsSave?.(nextBody)}
              />
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
            aria-label={data.isExpanded ? 'Collapse subgraph' : 'Expand subgraph'}
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
      <Handle type="source" position={Position.Bottom} className="!size-2.5 !border-background !bg-primary opacity-60 group-hover:opacity-100 transition-opacity duration-200" />
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
            <AlertTriangle className="size-4 shrink-0 text-amber-500 mt-0.5" />
            <div className="flex-1 min-w-0">
              <h4 className="text-xs font-semibold text-foreground">Sequential Overwrite Detected</h4>
              <p className="mt-1 text-[11px] text-muted-foreground leading-normal">
                Field <code className="text-amber-400 font-mono text-[10px] px-1 py-0.5 bg-zinc-900 rounded">{data.activeConflict.fieldName}</code> is also output by upstream node <span className="font-semibold">{data.activeConflict.ancestorNodeId}</span> and will be overwritten.
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
                  Cancel
                </Button>
                  <Button
                    size="sm"
                    variant="default"
                    className="h-7 text-[11px] px-2.5 bg-amber-500 hover:bg-amber-600 text-zinc-950 font-medium rounded-md"
                    onClick={() => data.onAllowSequentialOverwrite?.(
                      data.activeConflict!.nodeId,
                      data.activeConflict!.fieldName,
                      data.activeConflict!.ancestorNodeId,
                    )}
                  >
                    Allow Overwrite
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
